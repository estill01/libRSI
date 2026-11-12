"""Transport-independent service facade over canonical libRSI owners."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from threading import RLock
from typing import Any, cast

from ..capabilities import CapabilityRegistry
from ..improvement import ImprovementRequest
from ..intake import IntakeAdapter, IntakeAgent, IntakeRequest, SQLiteIntakeStore
from ..investigation import InvestigationRequest
from ..knowledge import KnowledgeQuery
from ..protocol import ExternalAgentController, TargetAdmission, response_document
from ..reasoning import ReasoningBackend
from ..records import TargetSnapshot, record_from_dict
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
        intake_agent: IntakeAgent | None = None,
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
        if intake_agent is not None and type(intake_agent) is not IntakeAgent:
            raise TypeError("service intake must be an IntakeAgent")
        self._intake = intake_agent

    @classmethod
    def local(
        cls,
        data_directory: str | Path,
        *,
        registry: CapabilityRegistry | None = None,
        limits: ServiceLimits | None = None,
        current_snapshot_resolver: Callable[[TargetSnapshot], TargetSnapshot] | None = None,
        intake_backend: ReasoningBackend | None = None,
        intake_adapters: tuple[IntakeAdapter, ...] = (),
    ) -> LibRSIService:
        if (intake_backend is None) != (not intake_adapters):
            raise ValueError("configure both an intake backend and adapters")
        controller = ExternalAgentController.local(data_directory)
        agent = None
        store = None
        try:
            if intake_backend is not None:
                store = SQLiteIntakeStore(Path(data_directory).expanduser() / "intake.sqlite3")
                agent = IntakeAgent(intake_backend, intake_adapters, store)
            return cls(
                controller,
                registry=registry,
                limits=limits,
                current_snapshot_resolver=current_snapshot_resolver,
                intake_agent=agent,
            )
        except Exception:
            controller.close()
            if store is not None:
                store.close()
            raise

    @property
    def intake_enabled(self) -> bool:
        return self._intake is not None

    def intake_adapters(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            return response_document(
                "intake.adapters",
                data={
                    "enabled": self.intake_enabled,
                    "adapters": [] if self._intake is None else self._intake.catalog(),
                },
            )

    def intake(self, request: IntakeRequest) -> dict[str, Any]:
        """Translate a goal and submit one run, without executing or applying it."""
        from ..errors import RSICapabilityError

        with self._lock:
            self._ensure_open()
            if self._intake is None:
                raise RSICapabilityError("no intake backend and adapters are configured")
            if type(request) is not IntakeRequest:
                raise TypeError("service intake requires an IntakeRequest")
            self._require_request_size(request.to_dict(), "intake request")
            receipt = self._intake.prepare(request)
            if "result" not in receipt:
                prepared = receipt["prepared"]
                admission = record_from_dict(prepared["admission"])
                workflow = record_from_dict(prepared["request"])
                if type(admission) is not TargetAdmission or type(workflow) not in {
                    ImprovementRequest,
                    InvestigationRequest,
                }:
                    raise ValueError("invalid prepared intake checkpoint")
                workflow = cast(ImprovementRequest | InvestigationRequest, workflow)
                run_id = workflow.canonical_run().run_id
                binding = self.controller.agent_store.load_run(run_id)
                if binding is not None and (
                    binding.request != workflow or binding.admission != admission
                ):
                    raise ValueError("intake run id already names different work")
                if binding is None or self.controller.runtime_store.resume(run_id) is None:
                    self._intake.require_current(request, receipt)
                    self.submit_target(admission)
                    self.start(workflow, admission_id=admission.admission_id)
                receipt["result"] = {
                    "request_id": request.request_id,
                    "disposition": "started",
                    "adapter_id": receipt["adapter_id"],
                    "run_id": run_id,
                    "workflow": "improvement"
                    if type(workflow) is ImprovementRequest
                    else "investigation",
                    "questions": [],
                    "criteria": admission.evaluation_contract.to_dict(),
                    "hypotheses": [item.to_dict() for item in workflow.initial_hypotheses],
                }
                self._intake.store.save(request.request_id, receipt)
            return response_document("intake.submit", data=receipt["result"])

    def intake_status(self, request_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            receipt = None if self._intake is None else self._intake.store.load(request_id)
            if receipt is None:
                raise KeyError("unknown intake request id")
            result = receipt.get(
                "result",
                {
                    "request_id": request_id,
                    "disposition": "pending",
                    "questions": [],
                    "run_id": None,
                },
            )
            return response_document("intake.status", data=result)

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
                    "intake_configured": self.intake_enabled,
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
                if self._intake is not None:
                    self._intake.close()
                self._closed = True

    def __enter__(self) -> LibRSIService:
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
