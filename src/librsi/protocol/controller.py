"""Transport-neutral external-agent operations over canonical workflows."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any, TypeAlias

from ..application import (
    APPLY_CANDIDATE_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    application_receipt_from_result,
    rollback_receipt_from_result,
)
from ..capabilities import CapabilityRegistry
from ..improvement import (
    ImprovementProgress,
    ImprovementRequest,
    ImprovementUpdate,
    ImprovementWorkflow,
)
from ..investigation import (
    InvestigationProgress,
    InvestigationRequest,
    InvestigationUpdate,
    InvestigationWorkflow,
)
from ..knowledge import KnowledgeWrite
from ..projections import project_result, projection_to_dict
from ..records import EvidenceRef, TargetSnapshot
from ..rsi import RSIProgress, RSIRequest, RSIUpdate, RSIWorkflow
from ..runtime import (
    ActionResult,
    RunBudget,
    RunState,
    RuntimeStore,
    Transition,
    persist_transitions,
)
from ..runtime.sqlite import SQLiteRuntimeStore
from ..sqlite_knowledge import SQLiteKnowledgeStore
from ..validation import (
    ValidationProgress,
    ValidationRequest,
    ValidationUpdate,
    ValidationWorkflow,
)
from .codec import response_document
from .records import TargetAdmission
from .schemas import action_result_schema
from .sqlite import AgentRunBinding, SQLiteAgentStore, WorkflowRequest

Progress: TypeAlias = ValidationProgress | InvestigationProgress | ImprovementProgress | RSIProgress
Workflow: TypeAlias = ValidationWorkflow | InvestigationWorkflow | ImprovementWorkflow | RSIWorkflow
Update: TypeAlias = ValidationUpdate | InvestigationUpdate | ImprovementUpdate | RSIUpdate


def _request_snapshot(request: WorkflowRequest) -> TargetSnapshot | None:
    if type(request) is ValidationRequest or type(request) is InvestigationRequest:
        return request.target_snapshot
    if type(request) is ImprovementRequest:
        return request.baseline
    if type(request) is RSIRequest:
        return request.declaration.target_snapshot
    raise TypeError("unsupported external workflow request")


def _workflow_name(request: WorkflowRequest) -> str:
    return {
        ValidationRequest: "validation",
        InvestigationRequest: "investigation",
        ImprovementRequest: "improvement",
        RSIRequest: "rsi",
    }[type(request)]


def _within_limits(budget: RunBudget, admission: TargetAdmission) -> None:
    limits = admission.resource_limits
    values = {
        "max_actions": budget.max_actions,
        "max_failures": budget.max_failures,
        "max_retries": budget.max_retries,
        **dict(budget.resource_limits),
    }
    if any(
        name not in limits or float(value) > float(limits[name]) for name, value in values.items()
    ):
        raise ValueError("workflow run budget exceeds its target admission")


class ExternalAgentController:
    """Durable command semantics shared by CLI and later service projections."""

    def __init__(
        self,
        *,
        agent_store: SQLiteAgentStore,
        runtime_store: RuntimeStore,
        knowledge_store: SQLiteKnowledgeStore,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        if type(agent_store) is not SQLiteAgentStore:
            raise TypeError("external controller requires a SQLiteAgentStore")
        if not isinstance(runtime_store, RuntimeStore):
            raise TypeError("external controller requires a RuntimeStore")
        if type(knowledge_store) is not SQLiteKnowledgeStore:
            raise TypeError("external controller requires a SQLiteKnowledgeStore")
        if capability_registry is not None and not isinstance(
            capability_registry, CapabilityRegistry
        ):
            raise TypeError("external controller capability registry is invalid")
        self.agent_store = agent_store
        self.runtime_store = runtime_store
        self.knowledge_store = knowledge_store
        self._capability_registry = capability_registry

    @classmethod
    def local(
        cls,
        data_directory: str | Path,
        *,
        capability_registry: CapabilityRegistry | None = None,
    ) -> ExternalAgentController:
        directory = Path(data_directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return cls(
            agent_store=SQLiteAgentStore(directory / "agent.sqlite3"),
            runtime_store=SQLiteRuntimeStore(directory / "runtime.sqlite3"),
            knowledge_store=SQLiteKnowledgeStore(directory / "knowledge.sqlite3"),
            capability_registry=capability_registry,
        )

    def configure_capabilities(self, registry: CapabilityRegistry) -> None:
        """Attach one process-owned provider registry to this controller composition."""

        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("external controller capability registry is invalid")
        if self._capability_registry is not None and self._capability_registry is not registry:
            raise ValueError("external controller already has a different capability registry")
        self._capability_registry = registry

    def close(self) -> None:
        self.agent_store.close()
        self.runtime_store.close()
        self.knowledge_store.close()

    def submit_target(self, admission: TargetAdmission) -> dict[str, Any]:
        stored = self.agent_store.put_admission(admission)
        if admission.evidence_baseline:
            self.knowledge_store.put_many(
                tuple(KnowledgeWrite(item, valid=True) for item in admission.evidence_baseline)
            )
        return response_document(
            "target.submit",
            data={
                "admission_id": stored.admission_id,
                "admission_root": stored.root,
                "target_snapshot_root": stored.target_snapshot.root,
            },
        )

    @staticmethod
    def _validate_admission(request: WorkflowRequest, admission: TargetAdmission) -> None:
        snapshot = _request_snapshot(request)
        if snapshot is None or snapshot != admission.target_snapshot:
            raise ValueError("workflow request does not use the admitted target snapshot")
        _within_limits(request.canonical_run().budget, admission)
        if type(request) is ImprovementRequest and (
            request.contract != admission.evaluation_contract
            or request.governance_requirement != admission.application_requirement
        ):
            raise ValueError("improvement request is not bound to the target admission")
        if type(request) is RSIRequest:
            improvement = request.improvement.request
            if (
                improvement.contract != admission.evaluation_contract
                or improvement.governance_requirement != admission.application_requirement
            ):
                raise ValueError("RSI request is not bound to the target admission")

    def _registry(self, admission: TargetAdmission) -> CapabilityRegistry:
        routes = tuple(item.route() for item in admission.capabilities)
        if self._capability_registry is None:
            return CapabilityRegistry(routes=routes)
        return self._capability_registry.scoped(routes)

    def _workflow(self, binding: AgentRunBinding) -> Workflow:
        if binding.workflow == "validation":
            return ValidationWorkflow()
        if binding.workflow == "investigation":
            return InvestigationWorkflow()
        if binding.workflow == "improvement":
            return ImprovementWorkflow()
        if binding.workflow == "rsi":
            return RSIWorkflow(self._registry(binding.admission))
        raise ValueError("unsupported bound workflow")

    def _record(self, transitions: Sequence[Transition]) -> None:
        persist_transitions(self.runtime_store, tuple(transitions))

    def start(
        self,
        request: WorkflowRequest,
        *,
        admission_id: str,
    ) -> dict[str, Any]:
        admission = self.agent_store.get_admission(admission_id)
        if admission is None:
            raise ValueError("unknown target admission")
        self._validate_admission(request, admission)
        snapshot = _request_snapshot(request)
        assert snapshot is not None
        binding = AgentRunBinding(_workflow_name(request), request, admission, snapshot)
        existing = self.agent_store.load_run(binding.run_id)
        if existing is not None:
            if existing != binding:
                raise ValueError("external run id is already bound to divergent data")
            if self.runtime_store.resume(binding.run_id) is not None:
                raise ValueError("external run id is already bound; use resume")
        else:
            self.agent_store.bind_run(binding)
        workflow = self._workflow(binding)
        update: Update
        if type(request) is ValidationRequest:
            assert type(workflow) is ValidationWorkflow
            update = workflow.start(request, knowledge_store=self.knowledge_store)
        elif type(request) is InvestigationRequest:
            assert type(workflow) is InvestigationWorkflow
            update = workflow.start(request, knowledge_store=self.knowledge_store)
        elif type(request) is ImprovementRequest:
            assert type(workflow) is ImprovementWorkflow
            update = workflow.start(request, current_snapshot=snapshot)
        else:
            assert type(request) is RSIRequest and type(workflow) is RSIWorkflow
            update = workflow.start(request, current_snapshot=snapshot)
        self._record(update.transitions)
        return self._status(binding, update.progress, operation=binding.workflow)

    def _binding(self, run_id: str) -> AgentRunBinding:
        binding = self.agent_store.load_run(run_id)
        if binding is None:
            raise ValueError("unknown external run id")
        return binding

    @staticmethod
    def _application_snapshot(
        baseline: TargetSnapshot,
        state: RunState,
    ) -> TargetSnapshot:
        observed = baseline
        for result in state.results:
            if result.disposition != "succeeded":
                continue
            if result.action.kind == APPLY_CANDIDATE_ACTION_KIND:
                observed = application_receipt_from_result(result).produced_snapshot
            elif result.action.kind == ROLLBACK_APPLICATION_ACTION_KIND:
                observed = rollback_receipt_from_result(result).restored_snapshot
        return observed

    def _resume(self, binding: AgentRunBinding) -> tuple[AgentRunBinding, Progress]:
        state = self.runtime_store.resume(binding.run_id)
        if state is None:
            raise ValueError("external run has no authoritative runtime history")
        workflow = self._workflow(binding)
        request = binding.request
        update: Update
        if type(request) is ValidationRequest:
            assert type(workflow) is ValidationWorkflow
            update = workflow.resume(request, state, knowledge_store=self.knowledge_store)
        elif type(request) is InvestigationRequest:
            assert type(workflow) is InvestigationWorkflow
            update = workflow.resume(request, state, knowledge_store=self.knowledge_store)
        elif type(request) is ImprovementRequest:
            assert type(workflow) is ImprovementWorkflow
            update = workflow.resume(
                request,
                state,
                current_snapshot=binding.current_snapshot,
            )
        else:
            assert type(request) is RSIRequest and type(workflow) is RSIWorkflow
            first = workflow.resume(
                request,
                state,
                current_snapshot=request.declaration.target_snapshot,
            )
            application = first.progress.application_progress
            stored_application = (
                None
                if application is None
                else self.runtime_store.resume(application.state.run.run_id)
            )
            if stored_application is None:
                if binding.current_snapshot != request.declaration.target_snapshot:
                    raise ValueError("RSI currentness advanced without application history")
                update = first
            else:
                observed = self._application_snapshot(
                    request.declaration.target_snapshot,
                    stored_application,
                )
                update = workflow.resume(
                    request,
                    state,
                    current_snapshot=observed,
                    application_state=stored_application,
                )
                if observed != binding.current_snapshot:
                    binding = self.agent_store.update_snapshot(
                        binding.run_id,
                        prior=binding.current_snapshot,
                        current=observed,
                    )
        self._record(update.transitions)
        return binding, update.progress

    @staticmethod
    def _status(
        binding: AgentRunBinding,
        progress: Progress,
        *,
        operation: str,
    ) -> dict[str, Any]:
        state = progress.state
        return response_document(
            operation,
            run_id=binding.run_id,
            state_root=state.root,
            data={
                "workflow": binding.workflow,
                "status": state.status,
                "sequence": state.sequence,
                "terminal": progress.result is not None,
                "pending_action_roots": [item.root for item in state.pending_actions],
                "result_root": None if progress.result is None else progress.result.root,
                "target_snapshot_root": binding.current_snapshot.root,
            },
        )

    def status(self, run_id: str) -> dict[str, Any]:
        binding = self._binding(run_id)
        binding, progress = self._resume(binding)
        return self._status(binding, progress, operation="status")

    def resume(self, run_id: str) -> dict[str, Any]:
        binding = self._binding(run_id)
        binding, progress = self._resume(binding)
        return self._status(binding, progress, operation="resume")

    def next(self, run_id: str) -> dict[str, Any]:
        binding = self._binding(run_id)
        binding, progress = self._resume(binding)
        state = progress.state
        if progress.result is not None:
            raise ValueError("external run is terminal; use outcome")
        if len(state.pending_actions) != 1:
            raise ValueError("external run does not expose exactly one pending action")
        action = state.pending_actions[0]
        capability = binding.admission.binding_for(action.kind)
        evidence_refs = tuple(
            item
            for item in action.input_refs
            if isinstance(item, EvidenceRef) or item.record_type == "evidence"
        )
        return response_document(
            "next",
            run_id=binding.run_id,
            state_root=state.root,
            data={
                "workflow": binding.workflow,
                "action": action.to_dict(),
                "action_root": action.root,
                "target_snapshot": binding.current_snapshot.to_dict(),
                "constraints": [
                    item.to_dict() for item in binding.admission.evaluation_contract.constraints
                ],
                "evidence_refs": [item.to_dict() for item in evidence_refs],
                "capability": capability.to_dict(),
                "expected_result_schema": action_result_schema(action),
            },
        )

    def submit(
        self,
        run_id: str,
        result: ActionResult,
        *,
        authority: str,
        current_snapshot: TargetSnapshot | None = None,
    ) -> dict[str, Any]:
        binding = self._binding(run_id)
        binding, progress = self._resume(binding)
        if progress.result is not None or len(progress.state.pending_actions) != 1:
            raise ValueError("external run does not accept another result")
        action = progress.state.pending_actions[0]
        if type(result) is not ActionResult or result.action != action:
            raise ValueError("submitted result does not match the exact pending action")
        capability = binding.admission.binding_for(action.kind)
        if authority != capability.posture or authority == "unavailable":
            raise ValueError("submission authority does not match the admitted capability")
        observed = binding.current_snapshot if current_snapshot is None else current_snapshot
        if type(observed) is not TargetSnapshot:
            raise TypeError("external submission currentness requires a TargetSnapshot")
        workflow = self._workflow(binding)
        update: Update
        if type(progress) is ValidationProgress:
            assert type(workflow) is ValidationWorkflow
            if observed != binding.current_snapshot:
                raise ValueError("validation submission cannot change target currentness")
            update = workflow.submit(progress, result, knowledge_store=self.knowledge_store)
        elif type(progress) is InvestigationProgress:
            assert type(workflow) is InvestigationWorkflow
            if observed != binding.current_snapshot:
                raise ValueError("investigation submission cannot change target currentness")
            update = workflow.submit(progress, result, knowledge_store=self.knowledge_store)
        elif type(progress) is ImprovementProgress:
            assert type(workflow) is ImprovementWorkflow
            if observed != binding.current_snapshot:
                raise ValueError("improvement submission cannot change target currentness")
            update = workflow.submit(progress, result, current_snapshot=observed)
        else:
            assert type(progress) is RSIProgress and type(workflow) is RSIWorkflow
            update = workflow.submit(
                progress,
                result,
                prior_snapshot=binding.current_snapshot,
                current_snapshot=observed,
                authority=authority,
            )
        self._record(update.transitions)
        if observed != binding.current_snapshot:
            binding = self.agent_store.update_snapshot(
                run_id,
                prior=binding.current_snapshot,
                current=observed,
            )
        return self._status(binding, update.progress, operation="submit")

    def outcome(self, run_id: str) -> dict[str, Any]:
        binding = self._binding(run_id)
        binding, progress = self._resume(binding)
        if progress.result is None:
            raise ValueError("external run has no terminal outcome")
        projection = project_result(progress.result)
        return response_document(
            "outcome",
            run_id=run_id,
            state_root=progress.state.root,
            data={"projection": projection_to_dict(projection)},
        )
