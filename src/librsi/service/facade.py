"""Transport-independent service facade over canonical libRSI owners."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any

from ..capabilities import CapabilityRegistry
from ..improvement import ImprovementRequest
from ..investigation import InvestigationRequest
from ..knowledge import KnowledgeQuery
from ..protocol import ExternalAgentController, TargetAdmission, response_document
from ..records import TargetSnapshot
from ..rsi import RSIRequest
from ..runtime import ActionResult
from ..validation import ValidationRequest
from .codec import knowledge_query_to_dict, require_json_size
from .managed import ManagedServiceRunner
from .records import ManagedBounds, ManagedExecution, ServiceLimits

ServiceRequest = ValidationRequest | InvestigationRequest | ImprovementRequest | RSIRequest


class LibRSIService:
    """Shared service abstraction used unchanged by Python, HTTP, and MCP."""

    def __init__(
        self,
        controller: ExternalAgentController,
        *,
        registry: CapabilityRegistry | None = None,
        limits: ServiceLimits | None = None,
        current_snapshot_resolver: Callable[[TargetSnapshot], TargetSnapshot] | None = None,
    ) -> None:
        if type(controller) is not ExternalAgentController:
            raise TypeError("service requires an ExternalAgentController")
        if registry is not None and not isinstance(registry, CapabilityRegistry):
            raise TypeError("service registry must be a CapabilityRegistry")
        if limits is not None and type(limits) is not ServiceLimits:
            raise TypeError("service limits must be ServiceLimits")
        if current_snapshot_resolver is not None and not callable(current_snapshot_resolver):
            raise TypeError("service current snapshot resolver must be callable")
        self.controller = controller
        self.registry = CapabilityRegistry() if registry is None else registry
        self.controller.configure_capabilities(self.registry)
        self.limits = ServiceLimits() if limits is None else limits
        self._current_snapshot_resolver = current_snapshot_resolver
        self._managed = ManagedServiceRunner(
            controller,
            self.registry,
            self.limits,
            current_snapshot_resolver,
        )
        self._closed = False
        self._lock = RLock()

    @classmethod
    def local(
        cls,
        data_directory: str | Path,
        *,
        registry: CapabilityRegistry | None = None,
        limits: ServiceLimits | None = None,
        current_snapshot_resolver: Callable[[TargetSnapshot], TargetSnapshot] | None = None,
    ) -> LibRSIService:
        return cls(
            ExternalAgentController.local(data_directory),
            registry=registry,
            limits=limits,
            current_snapshot_resolver=current_snapshot_resolver,
        )

    def _require_request_size(self, payload: object, label: str) -> None:
        require_json_size(payload, limit=self.limits.max_request_bytes, label=label)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("libRSI service is closed")

    def submit_target(self, admission: TargetAdmission) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            if type(admission) is not TargetAdmission:
                raise TypeError("target submission requires a TargetAdmission")
            self._require_request_size({"record": admission.to_dict()}, "target submission")
            return self.controller.submit_target(admission)

    def start(self, request: ServiceRequest, *, admission_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            if type(request) not in {
                ValidationRequest,
                InvestigationRequest,
                ImprovementRequest,
                RSIRequest,
            }:
                raise TypeError("service start requires a canonical workflow request")
            self._require_request_size(
                {"request": request.to_dict(), "admission_id": admission_id},
                "run start",
            )
            return self.controller.start(request, admission_id=admission_id)

    def validate(self, request: ValidationRequest, *, admission_id: str) -> dict[str, Any]:
        if type(request) is not ValidationRequest:
            raise TypeError("validate requires a ValidationRequest")
        return self.start(request, admission_id=admission_id)

    def investigate(
        self,
        request: InvestigationRequest,
        *,
        admission_id: str,
    ) -> dict[str, Any]:
        if type(request) is not InvestigationRequest:
            raise TypeError("investigate requires an InvestigationRequest")
        return self.start(request, admission_id=admission_id)

    def improve(self, request: ImprovementRequest, *, admission_id: str) -> dict[str, Any]:
        if type(request) is not ImprovementRequest:
            raise TypeError("improve requires an ImprovementRequest")
        return self.start(request, admission_id=admission_id)

    def recurse(self, request: RSIRequest, *, admission_id: str) -> dict[str, Any]:
        if type(request) is not RSIRequest:
            raise TypeError("recurse requires an RSIRequest")
        return self.start(request, admission_id=admission_id)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return self.controller.status(run_id)

    def get_status(self, run_id: str) -> dict[str, Any]:
        return self.get_run(run_id)

    def next_actions(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return self.controller.next(run_id)

    def submit_result(
        self,
        run_id: str,
        result: ActionResult,
        *,
        authority: str,
        current_snapshot: TargetSnapshot | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            if type(result) is not ActionResult:
                raise TypeError("result submission requires an ActionResult")
            if authority == "automatic":
                raise PermissionError(
                    "automatic capability authority is reserved for managed execution"
                )
            self._require_request_size(
                {
                    "run_id": run_id,
                    "result": result.to_dict(),
                    "authority": authority,
                    "current_snapshot": (
                        None if current_snapshot is None else current_snapshot.to_dict()
                    ),
                },
                "result submission",
            )
            return self.controller.submit(
                run_id,
                result,
                authority=authority,
                current_snapshot=current_snapshot,
            )

    def resume(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return self.controller.resume(run_id)

    def get_outcome(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return self.controller.outcome(run_id)

    def run_managed(self, run_id: str, bounds: ManagedBounds) -> ManagedExecution:
        with self._lock:
            self._ensure_open()
            return self._managed.run(run_id, bounds)

    def query_knowledge(self, query: KnowledgeQuery | None = None) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            query = KnowledgeQuery() if query is None else query
            if not isinstance(query, KnowledgeQuery):
                raise TypeError("service knowledge queries require KnowledgeQuery")
            self._require_request_size(knowledge_query_to_dict(query), "knowledge query")
            if query.limit is None:
                query = replace(query, limit=self.limits.max_query_results)
            elif query.limit > self.limits.max_query_results:
                raise ValueError("knowledge query exceeds the configured result limit")
            items = self.controller.knowledge_store.query(query)
            return response_document(
                "knowledge.query",
                data={
                    "items": [
                        {
                            "record": item.record.to_dict(),
                            "source_run_id": item.source_run_id,
                            "valid": item.valid,
                            "stored_at": item.stored_at,
                            "currentness": item.currentness,
                        }
                        for item in items
                    ],
                    "count": len(items),
                },
            )

    def capabilities(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            families = self.registry.configured_families
            return response_document(
                "capabilities",
                data={
                    "workflows": ["validation", "investigation", "improvement", "rsi"],
                    "operations": [
                        "target.submit",
                        "run.start",
                        "run.status",
                        "run.next",
                        "run.submit",
                        "run.resume",
                        "run.outcome",
                        "run.managed",
                        "knowledge.query",
                    ],
                    "configured_families": list(families),
                    "routes": [
                        {
                            "action_kind": route.action_kind,
                            "family": route.family,
                            "posture": route.posture,
                            "implementation_configured": route.family in families,
                        }
                        for route in self.registry.routes
                    ],
                    "application_execution_configured": "applier" in families,
                    "application_currentness_configured": (
                        self._current_snapshot_resolver is not None
                    ),
                    "limits": self.limits.to_dict(),
                },
            )

    def health(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return response_document("health", data={"status": "ok"})

    def readiness(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            self.controller.knowledge_store.query(KnowledgeQuery(limit=1))
            return response_document("readiness", data={"status": "ready"})

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self.controller.close()
                self._closed = True

    def __enter__(self) -> LibRSIService:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
