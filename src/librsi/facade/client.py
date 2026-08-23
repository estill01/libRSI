"""High-level Python composition over canonical libRSI workflows and adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..capabilities import CapabilityRegistry, CapabilityRoute
from ..errors import RSICapabilityError
from ..experiments import ExperimentPolicy
from ..hypotheses import HypothesisPolicy
from ..improvement import (
    ImprovementCycleProvider,
    ImprovementRequest,
    ImprovementResult,
    ImprovementWorkflow,
)
from ..investigation import (
    InvestigationRequest,
    InvestigationResult,
    InvestigationWorkflow,
)
from ..kernel import RSIKernel
from ..knowledge import KnowledgeStore, KnowledgeWrite
from ..local import (
    ArtifactStore,
    LocalArtifactStore,
    LocalCommandRunner,
    LocalFilesystemInspector,
    LocalLayout,
    LoggingTransitionSink,
    TransitionSink,
    WorkspaceInspector,
    emit_transitions,
)
from ..ports import ExperimentRunner
from ..records import Claim, Evidence, Hypothesis, Question, TargetRef, TargetSnapshot
from ..rsi import RSIRequest, RSIResult, RSIWorkflow
from ..runtime import RuntimeStore, Transition, persist_transitions
from ..runtime.sqlite import SQLiteRuntimeStore
from ..sqlite_knowledge import SQLiteKnowledgeStore
from ..validation import (
    ValidationEvidenceBatch,
    ValidationRequest,
    ValidationResult,
    ValidationWorkflow,
    make_validation_evidence_result,
    validation_evidence_request_from_action,
)
from .records import HypothesisTestResult
from .run import FacadeUpdate, LibRSIRun

WorkflowRequest = ValidationRequest | InvestigationRequest | ImprovementRequest | RSIRequest


class LibRSI:
    """Batteries-included when requested, fully replaceable by construction."""

    def __init__(
        self,
        *,
        kernel: RSIKernel | None = None,
        capability_registry: CapabilityRegistry | None = None,
        routes: Sequence[CapabilityRoute] = (),
        capabilities: Sequence[object] = (),
        runtime_store: RuntimeStore | None = None,
        knowledge_store: KnowledgeStore | None = None,
        command_runner: ExperimentRunner | None = None,
        artifact_store: ArtifactStore | None = None,
        transition_sink: TransitionSink | None = None,
        workspace_inspector: WorkspaceInspector | None = None,
        target: TargetRef | None = None,
        layout: LocalLayout | None = None,
        improvement_provider: ImprovementCycleProvider | None = None,
        _owned_resources: Sequence[object] = (),
    ) -> None:
        if kernel is not None and not isinstance(kernel, RSIKernel):
            raise TypeError("LibRSI kernel must be an RSIKernel")
        if capability_registry is not None and (routes or capabilities):
            raise ValueError("supply a capability registry or routes/capabilities, not both")
        registry = (
            CapabilityRegistry(routes=routes, implementations=capabilities)
            if capability_registry is None
            else capability_registry
        )
        if not isinstance(registry, CapabilityRegistry):
            raise TypeError("LibRSI requires a CapabilityRegistry")
        if runtime_store is not None and not isinstance(runtime_store, RuntimeStore):
            raise TypeError("LibRSI runtime store must implement RuntimeStore")
        if knowledge_store is not None and not isinstance(knowledge_store, KnowledgeStore):
            raise TypeError("LibRSI knowledge store must implement KnowledgeStore")
        if command_runner is not None and not isinstance(command_runner, ExperimentRunner):
            raise TypeError("LibRSI command runner must implement ExperimentRunner")
        if artifact_store is not None and not isinstance(artifact_store, ArtifactStore):
            raise TypeError("LibRSI artifact store must implement ArtifactStore")
        if transition_sink is not None and not isinstance(transition_sink, TransitionSink):
            raise TypeError("LibRSI transition sink must implement TransitionSink")
        if workspace_inspector is not None and not isinstance(
            workspace_inspector, WorkspaceInspector
        ):
            raise TypeError("LibRSI workspace inspector must implement WorkspaceInspector")
        if target is not None and not isinstance(target, TargetRef):
            raise TypeError("LibRSI target must be a TargetRef")
        if layout is not None and not isinstance(layout, LocalLayout):
            raise TypeError("LibRSI layout must be a LocalLayout")
        if improvement_provider is not None and not isinstance(
            improvement_provider, ImprovementCycleProvider
        ):
            raise TypeError("LibRSI improvement provider is invalid")
        self.kernel = RSIKernel() if kernel is None else kernel
        self.capability_registry = registry
        self.runtime_store = runtime_store
        self.knowledge_store = knowledge_store
        self.command_runner = command_runner
        self.artifact_store = artifact_store
        self.transition_sink = transition_sink
        self.workspace_inspector = workspace_inspector
        self.target = target
        self.layout = layout
        self.improvement_provider = improvement_provider
        self._owned_resources = tuple(_owned_resources)
        self._closed = False

    @classmethod
    def local(
        cls,
        workspace: str | Path = ".",
        *,
        data_directory: str | Path | None = None,
        target_id: str | None = None,
        target_kind: str = "filesystem",
        kernel: RSIKernel | None = None,
        capability_registry: CapabilityRegistry | None = None,
        routes: Sequence[CapabilityRoute] = (),
        capabilities: Sequence[object] = (),
        runtime_store: RuntimeStore | None = None,
        knowledge_store: KnowledgeStore | None = None,
        command_runner: ExperimentRunner | None = None,
        artifact_store: ArtifactStore | None = None,
        transition_sink: TransitionSink | None = None,
        workspace_inspector: WorkspaceInspector | None = None,
        improvement_provider: ImprovementCycleProvider | None = None,
    ) -> LibRSI:
        """Compose zero-service local defaults without making any one mandatory."""

        layout = LocalLayout.create(workspace, data_directory=data_directory)
        inspector = (
            LocalFilesystemInspector(layout.workspace, ignored_paths=(layout.data_directory,))
            if workspace_inspector is None
            else workspace_inspector
        )
        local_target = inspector.target(target_id=target_id, kind=target_kind)
        owned: list[object] = []
        if runtime_store is None:
            runtime_store = SQLiteRuntimeStore(layout.runtime_database)
            owned.append(runtime_store)
        if knowledge_store is None:
            knowledge_store = SQLiteKnowledgeStore(layout.knowledge_database)
            owned.append(knowledge_store)
        if command_runner is None:
            command_runner = LocalCommandRunner(allowed_roots=(layout.workspace,))
        if artifact_store is None:
            artifact_store = LocalArtifactStore(layout.artifact_directory)
        if transition_sink is None:
            transition_sink = LoggingTransitionSink()
        return cls(
            kernel=kernel,
            capability_registry=capability_registry,
            routes=routes,
            capabilities=capabilities,
            runtime_store=runtime_store,
            knowledge_store=knowledge_store,
            command_runner=command_runner,
            artifact_store=artifact_store,
            transition_sink=transition_sink,
            workspace_inspector=inspector,
            target=local_target,
            layout=layout,
            improvement_provider=improvement_provider,
            _owned_resources=owned,
        )

    @classmethod
    def for_repo(cls, repository: str | Path = ".", **kwargs: Any) -> LibRSI:
        """Confine repository convenience to an explicitly software-shaped target."""

        if "target_kind" in kwargs:
            raise ValueError("for_repo owns its software-repository target kind")
        return cls.local(repository, target_kind="software-repository", **kwargs)

    def snapshot(self) -> TargetSnapshot:
        if self.workspace_inspector is None or self.target is None:
            raise ValueError("this LibRSI instance has no configured local target inspector")
        return self.workspace_inspector.snapshot(self.target)

    def claim(self, statement: str, *, kind: str = "claim") -> Claim:
        return Claim(statement=statement, kind=kind, target=self.target)

    def question(self, prompt: str) -> Question:
        return Question(prompt=prompt, target=self.target)

    def _record(self, transitions: Sequence[Transition]) -> None:
        items = tuple(transitions)
        if self.runtime_store is not None:
            persist_transitions(self.runtime_store, items)
        if self.transition_sink is not None:
            emit_transitions(self.transition_sink, items)

    def start(
        self,
        request: WorkflowRequest,
        *,
        current_snapshot: TargetSnapshot | None = None,
        improvement_provider: ImprovementCycleProvider | None = None,
    ) -> LibRSIRun:
        """Start one canonical workflow and return its external/managed run handle."""

        if self._closed:
            raise RuntimeError("LibRSI is closed")
        provider = (
            self.improvement_provider if improvement_provider is None else improvement_provider
        )
        if isinstance(request, ValidationRequest):
            workflow: ValidationWorkflow | InvestigationWorkflow | ImprovementWorkflow | RSIWorkflow
            workflow = ValidationWorkflow()
            update: FacadeUpdate = workflow.start(request, knowledge_store=self.knowledge_store)
            observed = request.target_snapshot
        elif isinstance(request, InvestigationRequest):
            workflow = InvestigationWorkflow()
            update = workflow.start(request, knowledge_store=self.knowledge_store)
            observed = request.target_snapshot
        elif isinstance(request, ImprovementRequest):
            workflow = ImprovementWorkflow()
            observed = request.baseline if current_snapshot is None else current_snapshot
            update = workflow.start(request, current_snapshot=observed)
        elif isinstance(request, RSIRequest):
            workflow = RSIWorkflow(self.capability_registry)
            observed = (
                request.declaration.target_snapshot
                if current_snapshot is None
                else current_snapshot
            )
            update = workflow.start(request, current_snapshot=observed)
        else:
            raise TypeError("LibRSI.start requires a public workflow request")
        self._record(update.transitions)
        return LibRSIRun(
            workflow=workflow,
            progress=update.progress,
            registry=self.capability_registry,
            record_transitions=self._record,
            knowledge_store=self.knowledge_store,
            current_snapshot=observed,
            improvement_provider=provider,
        )

    def validate(
        self,
        claim: Claim | str,
        *,
        target_snapshot: TargetSnapshot | None = None,
        validation_id: str | None = None,
        evidence: Sequence[Evidence] = (),
        max_evidence_actions: int = 1,
    ) -> ValidationResult:
        """Validate a claim through the same stepped workflow used by external hosts."""

        canonical_claim = self.claim(claim) if isinstance(claim, str) else claim
        if not isinstance(canonical_claim, Claim):
            raise TypeError("LibRSI.validate requires a Claim or statement")
        snapshot = target_snapshot
        if snapshot is None and canonical_claim.target is not None and self.target is not None:
            snapshot = self.snapshot()
        supplied = tuple(evidence)
        if any(not isinstance(item, Evidence) for item in supplied):
            raise TypeError("LibRSI.validate evidence must contain Evidence values")
        resolved_validation_id = validation_id or (
            f"validation-{canonical_claim.root[:12]}-"
            f"{snapshot.root[:12] if snapshot is not None else 'unbound'}"
        )
        request = ValidationRequest.for_claim(
            validation_id=resolved_validation_id,
            claim=canonical_claim,
            target_snapshot=snapshot,
            max_evidence_actions=max_evidence_actions,
        )
        run = self.start(request)
        if supplied and not run.terminal:
            action = run.next()
            assert action is not None
            evidence_request = validation_evidence_request_from_action(action)
            run.submit(
                make_validation_evidence_result(
                    action=action,
                    batch=ValidationEvidenceBatch.collected(
                        request=evidence_request,
                        evidence=supplied,
                    ),
                )
            )
        elif not supplied:
            run.run()
        while not run.terminal:
            resolution = run.plan.resolutions[0]
            if resolution.posture not in {"unavailable", "automatic"}:
                raise RSICapabilityError(
                    "managed validation reached an external action; use LibRSI.start"
                )
            action = run.next()
            assert action is not None
            evidence_request = validation_evidence_request_from_action(action)
            run.submit(
                make_validation_evidence_result(
                    action=action,
                    batch=ValidationEvidenceBatch.unavailable(
                        request=evidence_request,
                        reason="no additional evidence collector was supplied",
                    ),
                )
            )
        result = run.result
        assert isinstance(result, ValidationResult)
        return result

    def investigate(
        self,
        question: InvestigationRequest | Question | str,
        *,
        target_snapshot: TargetSnapshot | None = None,
        investigation_id: str | None = None,
        initial_hypotheses: Sequence[Hypothesis] = (),
        portfolio_mode: str = "parallel",
        max_hypotheses: int = 4,
        max_experiments: int = 6,
        max_redesigns_per_hypothesis: int = 1,
    ) -> InvestigationResult:
        """Run configured automatic investigation capabilities to a result."""

        if isinstance(question, InvestigationRequest):
            request = question
        else:
            canonical = self.question(question) if isinstance(question, str) else question
            if not isinstance(canonical, Question):
                raise TypeError("LibRSI.investigate requires a request, Question, or prompt")
            snapshot = target_snapshot
            if snapshot is None and canonical.target is not None and self.target is not None:
                snapshot = self.snapshot()
            resolved_investigation_id = investigation_id or (
                f"investigation-{canonical.root[:12]}-"
                f"{snapshot.root[:12] if snapshot is not None else 'unbound'}"
            )
            request = InvestigationRequest.for_question(
                investigation_id=resolved_investigation_id,
                question=canonical,
                target_snapshot=snapshot,
                initial_hypotheses=initial_hypotheses,
                portfolio_mode=portfolio_mode,
                max_hypotheses=max_hypotheses,
                max_experiments=max_experiments,
                max_redesigns_per_hypothesis=max_redesigns_per_hypothesis,
            )
        run = self.start(request).run()
        if not run.terminal:
            raise RSICapabilityError(
                "managed investigation reached a nonautomatic action; use LibRSI.start"
            )
        result = run.result
        assert isinstance(result, InvestigationResult)
        return result

    def improve(
        self,
        request: ImprovementRequest,
        *,
        current_snapshot: TargetSnapshot | None = None,
        provider: ImprovementCycleProvider | None = None,
    ) -> ImprovementResult:
        if not isinstance(request, ImprovementRequest):
            raise TypeError("LibRSI.improve requires an ImprovementRequest")
        run = self.start(
            request,
            current_snapshot=current_snapshot,
            improvement_provider=provider,
        ).run()
        result = run.result
        if not isinstance(result, ImprovementResult):
            raise RuntimeError("managed improvement ended without a result")
        return result

    def recurse(
        self,
        request: RSIRequest,
        *,
        current_snapshot: TargetSnapshot | None = None,
    ) -> RSIResult | LibRSIRun:
        if not isinstance(request, RSIRequest):
            raise TypeError("LibRSI.recurse requires an RSIRequest")
        run = self.start(request, current_snapshot=current_snapshot).run()
        return run.result if isinstance(run.result, RSIResult) else run

    def test_hypothesis(
        self,
        hypothesis: Hypothesis | str,
        *,
        command: Sequence[str],
        success_criteria: Mapping[str, Any],
        target_snapshot: TargetSnapshot | None = None,
        experiment_id: str = "hypothesis-test",
        cwd: str | Path | None = None,
        design: Mapping[str, Any] | None = None,
        causal_model: Mapping[str, Any] | None = None,
        predictions: Sequence[Mapping[str, Any]] = ({"command.passed": True},),
        timeout_seconds: int = 60,
    ) -> HypothesisTestResult:
        """Execute the canonical hypothesis -> command -> evidence path locally."""

        if self.command_runner is None:
            raise RSICapabilityError("hypothesis testing requires an ExperimentRunner")
        snapshot = self.snapshot() if target_snapshot is None else target_snapshot
        if not isinstance(snapshot, TargetSnapshot):
            raise TypeError("hypothesis testing requires a TargetSnapshot")
        if isinstance(hypothesis, str):
            canonical_hypothesis = HypothesisPolicy().create(
                target=snapshot.target,
                statement=hypothesis,
                causal_model={} if causal_model is None else causal_model,
                predictions=predictions,
            )
        else:
            canonical_hypothesis = hypothesis
        if not isinstance(canonical_hypothesis, Hypothesis):
            raise TypeError("hypothesis testing requires a Hypothesis or statement")
        working_directory = (
            self.layout.workspace
            if cwd is None and self.layout is not None
            else Path.cwd()
            if cwd is None
            else Path(cwd)
        )
        policy: ExperimentPolicy = self.kernel.experiments
        experiment = policy.design_command(
            experiment_id=experiment_id,
            hypothesis=canonical_hypothesis,
            target_snapshot=snapshot,
            design={"kind": "local command"} if design is None else design,
            success_criteria=success_criteria,
            command=command,
            cwd=str(working_directory.expanduser().resolve()),
        )
        observation = self.command_runner.run(
            policy.prepare_command(experiment),
            timeout_seconds=timeout_seconds,
        )
        evidence = policy.evaluate_command(spec=experiment, observation=observation)
        updated = self.kernel.hypotheses.apply(
            hypothesis=canonical_hypothesis,
            evidence=evidence,
        )
        if self.knowledge_store is not None:
            self.knowledge_store.put_many(
                tuple(
                    KnowledgeWrite(record=item)
                    for item in (
                        snapshot.target,
                        snapshot,
                        canonical_hypothesis,
                        experiment,
                        evidence,
                        updated,
                    )
                )
            )
        return HypothesisTestResult(
            hypothesis=canonical_hypothesis,
            experiment=experiment,
            observation=observation,
            evidence=evidence,
            updated_hypothesis=updated,
        )

    def close(self) -> None:
        if self._closed:
            return
        for resource in reversed(self._owned_resources):
            close = getattr(resource, "close", None)
            if callable(close):
                close()
        self._closed = True

    def __enter__(self) -> LibRSI:
        if self._closed:
            raise RuntimeError("LibRSI is closed")
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
