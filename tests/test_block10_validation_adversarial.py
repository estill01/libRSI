from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    Action,
    ActionResult,
    Claim,
    EpistemicPolicy,
    Evidence,
    EvidenceRef,
    LinearEvidenceAggregator,
    RecordRef,
    Run,
    RunBudget,
    RuntimeEngine,
    RuntimeFailure,
    TargetRef,
    TargetSnapshot,
    ValidationEvidenceBatch,
    ValidationEvidenceRequest,
    ValidationEvidenceResultValidator,
    ValidationPolicy,
    ValidationProgress,
    ValidationRequest,
    ValidationResult,
    ValidationUpdate,
    ValidationWorkflow,
    classify_validation,
    make_validation_evidence_action,
    make_validation_evidence_failure,
    make_validation_evidence_result,
    validate,
    validation_batch_from_action_result,
    validation_evidence_request_from_action,
)


def _context():
    target = TargetRef(target_id="adversarial-process", kind="process")
    snapshot = TargetSnapshot(target=target, revision="v2", state={"rate": 2})
    claim = Claim(statement="The process is stable", kind="behavioral", target=target)
    validation = ValidationRequest.for_claim(
        validation_id="adversarial-validation",
        claim=claim,
        target_snapshot=snapshot,
        max_evidence_actions=2,
    )
    workflow = ValidationWorkflow()
    progress = workflow.start(validation).progress
    action = progress.state.pending_actions[0]
    gap = validation_evidence_request_from_action(action)
    evidence = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(claim.ref,),
        source_refs=(gap.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )
    batch = ValidationEvidenceBatch.collected(request=gap, evidence=(evidence,))
    return snapshot, claim, validation, workflow, progress, action, gap, evidence, batch


def test_action_codecs_fail_closed_on_wrong_types_shapes_and_lineage() -> None:
    snapshot, claim, validation, _, progress, action, gap, _, batch = _context()
    with pytest.raises(TypeError, match="require a Run"):
        make_validation_evidence_action(run=object(), request=gap)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a ValidationEvidenceRequest"):
        make_validation_evidence_action(run=progress.state.run, request=object())  # type: ignore[arg-type]
    other_run = Run(run_id="other", intent=Claim(statement="Other", kind="fact").ref)
    with pytest.raises(ValueError, match="does not match"):
        make_validation_evidence_action(run=other_run, request=gap)

    with pytest.raises(TypeError, match="requires an Action"):
        validation_evidence_request_from_action(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not a validation"):
        validation_evidence_request_from_action(replace(action, kind="other"))
    with pytest.raises(ValueError, match="only its exact request"):
        validation_evidence_request_from_action(replace(action, payload={"other": {}}))
    with pytest.raises(TypeError, match="must be a mapping"):
        validation_evidence_request_from_action(replace(action, payload={"request": 1}))
    with pytest.raises(TypeError, match="ValidationEvidenceRequest"):
        validation_evidence_request_from_action(
            replace(action, payload={"request": claim.to_dict()})
        )
    with pytest.raises(ValueError, match="exact request lineage"):
        validation_evidence_request_from_action(replace(action, input_refs=()))

    with pytest.raises(TypeError, match="ValidationEvidenceBatch"):
        make_validation_evidence_result(action=action, batch=object())  # type: ignore[arg-type]
    other_validation = ValidationRequest.for_claim(
        validation_id="other", claim=claim, target_snapshot=snapshot
    )
    other_gap = ValidationEvidenceRequest.for_gaps(
        validation=other_validation,
        sequence=1,
        known_evidence_refs=(),
        gaps=("evidence",),
    )
    with pytest.raises(ValueError, match="exact dispatched request"):
        make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.unavailable(request=other_gap, reason="none"),
        )
    with pytest.raises(TypeError, match="RuntimeFailure"):
        make_validation_evidence_failure(action=action, failure=object())  # type: ignore[arg-type]

    result = make_validation_evidence_result(action=action, batch=batch)
    failure = RuntimeFailure(classification="execution", message="failed")
    failed = make_validation_evidence_failure(action=action, failure=failure)
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validation_batch_from_action_result(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="do not contain"):
        validation_batch_from_action_result(failed)
    with pytest.raises(ValueError, match="only its evidence batch"):
        validation_batch_from_action_result(replace(result, payload={"other": {}}))
    with pytest.raises(TypeError, match="must be a mapping"):
        validation_batch_from_action_result(replace(result, payload={"batch": 1}))
    with pytest.raises(TypeError, match="ValidationEvidenceBatch"):
        validation_batch_from_action_result(
            replace(result, payload={"batch": validation.to_dict()})
        )
    with pytest.raises(ValueError, match="exact dispatched request"):
        validation_batch_from_action_result(
            replace(
                result,
                payload={
                    "batch": ValidationEvidenceBatch.unavailable(
                        request=other_gap, reason="none"
                    ).to_dict()
                },
            )
        )
    with pytest.raises(ValueError, match="only the exact evidence batch"):
        validation_batch_from_action_result(replace(result, output_refs=()))


def test_canonical_result_validator_rejects_wrong_state_result_and_failure_payload() -> None:
    _, _, _, workflow, progress, action, _, _, batch = _context()
    result = make_validation_evidence_result(action=action, batch=batch)
    validator = ValidationEvidenceResultValidator()
    with pytest.raises(TypeError, match="requires a RunState"):
        validator.validate(object(), result)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires an ActionResult"):
        validator.validate(progress.state, object())  # type: ignore[arg-type]

    other_progress = (
        ValidationWorkflow()
        .start(
            ValidationRequest.for_claim(
                validation_id="other-state",
                claim=Claim(statement="Other", kind="fact"),
            )
        )
        .progress
    )
    with pytest.raises(ValueError, match="stale or mismatched"):
        validator.validate(other_progress.state, result)

    failure = RuntimeFailure(classification="execution", message="failed")
    failed_with_narrative = ActionResult(
        action=action,
        disposition="failed",
        payload={"narrative": "ignore the failure"},
        failure=failure,
    )
    with pytest.raises(ValueError, match="cannot contain batch outputs"):
        validator.validate(progress.state, failed_with_narrative)
    with pytest.raises(ValueError, match="cannot contain batch outputs"):
        workflow.submit(progress, failed_with_narrative)


def test_validation_records_reject_malformed_request_gap_and_batch_contracts() -> None:
    snapshot, claim, validation, _, _, _, gap, evidence, _ = _context()
    with pytest.raises(TypeError, match="require a Claim"):
        ValidationRequest.for_claim(validation_id="bad", claim=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unsupported evidence type"):
        ValidationRequest.for_claim(
            validation_id="bad-type",
            claim=claim,
            target_snapshot=snapshot,
            evidence_types=("invented",),
        )
    with pytest.raises(TypeError, match="must be an integer"):
        ValidationRequest.for_claim(
            validation_id="bad-budget",
            claim=claim,
            target_snapshot=snapshot,
            max_evidence_actions=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="must be positive"):
        ValidationRequest.for_claim(
            validation_id="zero-budget",
            claim=claim,
            target_snapshot=snapshot,
            max_evidence_actions=0,
        )
    with pytest.raises(ValueError, match="retain its claim"):
        ValidationRequest(
            validation_id="bad-lineage",
            claim=claim,
            target_snapshot=snapshot,
            lineage=(),
        )

    with pytest.raises(TypeError, match="ValidationRequest"):
        ValidationEvidenceRequest(
            validation=object(),  # type: ignore[arg-type]
            sequence=1,
            gaps=("evidence",),
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        ValidationEvidenceRequest.for_gaps(
            validation=validation,
            sequence=1,
            known_evidence_refs=(),
            gaps=(),
        )
    with pytest.raises(ValueError, match="must be unique"):
        ValidationEvidenceRequest.for_gaps(
            validation=validation,
            sequence=1,
            known_evidence_refs=(),
            gaps=("evidence", "evidence"),
        )
    with pytest.raises(TypeError, match="EvidenceRef"):
        ValidationEvidenceRequest.for_gaps(
            validation=validation,
            sequence=1,
            known_evidence_refs=(RecordRef("claim", "a" * 64),),  # type: ignore[arg-type]
            gaps=("evidence",),
        )
    with pytest.raises(ValueError, match="retain validation"):
        ValidationEvidenceRequest(
            validation=validation,
            sequence=1,
            gaps=("evidence",),
            lineage=(),
        )

    with pytest.raises(TypeError, match="exact request"):
        ValidationEvidenceBatch(
            request=object(),  # type: ignore[arg-type]
            disposition="unavailable",
            reason="none",
        )
    with pytest.raises(ValueError, match="unsupported evidence batch"):
        ValidationEvidenceBatch(request=gap, disposition="invented", lineage=gap.lineage)
    with pytest.raises(ValueError, match="cannot contain an unavailable reason"):
        ValidationEvidenceBatch(
            request=gap,
            disposition="collected",
            evidence=(evidence,),
            reason="none",
            lineage=(gap.ref, *gap.lineage, evidence.ref),
        )
    with pytest.raises(ValueError, match="cannot contain evidence"):
        ValidationEvidenceBatch(
            request=gap,
            disposition="unavailable",
            evidence=(evidence,),
            reason="none",
            lineage=(gap.ref, *gap.lineage, evidence.ref),
        )
    with pytest.raises(ValueError, match="retain request"):
        ValidationEvidenceBatch(
            request=gap,
            disposition="unavailable",
            reason="none",
            lineage=(),
        )


def test_validation_records_reject_wrong_evidence_and_result_authority() -> None:
    snapshot, claim, validation, _, progress, _, gap, evidence, _ = _context()
    other_claim = Claim(statement="Other", kind="fact", target=snapshot.target)
    wrong_subject = replace(evidence, subject_refs=(other_claim.ref,))
    with pytest.raises(ValueError, match="exact claim"):
        ValidationEvidenceBatch.collected(request=gap, evidence=(wrong_subject,))
    restricted = ValidationRequest.for_claim(
        validation_id="support-only",
        claim=claim,
        target_snapshot=snapshot,
        evidence_types=("support",),
    )
    restricted_gap = ValidationEvidenceRequest.for_gaps(
        validation=restricted,
        sequence=1,
        known_evidence_refs=(),
        gaps=("support",),
    )
    counterexample = replace(evidence, evidence_type="counterexample")
    with pytest.raises(ValueError, match="not accepted"):
        ValidationEvidenceBatch.collected(
            request=restricted_gap,
            evidence=(counterexample,),
        )
    with pytest.raises(ValueError, match="explicit weight"):
        ValidationEvidenceBatch.collected(
            request=gap,
            evidence=(replace(evidence, weight=None),),
        )
    with pytest.raises(ValueError, match="must be unique"):
        ValidationEvidenceBatch.collected(request=gap, evidence=(evidence, evidence))

    with pytest.raises(TypeError, match="BeliefState"):
        classify_validation(object(), ())  # type: ignore[arg-type]
    belief = ValidationPolicy().belief(validation, ())
    with pytest.raises(TypeError, match="ValidationRequest"):
        ValidationResult(
            validation=object(),  # type: ignore[arg-type]
            run=progress.state.run.ref,
            disposition="inconclusive",
            belief=belief,
            unresolved=("unknown",),
        )
    with pytest.raises(TypeError, match="exact Run"):
        ValidationResult(
            validation=validation,
            run=claim.ref,
            disposition="inconclusive",
            belief=belief,
            unresolved=("unknown",),
            lineage=(validation.ref, claim.ref, belief.ref),
        )
    with pytest.raises(ValueError, match="unsupported validation disposition"):
        ValidationResult(
            validation=validation,
            run=progress.state.run.ref,
            disposition="invented",
            belief=belief,
        )
    with pytest.raises(TypeError, match="BeliefState"):
        ValidationResult(
            validation=validation,
            run=progress.state.run.ref,
            disposition="inconclusive",
            belief=object(),  # type: ignore[arg-type]
        )


def test_workflow_public_boundaries_reject_invalid_hosts_and_inputs() -> None:
    snapshot, claim, validation, workflow, progress, action, _, evidence, _ = _context()
    with pytest.raises(TypeError, match="ValidationPolicy"):
        ValidationWorkflow(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        ValidationPolicy(EpistemicPolicy(LinearEvidenceAggregator(support_scale=0.3)))

    class _InterventionPolicy(ValidationPolicy):
        def gaps(
            self, belief: object, evidence: object
        ) -> tuple[str, ...]:  # pragma: no cover - construction must fail first
            return ("generate and apply an intervention",)

    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        _InterventionPolicy()

    class _EqualitySpoofAggregator:
        def __eq__(self, other: object) -> bool:
            return True

        def aggregate(self, **kwargs: object) -> object:  # pragma: no cover
            raise AssertionError("a spoofed aggregator must never execute")

    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        ValidationPolicy(EpistemicPolicy(_EqualitySpoofAggregator()))  # type: ignore[arg-type]

    external_policy = ValidationPolicy()
    with pytest.raises(AttributeError):
        object.__setattr__(external_policy, "gaps", lambda *_: ("apply an intervention",))

    mutated_before = ValidationPolicy()
    object.__setattr__(
        mutated_before,
        "epistemics",
        EpistemicPolicy(LinearEvidenceAggregator(support_scale=0.3)),
    )
    with pytest.raises(ValueError, match="versioned semantic policy contract"):
        ValidationWorkflow(mutated_before)

    mutable_after = ValidationPolicy()
    isolated_workflow = ValidationWorkflow(mutable_after)
    object.__setattr__(
        mutable_after,
        "epistemics",
        EpistemicPolicy(LinearEvidenceAggregator(support_scale=0.3)),
    )
    isolated_progress = isolated_workflow.start(validation).progress
    isolated_gap = validation_evidence_request_from_action(
        isolated_progress.state.pending_actions[0]
    )
    assert isolated_gap.gaps == ("obtain current substantive evidence for the exact claim",)

    forged_policy = object.__new__(_InterventionPolicy)
    object.__setattr__(forged_policy, "epistemics", EpistemicPolicy())
    with pytest.raises(TypeError, match="require a ValidationPolicy"):
        ValidationWorkflow(forged_policy)

    with pytest.raises(TypeError, match="ValidationRequest"):
        workflow.start(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="implement KnowledgeStore"):
        workflow.start(validation, knowledge_store=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ValidationProgress"):
        workflow.submit(object(), object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exact pending action"):
        workflow.submit(
            progress,
            ActionResult(
                action=replace(action, action_id="other"),
                disposition="succeeded",
            ),
        )
    with pytest.raises(TypeError, match="ValidationProgress"):
        workflow.step(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ValidationRequest"):
        workflow.resume(object(), progress.state)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="RunState"):
        workflow.resume(validation, object())  # type: ignore[arg-type]
    active = RuntimeEngine.start(progress.state.run).state
    resumed = workflow.resume(validation, active)
    assert resumed.progress == progress
    assert len(resumed.transitions) == 1

    with pytest.raises(TypeError, match="requires a Claim"):
        validate(claim=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TargetSnapshot"):
        validate(claim=claim, target_snapshot=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be a sequence"):
        validate(claim=claim, target_snapshot=snapshot, evidence="evidence")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="contain Evidence"):
        validate(claim=claim, target_snapshot=snapshot, evidence=(object(),))  # type: ignore[arg-type]

    class _Experimenter:
        def experiment(self, requested: Action) -> ActionResult:
            return make_validation_evidence_failure(
                action=requested,
                failure=RuntimeFailure(classification="execution", message="none"),
            )

    with pytest.raises(ValueError, match="explicit evidence or an Experimenter"):
        validate(
            claim=claim,
            target_snapshot=snapshot,
            evidence=(evidence,),
            experimenter=_Experimenter(),
        )


def test_projection_records_reject_incomplete_provenance_and_transition_types() -> None:
    _, _, _, _, progress, _, _, evidence, _ = _context()
    with pytest.raises(ValueError, match="provenance is incomplete"):
        ValidationProgress(
            validation=progress.validation,
            state=progress.state,
            belief=ValidationPolicy().belief(progress.validation, (evidence,)),
            evidence=(evidence,),
            reused_evidence_refs=(),
            gathered_evidence_refs=(),
        )
    with pytest.raises(TypeError, match="ValidationProgress"):
        ValidationUpdate(progress=object(), transitions=())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Transition values"):
        ValidationUpdate(progress=progress, transitions=(object(),))  # type: ignore[arg-type]


def test_submit_reconciles_evidence_origins_and_policy_frontier_before_mutation() -> None:
    snapshot, claim, validation, workflow, progress, action, gap, _, batch = _context()
    injected = Evidence(
        evidence_type="support",
        data={"injected": True},
        subject_refs=(claim.ref,),
        source_refs=(gap.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )
    injected_ref = EvidenceRef.from_evidence(injected)
    belief = ValidationPolicy().belief(validation, (injected,))
    result = make_validation_evidence_result(action=action, batch=batch)

    class _CountingExperimenter:
        def __init__(self) -> None:
            self.calls: list[Action] = []

        def experiment(self, requested: Action) -> ActionResult:
            self.calls.append(requested)
            return result

    for reused, gathered in (((injected_ref,), ()), ((), (injected_ref,))):
        forged = ValidationProgress(
            validation=validation,
            state=progress.state,
            belief=belief,
            evidence=(injected,),
            reused_evidence_refs=reused,
            gathered_evidence_refs=gathered,
        )
        with pytest.raises(ValueError, match="canonical persisted frontier"):
            workflow.submit(forged, result)
        experimenter = _CountingExperimenter()
        with pytest.raises(ValueError, match="canonical persisted frontier"):
            workflow.run_managed(forged, experimenter)
        assert experimenter.calls == []

    active = RuntimeEngine.start(validation.canonical_run()).state
    intervention_gap = ValidationEvidenceRequest.for_gaps(
        validation=validation,
        sequence=1,
        known_evidence_refs=(),
        gaps=("generate and apply an intervention",),
    )
    intervention_action = make_validation_evidence_action(
        run=active.run,
        request=intervention_gap,
    )
    intervention_state = RuntimeEngine.request(active, intervention_action).state
    intervention_progress = ValidationProgress(
        validation=validation,
        state=intervention_state,
        belief=ValidationPolicy().belief(validation, ()),
        evidence=(),
        reused_evidence_refs=(),
        gathered_evidence_refs=(),
    )
    intervention_evidence = replace(
        injected,
        source_refs=(intervention_gap.ref,),
    )
    with pytest.raises(ValueError, match="not policy-derived"):
        workflow.submit(
            intervention_progress,
            make_validation_evidence_result(
                action=intervention_action,
                batch=ValidationEvidenceBatch.collected(
                    request=intervention_gap,
                    evidence=(intervention_evidence,),
                ),
            ),
        )
    experimenter = _CountingExperimenter()
    with pytest.raises(ValueError, match="not policy-derived"):
        workflow.run_managed(intervention_progress, experimenter)
    assert experimenter.calls == []


def test_submit_rejects_drifted_run_budget_before_runtime_mutation() -> None:
    snapshot, claim, validation, workflow, _, _, _, evidence, _ = _context()
    drifted_run = Run(
        run_id=validation.validation_id,
        intent=validation.claim.ref,
        target_snapshot=validation.target_snapshot,
        budget=RunBudget(max_actions=99, max_failures=99, max_retries=0),
        lineage=(validation.ref,),
    )
    active = RuntimeEngine.start(drifted_run).state
    gap = ValidationEvidenceRequest.for_gaps(
        validation=validation,
        sequence=1,
        known_evidence_refs=(),
        gaps=("obtain current substantive evidence for the exact claim",),
    )
    action = make_validation_evidence_action(run=drifted_run, request=gap)
    waiting = RuntimeEngine.request(active, action).state
    progress = ValidationProgress(
        validation=validation,
        state=waiting,
        belief=ValidationPolicy().belief(validation, ()),
        evidence=(),
        reused_evidence_refs=(),
        gathered_evidence_refs=(),
    )
    batch = ValidationEvidenceBatch.collected(
        request=gap,
        evidence=(replace(evidence, source_refs=(gap.ref,)),),
    )
    with pytest.raises(ValueError, match="run envelope has drifted"):
        workflow.submit(
            progress,
            make_validation_evidence_result(action=action, batch=batch),
        )

    class _CountingExperimenter:
        def __init__(self) -> None:
            self.calls: list[Action] = []

        def experiment(self, requested: Action) -> ActionResult:
            self.calls.append(requested)
            return make_validation_evidence_result(action=action, batch=batch)

    experimenter = _CountingExperimenter()
    with pytest.raises(ValueError, match="run envelope has drifted"):
        workflow.run_managed(progress, experimenter)
    assert experimenter.calls == []
