from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

import librsi
from librsi import (
    ArtifactRef,
    Candidate,
    Claim,
    Constraint,
    Evaluation,
    Evidence,
    EvidenceRef,
    ExperimentSpec,
    FrozenMap,
    Goal,
    Hypothesis,
    Intervention,
    Measurement,
    Observation,
    Outcome,
    Question,
    RecordRef,
    SemanticRecord,
    TargetRef,
    TargetSnapshot,
    Trial,
    deserialize_record,
    record_from_dict,
    serialize_record,
)


def _record_graph() -> list[SemanticRecord]:
    target = TargetRef(
        target_id="scheduler",
        kind="software",
        locator={"repo": "estill01/example", "component": "queue"},
        metadata={"display_name": "Scheduler"},
    )
    baseline = TargetSnapshot(
        target=target,
        revision="abc123",
        state={"metrics": {"p95_ms": 120.0}, "revision": "abc123"},
    )
    claim = Claim(
        statement="The scheduler preserves FIFO order for equal-priority work",
        kind="behavior",
        target=target,
        scope={"component": "queue"},
    )
    question = Question(
        prompt="What causes scheduler latency spikes?",
        target=target,
        context={"window": "p95"},
    )
    goal = Goal(
        statement="Reduce scheduler queue latency",
        target=target,
        scope={"metric": "p95_ms"},
    )
    constraint = Constraint(
        statement="Do not reduce throughput",
        target=target,
        scope={"tolerance": 0.02},
    )
    hypothesis = Hypothesis(
        statement="Lock contention contributes to p95 queue latency",
        target=target,
        causal_model={"cause": "global lock contention"},
        predictions=({"metric": "p95_ms", "direction": "decrease"},),
        source_refs=(question.ref,),
        confidence=0.6,
    )
    experiment = ExperimentSpec(
        experiment_id="latency-comparison-1",
        kind="benchmark",
        target_snapshot=baseline,
        design={"kind": "isolated comparison", "repetitions": 5},
        criteria={"p95_ms": {"direction": "decrease"}},
        inputs={"workload": "representative"},
        environment={"python": "3.13"},
        requested_measurements=("p95_ms", "throughput"),
        lineage=(hypothesis.ref,),
    )
    observation = Observation(
        kind="benchmark_result",
        value={"p95_ms": 92.0, "throughput": 1004},
        target_snapshot=baseline,
        source_refs=(experiment.ref,),
    )
    trial = Trial(
        experiment=experiment.ref,
        index=0,
        status="completed",
        observation_refs=(observation.ref,),
        data={"duration_seconds": 30},
    )
    measurement = Measurement(
        metric="p95_ms",
        value=92.0,
        unit="ms",
        target_snapshot=baseline,
        observation_refs=(observation.ref,),
    )
    evidence = Evidence(
        evidence_type="support",
        data={"baseline_ms": 120.0, "candidate_ms": 92.0},
        subject_refs=(hypothesis.ref,),
        source_refs=(trial.ref,),
        target_snapshot=baseline,
        weight=0.7,
    )
    evaluation = Evaluation(
        subject_refs=(experiment.ref,),
        disposition="passed",
        measurements=(measurement,),
        findings={"meaningful_improvement": True},
    )
    artifact = ArtifactRef(
        artifact_id="benchmark-report",
        uri="artifact://benchmark/report.json",
        content_digest="sha256:012345",
        media_type="application/json",
    )
    intervention = Intervention(
        target=target,
        kind="software.objective",
        specification={"objective": "narrow the scheduler critical section"},
        rationale={"hypothesis_root": hypothesis.root},
        expected_effects={"p95_ms": "decrease"},
        constraints=(constraint,),
        validation_plan={"experiment_root": experiment.root},
        lineage=(evidence.ref,),
    )
    candidate_snapshot = TargetSnapshot(
        target=target,
        revision="candidate-1",
        state={"metrics": {"p95_ms": 92.0}, "revision": "candidate-1"},
        lineage=(baseline.ref,),
    )
    candidate = Candidate(
        intervention=intervention.ref,
        target_snapshot=candidate_snapshot,
        artifacts=(artifact,),
    )
    outcome = Outcome(
        intent=goal.ref,
        status="improved",
        target_snapshot=candidate_snapshot,
        conclusions=("p95 queue latency decreased",),
        evidence_refs=(evidence.evidence_ref,),
        intervention_refs=(intervention.ref,),
        artifacts=(artifact,),
        unresolved=("p99 behavior remains unmeasured",),
        next_actions=("measure p99 latency",),
        lineage=(evaluation.ref, candidate.ref),
    )
    derived_claim = Claim(
        statement="The candidate reduced p95 queue latency under the benchmark workload",
        kind="observational",
        target=target,
        lineage=(claim.ref, evidence.ref),
    )
    return [
        target,
        baseline,
        claim,
        question,
        goal,
        constraint,
        hypothesis,
        experiment,
        observation,
        trial,
        measurement,
        evidence,
        evaluation,
        artifact,
        intervention,
        candidate_snapshot,
        candidate,
        outcome,
        derived_claim,
    ]


def test_all_block_one_records_are_public() -> None:
    names = {
        "ArtifactRef",
        "Candidate",
        "Claim",
        "Constraint",
        "Evaluation",
        "Evidence",
        "EvidenceRef",
        "ExperimentSpec",
        "Goal",
        "Hypothesis",
        "Intervention",
        "Measurement",
        "Observation",
        "Outcome",
        "Question",
        "RecordRef",
        "SemanticRecord",
        "TargetRef",
        "TargetSnapshot",
        "Trial",
    }
    assert names <= set(librsi.__all__)
    assert all(hasattr(librsi, name) for name in names)


def test_complete_record_graph_round_trips_deterministically() -> None:
    for record in _record_graph():
        serialized = serialize_record(record)
        restored = deserialize_record(serialized)
        assert restored == record
        assert restored.root == record.root
        assert serialize_record(restored) == serialized
        assert record_from_dict(record.to_dict()) == record
        envelope = json.loads(serialized)
        assert envelope["schema_version"] == 1
        assert envelope["record_type"] == record.record_type
        assert envelope["root"] == record.root


def test_identity_is_stable_for_ordering_and_excludes_presentation_metadata() -> None:
    first_target = TargetRef(
        target_id="system",
        locator={"z": 2, "a": {"two": 2, "one": 1}},
        metadata={"label": "first"},
    )
    second_target = TargetRef(
        target_id="system",
        locator={"a": {"one": 1, "two": 2}, "z": 2},
        metadata={"label": "second", "ui": {"expanded": True}},
    )
    assert first_target.root == second_target.root
    assert serialize_record(first_target) != serialize_record(second_target)

    changed_target = TargetRef(target_id="system-2", locator={"z": 2, "a": {"two": 2, "one": 1}})
    assert changed_target.root != first_target.root

    first_claim = Claim(statement="Capability exists", target=first_target, metadata={"label": "A"})
    second_claim = Claim(statement="Capability exists", target=second_target, metadata={"label": "B"})
    assert first_claim.root == second_claim.root
    assert Claim(statement="Capability does not exist", target=first_target).root != first_claim.root


def test_records_are_deeply_immutable_and_detached_from_input_objects() -> None:
    source = {"nested": {"items": [1, 2]}, "enabled": True}
    claim = Claim(statement="Immutable", scope=source)
    source["nested"]["items"].append(3)  # type: ignore[union-attr]
    assert claim.scope["nested"] == FrozenMap({"items": [1, 2]})

    with pytest.raises(FrozenInstanceError):
        claim.statement = "mutated"  # type: ignore[misc]
    with pytest.raises(TypeError):
        claim.scope["new"] = "value"  # type: ignore[index]
    nested = claim.scope["nested"]
    assert isinstance(nested, FrozenMap)
    with pytest.raises(TypeError):
        nested["items"] = (9,)  # type: ignore[index]


def test_exact_references_fail_closed_on_type_or_identity_mismatch() -> None:
    claim = Claim(statement="A claim")
    goal = Goal(statement="A goal")
    ref = claim.ref
    assert ref.matches(claim)
    assert ref.require(claim) is claim
    assert not ref.matches(goal)
    with pytest.raises(ValueError, match="does not match"):
        ref.require(goal)
    with pytest.raises(ValueError, match="SHA-256"):
        RecordRef("claim", "not-a-root")
    with pytest.raises(ValueError, match="record type"):
        RecordRef("", claim.root)

    evidence = Evidence(evidence_type="support", data={"ok": True}, subject_refs=(claim.ref,))
    evidence_ref = EvidenceRef.from_evidence(evidence)
    assert evidence_ref.matches(evidence)
    with pytest.raises(TypeError, match="evidence references"):
        Outcome(intent=goal.ref, status="done", evidence_refs=(claim.ref,))  # type: ignore[arg-type]


def test_serialization_detects_tampering_unknown_versions_and_bad_envelopes() -> None:
    claim = Claim(statement="The original claim", metadata={"display": "safe to edit"})
    envelope = claim.to_dict()
    envelope["data"]["statement"] = "A different claim"
    with pytest.raises(ValueError, match="root does not match"):
        record_from_dict(envelope)

    bad_version = claim.to_dict()
    bad_version["schema_version"] = 99
    with pytest.raises(ValueError, match="version"):
        record_from_dict(bad_version)

    unknown = claim.to_dict()
    unknown["record_type"] = "unknown"
    with pytest.raises(ValueError, match="unknown"):
        record_from_dict(unknown)

    incomplete = claim.to_dict()
    incomplete.pop("data")
    with pytest.raises(ValueError, match="incomplete"):
        record_from_dict(incomplete)

    bad_metadata = claim.to_dict()
    bad_metadata["metadata"] = "not-a-map"
    with pytest.raises(ValueError, match="metadata"):
        record_from_dict(bad_metadata)

    with pytest.raises(ValueError, match="schema"):
        record_from_dict({"$schema": "other"})
    with pytest.raises(ValueError, match="JSON object"):
        deserialize_record("[]")
    with pytest.raises(TypeError, match="SemanticRecord"):
        serialize_record("not-a-record")  # type: ignore[arg-type]


def test_canonical_values_reject_ambiguous_or_nondeterministic_data() -> None:
    with pytest.raises(TypeError, match="string keys"):
        FrozenMap({1: "bad"})  # type: ignore[dict-item]
    with pytest.raises(ValueError, match="finite"):
        Claim(statement="bad float", scope={"value": float("nan")})
    with pytest.raises(TypeError, match="unsupported"):
        Claim(statement="bad set", scope={"values": {1, 2}})


def test_record_specific_validation_fails_closed() -> None:
    target = TargetRef(target_id="target")
    snapshot = TargetSnapshot(target=target, state={"revision": 1})
    claim = Claim(statement="claim", target=target)
    experiment = ExperimentSpec(experiment_id="e", kind="command", target_snapshot=snapshot)
    observation = Observation(kind="result", value=1, target_snapshot=snapshot)
    constraint = Constraint(statement="constraint", target=target)
    intervention = Intervention(target=target, kind="change", specification={"x": 1})
    artifact = ArtifactRef(artifact_id="a", uri="artifact://a")

    with pytest.raises(TypeError, match="TargetRef"):
        TargetSnapshot(target=claim, state={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="components"):
        TargetSnapshot(target=target, state={}, components=(claim,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="claim target"):
        Claim(statement="x", target=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="question target"):
        Question(prompt="x", target=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="goal target"):
        Goal(statement="x", target=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="constraint target"):
        Constraint(statement="x", target=claim)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="between zero and one"):
        Hypothesis(statement="x", confidence=1.1)
    with pytest.raises(TypeError, match="hypothesis target"):
        Hypothesis(statement="x", target=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="evidence target"):
        Evidence(evidence_type="support", data={}, target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        Evidence(evidence_type="support", data={}, weight=float("inf"))
    with pytest.raises(TypeError, match="experiment target"):
        ExperimentSpec(experiment_id="e2", kind="x", target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation target"):
        Observation(kind="x", value=1, target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ExperimentSpec"):
        Trial(experiment=claim.ref, index=0, status="done")
    with pytest.raises(ValueError, match="nonnegative"):
        Trial(experiment=experiment.ref, index=-1, status="done")
    with pytest.raises(TypeError, match="measurement target"):
        Measurement(metric="x", value=1, target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="subject"):
        Evaluation(subject_refs=(), disposition="passed")
    with pytest.raises(TypeError, match="Measurement"):
        Evaluation(subject_refs=(claim.ref,), disposition="passed", measurements=(claim,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="intervention target"):
        Intervention(target=claim, kind="x", specification={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Constraint"):
        Intervention(target=target, kind="x", specification={}, constraints=(claim,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Intervention"):
        Candidate(intervention=claim.ref, target_snapshot=snapshot)
    with pytest.raises(TypeError, match="candidate target"):
        Candidate(intervention=intervention.ref, target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ArtifactRef"):
        Candidate(intervention=intervention.ref, target_snapshot=snapshot, artifacts=(claim,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="outcome intent"):
        Outcome(intent=target, status="done")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="outcome target"):
        Outcome(intent=claim.ref, status="done", target_snapshot=claim)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="intervention references"):
        Outcome(intent=claim.ref, status="done", intervention_refs=(claim.ref,))
    with pytest.raises(TypeError, match="outcome artifacts"):
        Outcome(intent=claim.ref, status="done", artifacts=(claim,))  # type: ignore[arg-type]

    evaluation = Evaluation(
        subject_refs=(experiment.ref,),
        disposition="passed",
        measurements=(Measurement(metric="x", value=1, observation_refs=(observation.ref,)),),
    )
    assert evaluation.measurements[0].metric == "x"
    assert constraint.target == target
    assert artifact.uri == "artifact://a"
