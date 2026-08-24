"""Maintained MCP tools and resources over :mod:`librsi.service`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from mcp.server import MCPServer
from mcp.server.auth.provider import TokenVerifier
from mcp.server.auth.settings import AuthSettings

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

    def bound(payload: object, label: str) -> None:
        require_json_size(payload, limit=service.limits.max_request_bytes, label=label)

    def start(workflow: str, request: Mapping[str, Any], admission_id: str) -> dict[str, Any]:
        bound({"request": request, "admission_id": admission_id}, f"{workflow} start")
        record = canonical_record_from_dict(request, label=f"{workflow} request")
        expected = {
            "validation": ValidationRequest,
            "investigation": InvestigationRequest,
            "improvement": ImprovementRequest,
            "rsi": RSIRequest,
        }[workflow]
        if type(record) is not expected:
            raise TypeError(f"{workflow} requires a canonical {expected.__name__}")
        return service.start(cast(Any, record), admission_id=admission_id)

    @server.tool(name="librsi_target_submit", structured_output=True)
    def target_submit(admission: dict[str, Any]) -> dict[str, Any]:
        """Admit one exact target/objective/evaluation/authority contract."""

        bound({"admission": admission}, "target submission")
        record = canonical_record_from_dict(admission, label="target admission")
        if type(record) is not TargetAdmission:
            raise TypeError("target submission requires a TargetAdmission")
        return service.submit_target(record)

    @server.tool(name="librsi_validate", structured_output=True)
    def validate(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable validation run and return its explicit handle."""

        return start("validation", request, admission_id)

    @server.tool(name="librsi_investigate", structured_output=True)
    def investigate(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable investigation run and return its explicit handle."""

        return start("investigation", request, admission_id)

    @server.tool(name="librsi_improve", structured_output=True)
    def improve(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one durable improvement run and return its explicit handle."""

        return start("improvement", request, admission_id)

    @server.tool(name="librsi_recurse", structured_output=True)
    def recurse(request: dict[str, Any], admission_id: str) -> dict[str, Any]:
        """Start one governed recursive-self-improvement run."""

        return start("rsi", request, admission_id)

    @server.tool(name="librsi_run_status", structured_output=True)
    def run_status(run_id: str) -> dict[str, Any]:
        """Inspect canonical durable run state."""

        bound({"run_id": run_id}, "run status")
        return service.get_status(run_id)

    @server.tool(name="librsi_run_next", structured_output=True)
    def run_next(run_id: str) -> dict[str, Any]:
        """Return the exact pending action, context, and result schema."""

        bound({"run_id": run_id}, "next action")
        return service.next_actions(run_id)

    @server.tool(name="librsi_run_submit", structured_output=True)
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
        record = canonical_record_from_dict(result, label="action result")
        if type(record) is not ActionResult:
            raise TypeError("run submission requires an ActionResult")
        if authority not in {"external", "human-reserved"}:
            raise PermissionError("MCP callers cannot claim automatic capability authority")
        if record.action.kind in _APPLICATION_ACTIONS:
            raise PermissionError("MCP result submission does not grant application authority")
        snapshot = None
        if current_snapshot is not None:
            supplied = canonical_record_from_dict(current_snapshot, label="current snapshot")
            if type(supplied) is not TargetSnapshot:
                raise TypeError("current snapshot must be a TargetSnapshot")
            snapshot = supplied
        return service.submit_result(
            run_id,
            record,
            authority=authority,
            current_snapshot=snapshot,
        )

    @server.tool(name="librsi_run_resume", structured_output=True)
    def run_resume(run_id: str) -> dict[str, Any]:
        """Reconstruct a durable run from canonical persisted history."""

        bound({"run_id": run_id}, "run resume")
        return service.resume(run_id)

    @server.tool(name="librsi_run_managed", structured_output=True)
    def run_managed(run_id: str, max_actions: int) -> dict[str, Any]:
        """Execute a bounded automatic pass that always stops at application authority."""

        bound({"run_id": run_id, "max_actions": max_actions}, "managed execution")
        execution = service.run_managed(
            run_id,
            ManagedBounds(max_actions=max_actions, allow_application=False),
        )
        return response_document(
            "managed",
            run_id=run_id,
            state_root=execution.state_root,
            data={"execution": execution.to_dict()},
        )

    @server.tool(name="librsi_run_outcome", structured_output=True)
    def run_outcome(run_id: str) -> dict[str, Any]:
        """Return the canonical versioned outcome projection for a terminal run."""

        bound({"run_id": run_id}, "run outcome")
        return service.get_outcome(run_id)

    @server.tool(name="librsi_knowledge_query", structured_output=True)
    def knowledge_query(query: dict[str, Any] | None = None) -> dict[str, Any]:
        """Query canonical knowledge without promoting transport data to evidence."""

        bound({"query": query}, "knowledge query")
        return service.query_knowledge(knowledge_query_from_dict({} if query is None else query))

    @server.tool(name="librsi_capabilities", structured_output=True)
    def capabilities() -> dict[str, Any]:
        """Inspect configured workflows, routes, authority, and bounds."""

        return service.capabilities()

    @server.resource(
        "librsi://runs/{run_id}",
        name="librsi-run",
        mime_type="application/json",
    )
    def run_resource(run_id: str) -> str:
        bound({"run_id": run_id}, "run resource")
        return serialize_response(service.get_run(run_id))

    @server.resource(
        "librsi://runs/{run_id}/outcome",
        name="librsi-outcome",
        mime_type="application/json",
    )
    def outcome_resource(run_id: str) -> str:
        bound({"run_id": run_id}, "outcome resource")
        return serialize_response(service.get_outcome(run_id))

    return server
