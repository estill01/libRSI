from __future__ import annotations

from pathlib import Path

import pytest

from librsi import (
    Claim,
    Evidence,
    SQLiteKnowledgeStore,
    StoredKnowledge,
    TargetRef,
    TargetSnapshot,
    ValidationEvidenceBatch,
    ValidationRequest,
    ValidationWorkflow,
    make_validation_evidence_result,
    validate,
    validation_evidence_request_from_action,
)


def _target_context():
    target = TargetRef(target_id="queue-service", kind="service")
    stale = TargetSnapshot(target=target, revision="v1", state={"workers": 1})
    current = TargetSnapshot(target=target, revision="v2", state={"workers": 2})
    claim = Claim(
        statement="Queue latency stays below the service bound",
        kind="behavioral",
        target=target,
    )
    return target, stale, current, claim


def _support(claim: Claim, snapshot: TargetSnapshot, index: int) -> Evidence:
    return Evidence(
        evidence_type="support",
        data={"sample": index, "latency_ms": 12 - index},
        subject_refs=(claim.ref,),
        source_refs=(snapshot.ref,),
        target_snapshot=snapshot,
        weight=1.0,
    )


def test_sufficient_current_knowledge_avoids_execution_and_returns_provenance(
    tmp_path: Path,
) -> None:
    _, stale, current, claim = _target_context()
    stale_evidence = (_support(claim, stale, 1), _support(claim, stale, 2))
    current_evidence = (_support(claim, current, 3), _support(claim, current, 4))
    with SQLiteKnowledgeStore(tmp_path / "knowledge.sqlite") as store:
        for item in (*stale_evidence, *current_evidence):
            store.put(item, source_run_id="prior-validation")
        request = ValidationRequest.for_claim(
            validation_id="reuse-current",
            claim=claim,
            target_snapshot=current,
        )
        update = ValidationWorkflow().start(request, knowledge_store=store)

        assert update.progress.result is not None
        assert update.progress.result.disposition == "supported"
        assert update.progress.state.status == "completed"
        assert update.progress.state.actions == ()
        assert len(update.transitions) == 2
        assert set(update.progress.result.reused_evidence_refs) == {
            item.evidence_ref for item in current_evidence
        }
        assert not update.progress.result.gathered_evidence_refs
        resumed = ValidationWorkflow().resume(
            request,
            update.transitions[0].next_state,
            knowledge_store=store,
        )
        assert resumed.progress == update.progress
        assert resumed.transitions == (update.transitions[1],)
        stored = store.put(update.progress.result, source_run_id="reuse-current")
        assert stored.record == update.progress.result


def test_stale_knowledge_is_not_current_and_emits_one_exact_gap_action(tmp_path: Path) -> None:
    _, stale, current, claim = _target_context()
    with SQLiteKnowledgeStore(tmp_path / "stale.sqlite") as store:
        store.put(_support(claim, stale, 1))
        store.put(_support(claim, stale, 2))
        request = ValidationRequest.for_claim(
            validation_id="reject-stale",
            claim=claim,
            target_snapshot=current,
        )
        update = ValidationWorkflow().start(request, knowledge_store=store)

    step = ValidationWorkflow.step(update.progress)
    assert not step.terminal
    assert len(step.actions) == 1
    assert update.progress.evidence == ()
    gap = validation_evidence_request_from_action(step.actions[0])
    assert gap.validation == request
    assert gap.known_evidence_refs == ()
    assert gap.gaps == ("obtain current substantive evidence for the exact claim",)


def test_knowledge_reuse_honors_the_request_evidence_types(tmp_path: Path) -> None:
    _, _, current, claim = _target_context()
    counterexamples = tuple(
        Evidence(
            evidence_type="counterexample",
            data={"sample": index},
            subject_refs=(claim.ref,),
            source_refs=(current.ref,),
            target_snapshot=current,
            weight=1.0,
        )
        for index in (1, 2)
    )
    with SQLiteKnowledgeStore(tmp_path / "evidence-types.sqlite") as store:
        for item in counterexamples:
            store.put(item)
        request = ValidationRequest.for_claim(
            validation_id="support-only-knowledge",
            claim=claim,
            target_snapshot=current,
            evidence_types=("support",),
        )
        update = ValidationWorkflow().start(request, knowledge_store=store)

    assert update.progress.result is None
    assert update.progress.evidence == ()
    gap = validation_evidence_request_from_action(update.progress.state.pending_actions[0])
    assert gap.known_evidence_refs == ()
    assert gap.validation.evidence_types == ("support",)


@pytest.mark.parametrize(
    ("valid", "currentness", "message"),
    [
        (False, "current", "invalid evidence state"),
        (True, "stale", "currentness projection has drifted"),
    ],
)
def test_knowledge_reuse_revalidates_host_store_projections(
    valid: bool,
    currentness: str,
    message: str,
) -> None:
    _, _, current, claim = _target_context()
    evidence = _support(claim, current, 1)

    class _LeakyStore:
        def put(self, *args, **kwargs):
            raise NotImplementedError

        def put_many(self, *args, **kwargs):
            raise NotImplementedError

        def get(self, root: str):
            return evidence if root == evidence.root else None

        def query(self, query):
            assert query.evidence_types == tuple(sorted(request.evidence_types))
            return (
                StoredKnowledge(
                    record=evidence,
                    source_run_id="host-store",
                    valid=valid,
                    stored_at="2026-08-22T00:00:00Z",
                    currentness=currentness,
                ),
            )

        def relationships(self, *args, **kwargs):
            return ()

        def close(self):
            return None

    request = ValidationRequest.for_claim(
        validation_id="revalidate-host-store",
        claim=claim,
        target_snapshot=current,
        evidence_types=("support",),
    )
    with pytest.raises(ValueError, match=message):
        ValidationWorkflow().start(
            request,
            knowledge_store=_LeakyStore(),  # type: ignore[arg-type]
        )


def test_convenience_validation_uses_same_runtime_semantics_for_all_outcomes() -> None:
    claim = Claim(statement="The invariant holds", kind="invariant")

    def evidence(kind: str, index: int, weight: float = 1.0) -> Evidence:
        return Evidence(
            evidence_type=kind,
            data={"sample": index},
            subject_refs=(claim.ref,),
            source_refs=(claim.ref,),
            weight=weight,
        )

    supported = validate(
        claim=claim,
        validation_id="supported",
        evidence=(evidence("support", 1), evidence("support", 2)),
    )
    contradicted = validate(
        claim=claim,
        validation_id="contradicted",
        evidence=(evidence("counterexample", 3), evidence("counterexample", 4)),
    )
    bounded = validate(
        claim=claim,
        validation_id="bounded",
        evidence=(evidence("boundary", 5),),
    )
    inconclusive = validate(claim=claim, validation_id="inconclusive")

    assert supported.disposition == "supported"
    assert contradicted.disposition == "contradicted"
    assert bounded.disposition == "bounded"
    assert inconclusive.disposition == "inconclusive"
    assert inconclusive.unresolved == ("no evidence collector or explicit evidence was supplied",)
    assert all(item.validation.claim == claim for item in (supported, contradicted, bounded))


def test_validation_requests_only_the_bounded_frontier_and_stops_at_sufficiency() -> None:
    claim = Claim(statement="The bounded process is stable", kind="behavioral")
    request = ValidationRequest.for_claim(
        validation_id="two-frontiers",
        claim=claim,
        max_evidence_actions=2,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    first_action = started.progress.state.pending_actions[0]
    first_request = validation_evidence_request_from_action(first_action)
    first_evidence = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(claim.ref,),
        source_refs=(first_request.ref,),
        weight=1.0,
    )
    first = workflow.submit(
        started.progress,
        make_validation_evidence_result(
            action=first_action,
            batch=ValidationEvidenceBatch.collected(
                request=first_request, evidence=(first_evidence,)
            ),
        ),
    )

    assert first.progress.result is None
    second_action = first.progress.state.pending_actions[0]
    assert second_action.action_id == "validation-evidence-2"
    assert second_action.action_id != first_action.action_id
    second_request = validation_evidence_request_from_action(second_action)
    second_evidence = Evidence(
        evidence_type="support",
        data={"sample": 2},
        subject_refs=(claim.ref,),
        source_refs=(second_request.ref,),
        weight=1.0,
    )
    second = workflow.submit(
        first.progress,
        make_validation_evidence_result(
            action=second_action,
            batch=ValidationEvidenceBatch.collected(
                request=second_request, evidence=(second_evidence,)
            ),
        ),
    )

    assert second.progress.result is not None
    assert second.progress.result.disposition == "supported"
    assert second.progress.state.action_count == 2
    assert second.progress.state.pending_actions == ()


def test_submission_revalidates_reused_evidence_against_the_same_store(
    tmp_path: Path,
) -> None:
    _, _, current, claim = _target_context()
    reused = _support(claim, current, 1)
    request = ValidationRequest.for_claim(
        validation_id="reused-submit",
        claim=claim,
        target_snapshot=current,
    )
    workflow = ValidationWorkflow()
    with SQLiteKnowledgeStore(tmp_path / "reused-submit.sqlite") as store:
        store.put(reused)
        started = workflow.start(request, knowledge_store=store)
        action = started.progress.state.pending_actions[0]
        gap = validation_evidence_request_from_action(action)
        gathered = Evidence(
            evidence_type="support",
            data={"sample": 2},
            subject_refs=(claim.ref,),
            source_refs=(gap.ref,),
            target_snapshot=current,
            weight=1.0,
        )
        result = make_validation_evidence_result(
            action=action,
            batch=ValidationEvidenceBatch.collected(
                request=gap,
                evidence=(gathered,),
            ),
        )

        class _CountingExperimenter:
            def __init__(self) -> None:
                self.calls = 0

            def experiment(self, requested):
                self.calls += 1
                return result

        with pytest.raises(ValueError, match="requires KnowledgeStore"):
            workflow.submit(started.progress, result)
        experimenter = _CountingExperimenter()
        with pytest.raises(ValueError, match="requires KnowledgeStore"):
            workflow.run_managed(started.progress, experimenter)
        assert experimenter.calls == 0
        completed = workflow.submit(
            started.progress,
            result,
            knowledge_store=store,
        )

    assert completed.progress.result is not None
    assert completed.progress.result.disposition == "supported"
    assert completed.progress.result.reused_evidence_refs == (reused.evidence_ref,)
    assert completed.progress.result.gathered_evidence_refs == (gathered.evidence_ref,)


def test_evidence_action_budget_stops_an_inconclusive_validation() -> None:
    claim = Claim(statement="One sample is sufficient", kind="behavioral")
    result = validate(
        claim=claim,
        validation_id="one-action-budget",
        evidence=(
            Evidence(
                evidence_type="support",
                data={"sample": 1},
                subject_refs=(claim.ref,),
                source_refs=(claim.ref,),
                weight=1.0,
            ),
        ),
        max_evidence_actions=1,
    )

    assert result.disposition == "inconclusive"
    assert result.unresolved == ("obtain enough current evidence to meet a decisive threshold",)
