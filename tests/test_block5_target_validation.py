from __future__ import annotations

import json
from dataclasses import fields

import pytest

from librsi import (
    Claim,
    Evidence,
    TargetCapabilities,
    TargetComparison,
    TargetComponent,
    TargetPolicy,
    TargetRef,
    TargetSnapshot,
    deserialize_record,
    serialize_record,
)


def _components() -> tuple[TargetRef, TargetRef, TargetComponent, TargetComponent]:
    first = TargetRef(target_id="first", kind="simulation-component")
    second = TargetRef(target_id="second", kind="simulation-component")
    return (
        first,
        second,
        TargetComponent(component_id="first", target=first),
        TargetComponent(component_id="second", target=second),
    )


def test_duplicate_component_ids_and_targets_fail_closed() -> None:
    first, second, first_component, _ = _components()

    with pytest.raises(ValueError, match="component ids.*unique"):
        TargetRef(
            target_id="duplicate-id",
            components=(
                first_component,
                TargetComponent(component_id="first", target=second),
            ),
        )
    with pytest.raises(ValueError, match="component targets.*unique"):
        TargetRef(
            target_id="duplicate-target",
            components=(
                first_component,
                TargetComponent(component_id="alias", target=first),
            ),
        )


def test_partial_extra_and_duplicate_component_snapshots_fail_closed() -> None:
    first, second, first_component, second_component = _components()
    composite = TargetRef(
        target_id="composite",
        components=(first_component, second_component),
    )
    first_snapshot = TargetSnapshot(target=first, state={"value": 1})
    second_snapshot = TargetSnapshot(target=second, state={"value": 2})
    extra = TargetRef(target_id="extra")
    extra_snapshot = TargetSnapshot(target=extra, state={})

    with pytest.raises(ValueError, match="every exact target component"):
        TargetSnapshot(target=composite, state={}, components=(first_snapshot,))
    with pytest.raises(ValueError, match="every exact target component"):
        TargetSnapshot(
            target=composite,
            state={},
            components=(first_snapshot, extra_snapshot),
        )
    with pytest.raises(ValueError, match="components must be unique"):
        TargetSnapshot(
            target=composite,
            state={},
            components=(first_snapshot, first_snapshot),
        )
    assert TargetSnapshot(
        target=composite,
        state={},
        components=(second_snapshot, first_snapshot),
    ).components == (first_snapshot, second_snapshot)


def test_atomic_target_rejects_unowned_component_snapshot() -> None:
    atomic = TargetRef(target_id="atomic")
    component = TargetSnapshot(target=TargetRef(target_id="other"), state={})

    with pytest.raises(ValueError, match="atomic target"):
        TargetSnapshot(target=atomic, state={}, components=(component,))


def test_component_capabilities_must_match_the_exact_component_target() -> None:
    first, second, _, _ = _components()
    capabilities = TargetCapabilities(target=second, supported=("inspect",))

    with pytest.raises(ValueError, match="do not match"):
        TargetComponent(
            component_id="first",
            target=first,
            capabilities=capabilities,
        )
    with pytest.raises(TypeError, match="require a TargetRef"):
        TargetComponent(component_id="bad", target=Claim(statement="bad"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be TargetCapabilities"):
        TargetComponent(
            component_id="bad",
            target=first,
            capabilities=Claim(statement="bad"),  # type: ignore[arg-type]
        )


def test_capability_declarations_are_unique_and_locally_bounded() -> None:
    target = TargetRef(target_id="opaque")

    with pytest.raises(ValueError, match="supported.*unique"):
        TargetCapabilities(target=target, supported=("inspect", "inspect"))
    with pytest.raises(ValueError, match="available.*unique"):
        TargetCapabilities(
            target=target,
            supported=("inspect",),
            locally_available=("inspect", "inspect"),
        )
    with pytest.raises(ValueError, match="declared as supported"):
        TargetCapabilities(target=target, locally_available=("mutate",))
    with pytest.raises(TypeError, match="sequence"):
        TargetPolicy.capabilities(target, supported="inspect")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a TargetRef"):
        TargetCapabilities(target=Claim(statement="bad"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="require a TargetRef"):
        TargetPolicy.capabilities(Claim(statement="bad"))  # type: ignore[arg-type]


def test_comparison_rejects_mismatched_targets_and_untruthful_results() -> None:
    first = TargetRef(target_id="first")
    second = TargetRef(target_id="second")
    first_snapshot = TargetSnapshot(target=first, state={"value": 1})
    changed_first = TargetSnapshot(target=first, state={"value": 2})
    second_snapshot = TargetSnapshot(target=second, state={"value": 1})

    with pytest.raises(ValueError, match="exact same target"):
        TargetPolicy().compare(first_snapshot, second_snapshot)
    with pytest.raises(ValueError, match="exact same target"):
        TargetComparison(
            baseline=first_snapshot,
            current=second_snapshot,
            disposition="stale",
        )
    with pytest.raises(ValueError, match="does not match"):
        TargetComparison(
            baseline=first_snapshot,
            current=changed_first,
            disposition="current",
        )
    with pytest.raises(ValueError, match="unsupported"):
        TargetComparison(
            baseline=first_snapshot,
            current=changed_first,
            disposition="unknown",
        )


def test_composite_comparison_requires_complete_component_currentness() -> None:
    first, second, first_component, second_component = _components()
    composite = TargetRef(
        target_id="composite",
        components=(first_component, second_component),
    )
    first_snapshot = TargetSnapshot(target=first, state={"value": 1})
    second_snapshot = TargetSnapshot(target=second, state={"value": 2})
    baseline = TargetSnapshot(
        target=composite,
        state={},
        components=(first_snapshot, second_snapshot),
    )

    with pytest.raises(ValueError, match="every exact component"):
        TargetComparison(
            baseline=baseline,
            current=baseline,
            disposition="current",
            component_currentness={"first": True},
        )
    with pytest.raises(TypeError, match="must be booleans"):
        TargetComparison(
            baseline=baseline,
            current=baseline,
            disposition="current",
            component_currentness={"first": 1, "second": 1},
        )

    valid = TargetPolicy().compare(baseline, baseline)
    payload = json.loads(serialize_record(valid))
    payload["data"]["component_currentness"]["items"]["first"] = 1
    with pytest.raises(TypeError, match="must be booleans"):
        deserialize_record(json.dumps(payload))


def test_evidence_currentness_rejects_missing_or_cross_target_snapshots() -> None:
    first = TargetRef(target_id="first")
    second = TargetRef(target_id="second")
    first_snapshot = TargetSnapshot(target=first, state={})
    second_snapshot = TargetSnapshot(target=second, state={})
    claim = Claim(statement="claim", target=first)
    unbound = Evidence(
        evidence_type="support",
        data={},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        weight=0.5,
    )
    bound = Evidence(
        evidence_type="support",
        data={},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        target_snapshot=first_snapshot,
        weight=0.5,
    )

    with pytest.raises(ValueError, match="exact target snapshot"):
        TargetPolicy().evidence_currentness(unbound, first_snapshot)
    with pytest.raises(ValueError, match="exact same target"):
        TargetPolicy().evidence_currentness(bound, second_snapshot)


def test_policy_construction_inputs_fail_closed() -> None:
    target = TargetRef(target_id="target")

    with pytest.raises(ValueError, match="at least one component"):
        TargetPolicy.compose(target_id="empty", components=())
    with pytest.raises(TypeError, match="sequence"):
        TargetPolicy.compose(target_id="bad", components="component")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TargetComponent"):
        TargetPolicy.compose(target_id="bad", components=(target,))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="state must be a mapping"):
        TargetPolicy.snapshot(target, state=())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requires a TargetRef"):
        TargetPolicy.snapshot(Claim(statement="bad"), state={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TargetSnapshot"):
        TargetPolicy().compare(target, target)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Evidence"):
        TargetPolicy().evidence_currentness(target, TargetSnapshot(target=target, state={}))  # type: ignore[arg-type]
    baseline = TargetSnapshot(target=target, state={"value": 1})
    current = TargetSnapshot(target=target, state={"value": 2})
    with pytest.raises(ValueError, match="stale"):
        TargetPolicy().require_current(baseline, current)


def test_generic_target_schema_requires_no_git_or_repository_fields() -> None:
    forbidden = {"git", "repository", "repo", "commit", "branch", "worktree"}
    target_fields = {item.name for item in fields(TargetRef)}
    snapshot_fields = {item.name for item in fields(TargetSnapshot)}
    target = TargetRef(target_id="structured-document", kind="document")

    assert forbidden.isdisjoint(target_fields)
    assert forbidden.isdisjoint(snapshot_fields)
    assert "components" not in target.identity_data()
    assert TargetSnapshot(target=target, state={"sections": 3}).target == target
