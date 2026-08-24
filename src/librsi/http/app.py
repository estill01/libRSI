"""FastAPI projection over :class:`librsi.service.LibRSIService`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..errors import RSICapabilityError
from ..improvement import ImprovementRequest
from ..investigation import InvestigationRequest
from ..protocol import TargetAdmission, error_document, response_document
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
from .auth import HTTPTokenPolicy


class _StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CanonicalRecordBody(_StrictBody):
    record: dict[str, Any]


class StartRunBody(_StrictBody):
    request: dict[str, Any]
    admission_id: str = Field(min_length=1)


class SubmitResultBody(_StrictBody):
    result: dict[str, Any]
    authority: str = Field(pattern="^(automatic|external|human-reserved)$")
    current_snapshot: dict[str, Any] | None = None


class ManagedRunBody(_StrictBody):
    max_actions: int = Field(gt=0)
    allow_application: bool = False


class KnowledgeQueryBody(_StrictBody):
    query: dict[str, Any] = Field(default_factory=dict)


def _status_for(error: Exception) -> int:
    if isinstance(error, PermissionError):
        return 403
    if isinstance(error, KeyError):
        return 404
    if isinstance(error, RSICapabilityError):
        return 409
    if isinstance(error, TypeError | ValueError):
        return 400
    return 500


def _safe_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, (PermissionError, KeyError, RSICapabilityError, TypeError, ValueError)):
        return error_document(error)
    return error_document(RuntimeError("internal service error"))


def create_http_app(
    service: LibRSIService,
    *,
    token_policy: HTTPTokenPolicy | None = None,
    close_service: bool = True,
) -> FastAPI:
    """Build a versioned HTTP projection with optional fail-closed bearer auth."""

    if type(service) is not LibRSIService:
        raise TypeError("HTTP projection requires a LibRSIService")
    if token_policy is not None and type(token_policy) is not HTTPTokenPolicy:
        raise TypeError("HTTP token policy is invalid")
    if type(close_service) is not bool:
        raise TypeError("HTTP close-service posture must be a boolean")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if close_service:
            service.close()

    app = FastAPI(
        title="libRSI service",
        version="1",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def limit_request_body(
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Any:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                announced = int(length)
            except ValueError:
                return JSONResponse(
                    status_code=400, content=error_document(ValueError("invalid content length"))
                )
            if announced > service.limits.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_document(ValueError("request body exceeds configured limit")),
                )
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > service.limits.max_request_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_document(ValueError("request body exceeds configured limit")),
                )
            body.extend(chunk)
        request._body = bytes(body)
        return await call_next(request)

    def authorize(request: Request, permission: str) -> None:
        if token_policy is not None:
            token_policy.authorize(request.headers.get("authorization"), permission)

    def bound(payload: object, label: str) -> None:
        require_json_size(payload, limit=service.limits.max_request_bytes, label=label)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_document(ValueError("request validation failed")),
        )

    async def service_error(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=_status_for(error), content=_safe_error(error))

    # Register expected service failures explicitly. FastAPI delegates a catch-all
    # ``Exception`` handler to its outer server-error middleware, which intentionally
    # re-raises after responding and is therefore unsuitable for protocol failures.
    for error_type in (PermissionError, KeyError, RSICapabilityError, TypeError, ValueError):
        app.add_exception_handler(error_type, service_error)

    @app.exception_handler(Exception)
    async def unexpected_service_error(_request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=_status_for(error), content=_safe_error(error))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return service.health()

    @app.get("/ready")
    async def ready(request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.readiness()

    @app.get("/v1/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.capabilities()

    @app.post("/v1/targets")
    async def submit_target(
        body: CanonicalRecordBody,
        request: Request,
    ) -> dict[str, Any]:
        authorize(request, "mutate")
        bound({"record": body.record}, "target submission")
        record = canonical_record_from_dict(body.record, label="target admission")
        if type(record) is not TargetAdmission:
            raise TypeError("target submission requires a TargetAdmission")
        return service.submit_target(record)

    def start_operation(
        workflow: str,
        body: StartRunBody,
    ) -> dict[str, Any]:
        bound(
            {"request": body.request, "admission_id": body.admission_id},
            f"{workflow} start",
        )
        record = canonical_record_from_dict(body.request, label=f"{workflow} request")
        expected = {
            "validation": ValidationRequest,
            "investigation": InvestigationRequest,
            "improvement": ImprovementRequest,
            "rsi": RSIRequest,
        }[workflow]
        if type(record) is not expected:
            raise TypeError(f"{workflow} start requires a canonical {expected.__name__}")
        return service.start(cast(Any, record), admission_id=body.admission_id)

    @app.post("/v1/runs/validation")
    async def start_validation(body: StartRunBody, request: Request) -> dict[str, Any]:
        authorize(request, "mutate")
        return start_operation("validation", body)

    @app.post("/v1/runs/investigation")
    async def start_investigation(body: StartRunBody, request: Request) -> dict[str, Any]:
        authorize(request, "mutate")
        return start_operation("investigation", body)

    @app.post("/v1/runs/improvement")
    async def start_improvement(body: StartRunBody, request: Request) -> dict[str, Any]:
        authorize(request, "mutate")
        return start_operation("improvement", body)

    @app.post("/v1/runs/rsi")
    async def start_rsi(body: StartRunBody, request: Request) -> dict[str, Any]:
        authorize(request, "mutate")
        return start_operation("rsi", body)

    @app.get("/v1/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.get_run(run_id)

    @app.get("/v1/runs/{run_id}/status")
    async def get_status(run_id: str, request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.get_status(run_id)

    @app.get("/v1/runs/{run_id}/actions")
    async def get_actions(run_id: str, request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.next_actions(run_id)

    @app.post("/v1/runs/{run_id}/results")
    async def submit_result(
        run_id: str,
        body: SubmitResultBody,
        request: Request,
    ) -> dict[str, Any]:
        bound(body.model_dump(), "result submission")
        result = canonical_record_from_dict(body.result, label="action result")
        if type(result) is not ActionResult:
            raise TypeError("result submission requires an ActionResult")
        permission = (
            "apply"
            if result.action.kind in {"apply-selected-candidate", "rollback-applied-target"}
            else "mutate"
        )
        authorize(request, permission)
        snapshot = None
        if body.current_snapshot is not None:
            record = canonical_record_from_dict(body.current_snapshot, label="current snapshot")
            if type(record) is not TargetSnapshot:
                raise TypeError("current snapshot must be a TargetSnapshot")
            snapshot = record
        return service.submit_result(
            run_id,
            result,
            authority=body.authority,
            current_snapshot=snapshot,
        )

    @app.post("/v1/runs/{run_id}/resume")
    async def resume(run_id: str, request: Request) -> dict[str, Any]:
        authorize(request, "mutate")
        return service.resume(run_id)

    @app.post("/v1/runs/{run_id}/managed")
    async def managed(
        run_id: str,
        body: ManagedRunBody,
        request: Request,
    ) -> dict[str, Any]:
        authorize(request, "apply" if body.allow_application else "mutate")
        execution = service.run_managed(
            run_id,
            ManagedBounds(
                max_actions=body.max_actions,
                allow_application=body.allow_application,
            ),
        )
        return response_document(
            "managed",
            run_id=run_id,
            state_root=execution.state_root,
            data={"execution": execution.to_dict()},
        )

    @app.get("/v1/runs/{run_id}/outcome")
    async def outcome(run_id: str, request: Request) -> dict[str, Any]:
        authorize(request, "read")
        return service.get_outcome(run_id)

    @app.post("/v1/knowledge/query")
    async def query_knowledge(
        body: KnowledgeQueryBody,
        request: Request,
    ) -> dict[str, Any]:
        authorize(request, "read")
        bound(body.model_dump(), "knowledge query")
        return service.query_knowledge(knowledge_query_from_dict(body.query))

    return app
