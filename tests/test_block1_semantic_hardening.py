from __future__ import annotations

import pytest

from librsi import (
    Claim,
    Evidence,
    EvidenceRef,
    Goal,
    Hypothesis,
    Observation,
    RecordRef,
    TargetRef,
    Trial,
)


def test_metadata_is_not_python_semantic_identity() -> None:
    first = Claim(statement="Same claim", metadata={"display": "first"})
    second = Claim(
        statement="Same claim",
        metadata={"display": "second", "expanded": True},
    )

    assert first.root == second.root
    assert first == second
    assert hash(first) == hash(second)
    assert len({first, second}) == 1


def test_typed_and_generic_refs_share_exact_reference_identity() -> None:
    claim = Claim(statement="Claim")
    evidence = Evidence(
        evidence_type="support",
        data={"ok": True},
        subject_refs=(claim.ref,),
    )

    generic = RecordRef("evidence", evidence.root)
    typed = EvidenceRef.from_evidence(evidence)

    assert EvidenceRef.from_record(evidence) == typed
    assert generic == typed
    assert typed == generic
    assert hash(generic) == hash(typed)
    assert len({generic, typed}) == 1
    assert generic.matches(evidence)
    assert typed.require(evidence) is evidence
    with pytest.raises(TypeError, match="Evidence record"):
        EvidenceRef.from_record(claim)


def test_text_fields_reject_non_strings_instead_of_coercing() -> None:
    with pytest.raises(TypeError, match="string"):
        Claim(statement=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="string"):
        TargetRef(target_id=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="string"):
        Goal(statement=True)  # type: ignore[arg-type]


def test_boolean_fields_reject_truthy_strings() -> None:
    with pytest.raises(TypeError, match="boolean"):
        Observation(kind="result", value=1, valid="false")  # type: ignore[arg-type]


def test_trial_index_rejects_lossy_numeric_coercion() -> None:
    experiment_ref = RecordRef("experiment_spec", "a" * 64)

    with pytest.raises(TypeError, match="integer"):
        Trial(experiment=experiment_ref, index=1.7, status="done")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="integer"):
        Trial(experiment=experiment_ref, index=True, status="done")  # type: ignore[arg-type]


def test_numeric_epistemic_fields_reject_strings_and_booleans() -> None:
    with pytest.raises(TypeError, match="number"):
        Hypothesis(statement="H", confidence="0.5")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="number"):
        Hypothesis(statement="H", confidence=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="number"):
        Evidence(evidence_type="support", data={}, weight="0.7")  # type: ignore[arg-type]


def test_record_roots_reject_non_string_values() -> None:
    with pytest.raises(TypeError, match="root must be a string"):
        RecordRef("claim", 1)  # type: ignore[arg-type]
