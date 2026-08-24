"""Maintained MCP tools and resources over :mod:`librsi.service`."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any, TypeVar, cast

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ResourceError, ResourceNotFoundError, ToolError

from ..improvement import ImprovementRequest
from ..investigation import InvestigationRequest
from ..protocol import TargetAdmission, response_document, serialize_response
from ..records import TargetSnapshot
from ..rsi import RSIRequest
from ..runtime import ActionResult
from ..service import (
    LibRSIService,
    ManagedBounds,
    canonical_record_from_dict,
    knowledge_query_from_dict,
    require_json_size,
)
from ..validation import ValidationRequest

_APPLICATION_ACTIONS = frozenset({"apply-selected-candidate", "rollback-applied-target"})
_Handler = TypeVar("_Handler", bound=Callable[..., Any])
_Value = TypeVar("_Value")


class _ClientFault(Exception):
    """A detail-safe fault created by this projection's own input boundary."""

    def __init__(self, origin: object, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.origin = origin
        self.not_found = not_found


def create_mcp_server(
    service: LibRSIService,
    *,
    auth: AuthSettings | None = None,
    token_verifier: TokenVerifier | None = None,
) -> MCPServer[Any]:
    """Build stdio/Streamable-HTTP MCP projections over one service instance."""

    if type(service) is not LibRSIService:
        raise TypeError("MCP projection requires a LibRSIService")
    if (auth is None) != (token_verifier is None):
        raise ValueError("MCP auth settings and token verifier must be configured together")
    server: MCPServer[Any] = MCPServer(
        "libRSI",
        version="1",
        description="Bounded evidence-driven workflows over canonical libRSI state",
        instructions=(
            "Use explicit durable run IDs. MCP transport access does not grant "
            "application authority; application and rollback results are not accepted "
            "through the generic MCP submission tool."
        ),
        auth=auth,
        token_verifier=token_verifier,
    )
    client_origin = object()

    def client_fault(message: str, *, not_found: bool = False) -> _ClientFault:
        return _ClientFault(client_origin, message, not_found=not_found)

    def client_value(operation: Callable[[], _Value]) -> _Value:
        """Translate only this projection instance's validation into a trusted fault."""

        try:
            return operation()
        except _ClientFault as error:
            if type(error) is _ClientFault and error.origin is client_origin:
                raise
            raise ToolError("internal tool error") from error
        except (PermissionError, TypeError, ValueError) as error:
            raise client_fault(str(error)) from error

    def tool_errors(handler: _Handler) -> _Handler:
        """Expose only instance-bound client faults; mask every host/service fault."""

        @wraps(handler)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            try:
                return handler(*args, **kwargs)
            except _ClientFault as error:
                if type(error) is _ClientFault and error.origin is client_origin:
                    raise ToolError(str(error)) from error
                raise ToolError("internal tool error") from error
            except Exception as error:
                raise ToolError("internal tool error") from error

        return cast(_Handler, guarded)

    def resource_errors(handler: _Handler) -> _Handler:
        """Use the resource channel only for instance-bound projection faults."""

        @wraps(handler)
        def guarded(*args: Any, **kwargs: Any) -> Any:
            try:
                return handler(*args, **kwargs)
            except _ClientFault as error:
                if type(error) is not _ClientFault or error.origin is not client_origin:
                    raise ResourceError("internal resource error") from error
                if error.not_found:
                    raise ResourceNotFoundError(str(error)) from error
                raise ResourceError(str(error)) from error
            except Exception as error:
                raise ResourceError("internal resource error") from error

        return cast(_Handler, guarded)

    def bound(payload: object, label: str) -> None:
        client_value(
            lambda: require_json_size(
                payload,
                limit=service.limits.max_request_bytes,
                label=label,
            )
        )

    def canonical(payload: Mapping[str, Any], label: str) -> object:
        return client_value(lambda: canonical_record_from_dict(payload, label=label))

    def require_run(run_id: str) -> None:
        if service.controller.agent_store.load_run(run_id) is None:
            raise client_fault("unknown external run id", not_found=True)

    def require_admission(admission_id: str) -> None:
        if service.controller.agent_store.get_admission(admission_id) is None:
            raise client_fault("unknown target admission id", not_found=True)

    def start(workflow: str, request: Mapping[str, Any], admission_id: str) -> dict[str, Any]:
        bound({"request": request, "admission_id": admission_id}, f"{workflow} start")
        record = canonical(request, f"{workflow} request")
        expected = {
            "validation": ValidationRequest,
            "investigation": InvestigationRequest,
            "improvement": ImprovementRequest,
            "rsi": RSIRequest,
        }[workflow]
        if type(record) is not expected:
            raise client_fault(f"{workflow} requires a canonical {expected.__name__}")
        require_admission(admission_id)
        return service.start(cast(Any, record), admission_id=admission_id)

    @server.tool(name="librsi_target_submit", structured_output=True)
    @tool_errors
    def target_submit(admission: dict[str, Any]) -> dict[str, Any]:
        """Admit one exact target/objective/evaluation/authority contract."""

        bound({"admission": admission}, "target submission")
        record = canonical(admission, "target admission")
        if type(record) is not TargetAdmission:
            raise client_fault("target submission requires a TargetAdmission")
        return service.submit_target(record)

    @server.tool(name="librsi_validate", structured_output=True)
    @tool_errors
    def validate(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable validation run and return its explicit handle."""

        return start("validation", request, admission_id)

    @server.tool(name="librsi_investigate", structured_output=True)
    @tool_errors
    def investigate(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable investigation run and return its explicit handle."""

        return start("investigation", request, admission_id)

    @server.tool(name="librsi_improve", structured_output=True)
    @tool_errors
    def improve(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable improvement run and return its explicit handle."""

        return start("improvement", request, admission_id)

    @server.tool(name="librsi_recurse", structured_output=True)
    @tool_errors
    def recurse(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one governed recursive-self-improvement run."""

        return start("rsi", request, admission_id)

    @server.tool(name="librsi_run_status", structured_output=True)
    @tool_errors
    def run_status(run_id: str) -> dict[str, Any]:
        """Inspect canonical durable run state."""

        bound({"run_id": run_id}, "run status")
        require_run(run_id)
        return service.get_status(run_id)

    @server.tool(name="librsi_run_next", structured_output=True)
    @tool_errors
    def run_next(run_id: str) -> dict[str, Any]:
        """Return the exact pending action, context, and result schema."""

        bound({"run_id": run_id}, "next action")
        require_run(run_id)
        return service.next_actions(run_id)

    @server.tool(name="librsi_run_submit", structured_output=True)
    @tool_errors
    def run_submit(
        run_id: str,
        result: dict[str, Any],
        authority: str,
        current_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Submit one external/human result; application requires another authority path."""

        bound(
            {
                "run_id": run_id,
                "result": result,
                "authority": authority,
                "current_snapshot": current_snapshot,
            },
            "result submission",
        )
        record = canonical(result, "action result")
        if type(record) is not ActionResult:
            raise client_fault("run submission requires an ActionResult")
        if authority not in {"external", "human-reserved"}:
            raise client_fault("MCP callers cannot claim automatic capability authority")
        if record.action.kind in _APPLICATION_ACTIONS:
            raise client_fault("MCP result submission does not grant application authority")
        snapshot = None
        if current_snapshot is not None:
            supplied = canonical(current_snapshot, "current snapshot")
            if type(supplied) is not TargetSnapshot:
                raise client_fault("current snapshot must be a TargetSnapshot")
            snapshot = supplied
        require_run(run_id)
        return service.submit_result(
            run_id,
            record,
            authority=authority,
            current_snapshot=snapshot,
        )

    @server.tool(name="librsi_run_resume", structured_output=True)
    @tool_errors
    def run_resume(run_id: str) -> dict[str, Any]:
        """Reconstruct a durable run from canonical persisted history."""

        bound({"run_id": run_id}, "run resume")
        require_run(run_id)
        return service.resume(run_id)

    @server.tool(name="librsi_run_managed", structured_output=True)
    @tool_errors
    def run_managed(run_id: str, max_actions: int) -> dict[str, Any]:
        """Execute a bounded automatic pass that always stops at application authority."""

        bound({"run_id": run_id, "max_actions": max_actions}, "managed execution")
        bounds = client_value(
            lambda: ManagedBounds(max_actions=max_actions, allow_application=False)
        )
        require_run(run_id)
        execution = service.run_managed(
            run_id,
            bounds,
        )
        return response_document(
            "managed",
            run_id=run_id,
            state_root=execution.state_root,
            data={"execution": execution.to_dict()},
        )

    @server.tool(name="librsi_run_outcome", structured_output=True)
    @tool_errors
    def run_outcome(run_id: str) -> dict[str, Any]:
        """Return the canonical versioned outcome projection for a terminal run."""

        bound({"run_id": run_id}, "run outcome")
        require_run(run_id)
        return service.get_outcome(run_id)

    @server.tool(name="librsi_knowledge_query", structured_output=True)
    @tool_errors
    def knowledge_query(query: dict[str, Any] | None = None) -> dict[str, Any]:
        """Query canonical knowledge without promoting transport data to evidence."""

        bound({"query": query}, "knowledge query")
        decoded = client_value(lambda: knowledge_query_from_dict({} if query is None else query))
        return service.query_knowledge(decoded)

    @server.tool(name="librsi_capabilities", structured_output=True)
    @tool_errors
    def capabilities() -> dict[str, Any]:
        """Inspect configured workflows, routes, authority, and bounds."""

        return service.capabilities()

    @server.resource(
        "librsi://runs/{run_id}",
        name="librsi-run",
        mime_type="application/json",
    )
    @resource_errors
    def run_resource(run_id: str) -> str:
        bound({"run_id": run_id}, "run resource")
        require_run(run_id)
        return serialize_response(service.get_run(run_id))

    @server.resource(
        "librsi://runs/{run_id}/outcome",
        name="librsi-outcome",
        mime_type="application/json",
    )
    @resource_errors
    def outcome_resource(run_id: str) -> str:
        bound({"run_id": run_id}, "outcome resource")
        require_run(run_id)
        return serialize_response(service.get_outcome(run_id))

    return server
