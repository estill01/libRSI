from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from librsi import (
    CapabilityRegistry,
    CapabilityRoute,
    Claim,
    Evidence,
    Hypothesis,
    HypothesisTestResult,
    ImprovementWorkflow,
    InvestigationRequest,
    LibRSI,
    LibRSIRun,
    LocalArtifactStore,
    LocalCommandRunner,
    LocalFilesystemInspector,
    LoggingTransitionSink,
    RSICapabilityError,
    RSIResult,
    RSIWorkflow,
    SQLiteKnowledgeStore,
    SQLiteRuntimeStore,
    ValidationEvidenceBatch,
    ValidationRequest,
    ValidationResult,
    ValidationWorkflow,
    make_validation_evidence_result,
    serialize_record,
    validation_evidence_request_from_action,
)
from librsi.expert import RSIKernel as ExpertKernel
from tests.block14_support import comparison_context
from tests.block15_support import (
    CycleExperimenter,
    CycleReasoner,
    DeterministicCycleProvider,
    hypotheses,
    improvement_request,
)
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import (
    DeterministicGovernanceProvider,
    self_change_registry,
    self_change_request,
)


class RecordingSink:
    def __init__(self) -> None:
        self.transitions = []

    def emit(self, transition) -> None:
        self.transitions.append(transition)


def _support(claim: Claim, snapshot=None) -> tuple[Evidence, Evidence]:
    return tuple(
        Evidence(
            evidence_type="support",
            data={"sample": sample},
            subject_refs=(claim.ref,),
            source_refs=(claim.ref,),
            target_snapshot=snapshot,
            weight=1.0,
        )
        for sample in (1, 2)
    )  # type: ignore[return-value]


def test_for_repo_composes_real_defaults_without_hiding_repo_in_core(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text("value = 1\n")

    with LibRSI.for_repo(tmp_path) as lib:
        assert lib.target is not None and lib.target.kind == "software-repository"
        assert isinstance(lib.runtime_store, SQLiteRuntimeStore)
        assert isinstance(lib.knowledge_store, SQLiteKnowledgeStore)
        assert isinstance(lib.command_runner, LocalCommandRunner)
        assert isinstance(lib.artifact_store, LocalArtifactStore)
        assert isinstance(lib.transition_sink, LoggingTransitionSink)
        assert isinstance(lib.workspace_inspector, LocalFilesystemInspector)
        assert lib.snapshot().state["entry_count"] == 1

    assert (tmp_path / ".librsi" / "runtime.sqlite").is_file()
    assert (tmp_path / ".librsi" / "knowledge.sqlite").is_file()

    generic = LibRSI()
    generic_claim = Claim(statement="A generic process remains bounded")
    result = generic.validate(
        generic_claim,
        evidence=_support(generic_claim),
    )
    assert result.disposition == "supported"


def test_trivial_local_validation_persists_and_logs_canonical_transitions(
    tmp_path: Path,
) -> None:
    (tmp_path / "service.txt").write_text("available")
    sink = RecordingSink()
    with LibRSI.for_repo(tmp_path, transition_sink=sink) as lib:
        claim = lib.claim("The service is available", kind="behavioral")
        snapshot = lib.snapshot()
        result = lib.validate(
            claim,
            validation_id="local-validation",
            target_snapshot=snapshot,
            evidence=_support(claim, snapshot),
        )

        assert isinstance(result, ValidationResult)
        assert result.disposition == "supported"
        assert lib.runtime_store is not None
        persisted = lib.runtime_store.resume("local-validation")
        assert persisted is not None and persisted.status == "completed"
        assert tuple(item.event for item in sink.transitions) == lib.runtime_store.events(
            "local-validation"
        )


def test_facade_step_is_exactly_the_low_level_workflow(tmp_path: Path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite")
    claim = Claim(statement="The transition is canonical")
    request = ValidationRequest.for_claim(validation_id="stepped", claim=claim)
    direct = ValidationWorkflow().start(request)
    lib = LibRSI(runtime_store=store)

    run = lib.start(request)

    assert isinstance(run, LibRSIRun)
    assert run.progress == direct.progress
    action = run.next()
    assert action is not None
    evidence_request = validation_evidence_request_from_action(action)
    envelope = make_validation_evidence_result(
        action=action,
        batch=ValidationEvidenceBatch.collected(
            request=evidence_request,
            evidence=_support(claim),
        ),
    )
    assert run.current_snapshot is None
    with pytest.raises(TypeError, match="ActionResult"):
        run.submit(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact pending action"):
        run.submit(replace(envelope, action=replace(action, action_id="other")))
    with pytest.raises(TypeError, match="TargetSnapshot"):
        run.submit(envelope, current_snapshot=object())  # type: ignore[arg-type]
    expected = ValidationWorkflow().submit(direct.progress, envelope)
    run.submit(envelope)

    assert run.progress == expected.progress
    assert tuple(serialize_record(item) for item in run.transitions) == tuple(
        serialize_record(item) for item in expected.transitions
    )
    assert store.resume("stepped") == run.state
    assert run.next() is None
    store.close()


def test_hypothesis_testing_uses_command_adapter_and_persists_exact_lineage(
    tmp_path: Path,
) -> None:
    (tmp_path / "input.txt").write_text("ready")
    with LibRSI.for_repo(tmp_path) as lib:
        result = lib.test_hypothesis(
            "The local check reports READY",
            experiment_id="local-command-check",
            command=(sys.executable, "-c", "print('READY')"),
            success_criteria={
                "accepted_exit_codes": [0],
                "stdout_contains": ["READY"],
            },
        )

        assert isinstance(result, HypothesisTestResult)
        assert result.evidence.evidence_type == "support"
        assert result.observation.exact_input_root == result.experiment.root
        assert result.hypothesis.ref in result.evidence.subject_refs
        assert result.experiment.ref in result.evidence.source_refs
        assert lib.knowledge_store is not None
        assert lib.knowledge_store.get(result.evidence.root) == result.evidence
        assert lib.knowledge_store.get(result.updated_hypothesis.root) == result.updated_hypothesis


def test_local_components_are_independently_replaceable_and_caller_owned(
    tmp_path: Path,
) -> None:
    runtime = SQLiteRuntimeStore(":memory:")
    knowledge = SQLiteKnowledgeStore(":memory:")
    runner = LocalCommandRunner(allowed_roots=(tmp_path,))
    artifacts = LocalArtifactStore(tmp_path / "alternate-artifacts")
    sink = RecordingSink()
    inspector = LocalFilesystemInspector(tmp_path, ignored_names=())

    lib = LibRSI.local(
        tmp_path,
        runtime_store=runtime,
        knowledge_store=knowledge,
        command_runner=runner,
        artifact_store=artifacts,
        transition_sink=sink,
        workspace_inspector=inspector,
    )

    assert lib.runtime_store is runtime
    assert lib.knowledge_store is knowledge
    assert lib.command_runner is runner
    assert lib.artifact_store is artifacts
    assert lib.transition_sink is sink
    assert lib.workspace_inspector is inspector
    lib.close()
    assert runtime.load("never-started") is None
    assert knowledge.query() == ()
    runtime.close()
    knowledge.close()


def test_investigate_and_improve_delegate_to_existing_workflows() -> None:
    context = comparison_context()
    question = improvement_request(context).question
    reasoner = CycleReasoner()
    experimenter = CycleExperimenter()
    registry = CapabilityRegistry(
        routes=(
            CapabilityRoute("investigation-reason", "reasoner", "automatic"),
            CapabilityRoute("investigation-experiment", "experimenter", "automatic"),
        ),
        implementations=(reasoner, experimenter),
    )
    lib = LibRSI(capability_registry=registry)

    investigation = lib.investigate(
        question,
        target_snapshot=context.baseline_snapshot,
        initial_hypotheses=hypotheses(question),
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )

    assert investigation.disposition == "answered"

    request = improvement_request(context)
    provider = DeterministicCycleProvider(context, (True,))
    improved = LibRSI(improvement_provider=provider).improve(
        request,
        current_snapshot=context.baseline_snapshot,
    )
    assert improved.disposition == "improved"
    assert len(provider.actions) == 1


def test_recurse_facade_preserves_governance_and_application_semantics() -> None:
    context = comparison_context(target_kind="improvement-policy-bundle")
    request = self_change_request(context, activate=True)
    governance = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(context.baseline_snapshot)
    lib = LibRSI(capability_registry=self_change_registry(governance, target))

    result = lib.recurse(request, current_snapshot=context.baseline_snapshot)

    assert isinstance(result, RSIResult)
    assert result.disposition == "verified"
    assert result.governance.disposition == "accepted"
    assert result.application is not None
    assert result.authoritative_snapshot == target.snapshot


def test_managed_methods_stop_at_external_authority_instead_of_stealing_it() -> None:
    request = InvestigationRequest.for_question(
        investigation_id="external-investigation",
        question=LibRSI().question("What explains the observation?"),
    )
    lib = LibRSI(routes=(CapabilityRoute("investigation-reason", "reasoner", "external"),))

    with pytest.raises(RSICapabilityError, match="nonautomatic"):
        lib.investigate(request)

    run = lib.start(request)
    assert run.next() is not None
    assert run.plan.external_actions == (run.next(),)


def test_low_level_expert_and_legacy_exports_remain_reachable() -> None:
    from librsi import RSIKernel

    assert ExpertKernel is RSIKernel
    assert isinstance(RSIKernel(), RSIKernel)


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    (
        ({"kernel": object()}, TypeError, "kernel"),
        (
            {
                "capability_registry": CapabilityRegistry(),
                "routes": (CapabilityRoute("x", "inspector", "automatic"),),
            },
            ValueError,
            "registry or routes",
        ),
        ({"capability_registry": object()}, TypeError, "CapabilityRegistry"),
        ({"runtime_store": object()}, TypeError, "runtime store"),
        ({"knowledge_store": object()}, TypeError, "knowledge store"),
        ({"command_runner": object()}, TypeError, "command runner"),
        ({"artifact_store": object()}, TypeError, "artifact store"),
        ({"transition_sink": object()}, TypeError, "transition sink"),
        ({"workspace_inspector": object()}, TypeError, "workspace inspector"),
        ({"target": object()}, TypeError, "target"),
        ({"layout": object()}, TypeError, "layout"),
        ({"improvement_provider": object()}, TypeError, "improvement provider"),
    ),
)
def test_facade_rejects_invalid_component_composition(kwargs, error, message) -> None:
    with pytest.raises(error, match=message):
        LibRSI(**kwargs)


def test_facade_rejects_invalid_inputs_and_closed_use(tmp_path: Path) -> None:
    lib = LibRSI()

    with pytest.raises(ValueError, match="no configured local target"):
        lib.snapshot()
    with pytest.raises(TypeError, match="public workflow request"):
        lib.start(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Claim or statement"):
        lib.validate(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Question, or prompt"):
        lib.investigate(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ImprovementRequest"):
        lib.improve(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RSIRequest"):
        lib.recurse(object())  # type: ignore[arg-type]
    with pytest.raises(RSICapabilityError, match="ExperimentRunner"):
        lib.test_hypothesis("unsupported", command=("true",), success_criteria={})

    lib.close()
    lib.close()
    with pytest.raises(RuntimeError, match="closed"):
        lib.start(ValidationRequest.for_claim(validation_id="closed", claim=Claim(statement="x")))
    with pytest.raises(RuntimeError, match="closed"), lib:
        pass

    with pytest.raises(ValueError, match="owns its software-repository"):
        LibRSI.for_repo(tmp_path, target_kind="filesystem")


def test_facade_managed_validation_handles_defaults_and_external_authority(tmp_path: Path) -> None:
    (tmp_path / "state.txt").write_text("ready")
    with LibRSI.local(tmp_path) as lib:
        result = lib.validate("No collector is configured")
        assert result.disposition == "inconclusive"
        second = lib.validate("A second claim receives its own run")
        assert second.validation.validation_id != result.validation.validation_id
        with pytest.raises(TypeError, match="Evidence values"):
            lib.validate("bad evidence", evidence=(object(),))  # type: ignore[arg-type]
        with pytest.raises(RSICapabilityError, match="nonautomatic"):
            lib.investigate("No reasoner is configured")

    external = LibRSI(routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),))
    with pytest.raises(RSICapabilityError, match="external action"):
        external.validate("External evidence is required")


def test_hypothesis_facade_accepts_typed_inputs_and_validates_result_lineage(
    tmp_path: Path,
) -> None:
    inspector = LocalFilesystemInspector(tmp_path)
    snapshot = inspector.snapshot(inspector.target())
    runner = LocalCommandRunner(allowed_roots=(tmp_path,))
    lib = LibRSI(command_runner=runner)
    hypothesis = Hypothesis(
        statement="The command succeeds",
        target=snapshot.target,
        predictions=({"command.passed": True},),
    )
    result = lib.test_hypothesis(
        hypothesis,
        command=(sys.executable, "-c", "pass"),
        success_criteria={"accepted_exit_codes": [0]},
        target_snapshot=snapshot,
        cwd=tmp_path,
    )

    assert result.hypothesis is hypothesis
    for field in ("hypothesis", "experiment", "observation", "evidence", "updated_hypothesis"):
        with pytest.raises(TypeError):
            replace(result, **{field: object()})
    with pytest.raises(ValueError, match="another hypothesis"):
        replace(result, experiment=replace(result.experiment, lineage=()))
    with pytest.raises(ValueError, match="another experiment"):
        replace(result, observation=replace(result.observation, exact_input_root="other"))
    with pytest.raises(ValueError, match="exact experiment lineage"):
        replace(result, evidence=replace(result.evidence, subject_refs=()))
    with pytest.raises(ValueError, match="exact evidence lineage"):
        replace(result, updated_hypothesis=replace(result.updated_hypothesis, lineage=()))

    with pytest.raises(TypeError, match="TargetSnapshot"):
        lib.test_hypothesis(
            hypothesis,
            command=("true",),
            success_criteria={},
            target_snapshot=object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="Hypothesis or statement"):
        lib.test_hypothesis(
            object(),  # type: ignore[arg-type]
            command=("true",),
            success_criteria={},
            target_snapshot=snapshot,
        )


def test_facade_close_ignores_noncloseable_owned_resources() -> None:
    LibRSI(_owned_resources=(object(),)).close()


def test_facade_run_rejects_invalid_composition_and_missing_managed_dependencies() -> None:
    validation_request = ValidationRequest.for_claim(
        validation_id="constructor-guards",
        claim=Claim(statement="facade guards remain explicit"),
    )
    validation_update = ValidationWorkflow().start(validation_request)
    base = {
        "workflow": ValidationWorkflow(),
        "progress": validation_update.progress,
        "registry": CapabilityRegistry(),
        "record_transitions": lambda transitions: None,
    }
    invalid = (
        ("workflow", object(), "canonical workflow"),
        ("progress", object(), "canonical progress"),
        ("registry", object(), "CapabilityRegistry"),
        ("record_transitions", object(), "transition recorder"),
        ("current_snapshot", object(), "TargetSnapshot"),
        ("knowledge_store", object(), "KnowledgeStore"),
        ("improvement_provider", object(), "improvement provider"),
    )
    for field, value, message in invalid:
        with pytest.raises(TypeError, match=message):
            LibRSIRun(**(base | {field: value}))

    context = comparison_context()
    improvement = improvement_request(context)
    improvement_update = ImprovementWorkflow().start(
        improvement,
        current_snapshot=context.baseline_snapshot,
    )
    without_provider = LibRSIRun(
        workflow=ImprovementWorkflow(),
        progress=improvement_update.progress,
        registry=CapabilityRegistry(),
        record_transitions=lambda transitions: None,
        current_snapshot=context.baseline_snapshot,
    )
    with pytest.raises(RSICapabilityError, match="ImprovementCycleProvider"):
        without_provider.run()

    without_snapshot = LibRSIRun(
        workflow=ImprovementWorkflow(),
        progress=improvement_update.progress,
        registry=CapabilityRegistry(),
        record_transitions=lambda transitions: None,
        improvement_provider=DeterministicCycleProvider(context, (True,)),
    )
    with pytest.raises(ValueError, match="current snapshot"):
        without_snapshot.run()

    rsi_request = self_change_request(
        comparison_context(target_kind="improvement-policy-bundle"),
        activate=True,
    )
    rsi_workflow = RSIWorkflow(CapabilityRegistry())
    rsi_update = rsi_workflow.start(
        rsi_request,
        current_snapshot=rsi_request.declaration.target_snapshot,
    )
    rsi_without_snapshot = LibRSIRun(
        workflow=rsi_workflow,
        progress=rsi_update.progress,
        registry=CapabilityRegistry(),
        record_transitions=lambda transitions: None,
    )
    with pytest.raises(ValueError, match="current snapshot"):
        rsi_without_snapshot.run()
