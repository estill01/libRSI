from __future__ import annotations

from librsi import (
    Claim,
    Evidence,
    RSIKernel,
    Target,
    TargetCapabilities,
    TargetComparison,
    TargetPolicy,
    TargetRef,
    TargetSnapshot,
    deserialize_record,
    serialize_record,
)


def _simulation_snapshots() -> tuple[TargetRef, TargetSnapshot, TargetSnapshot]:
    target = TargetRef(
        target_id="thermal-process",
        kind="parameterized-simulation",
        locator={"model": "synthetic-thermal-v1"},
    )
    baseline = TargetSnapshot(
        target=target,
        revision="sample-1",
        state={"gain": 0.4, "ambient_temperature": 20.0},
    )
    current = TargetSnapshot(
        target=target,
        revision="sample-2",
        state={"gain": 0.5, "ambient_temperature": 20.0},
    )
    return target, baseline, current


def _process_target() -> tuple[TargetRef, TargetSnapshot, TargetSnapshot]:
    policy = TargetPolicy()
    controller = TargetRef(target_id="controller", kind="configuration")
    vessel = TargetRef(target_id="vessel", kind="physical-system")
    sensor = TargetRef(target_id="temperature-sensor", kind="instrument")
    controller_capabilities = policy.capabilities(
        controller,
        supported=("inspect", "adjust"),
        locally_available=("inspect",),
    )
    components = (
        policy.component(component_id="sensor", target=sensor),
        policy.component(
            component_id="controller",
            target=controller,
            capabilities=controller_capabilities,
        ),
        policy.component(component_id="vessel", target=vessel),
    )
    process = policy.compose(
        target_id="heat-treatment-process",
        kind="synthetic-process",
        components=components,
        locator={"site": "test-cell"},
    )

    controller_v1 = policy.snapshot(controller, state={"gain": 0.4}, revision="c1")
    controller_v2 = policy.snapshot(controller, state={"gain": 0.5}, revision="c2")
    vessel_snapshot = policy.snapshot(vessel, state={"volume": 100.0})
    sensor_snapshot = policy.snapshot(sensor, state={"calibration": "s1"})
    baseline = policy.snapshot(
        process,
        state={"mode": "closed-loop"},
        revision="run-1",
        components=(vessel_snapshot, sensor_snapshot, controller_v1),
    )
    current = policy.snapshot(
        process,
        state={"mode": "closed-loop"},
        revision="run-2",
        components=(controller_v2, vessel_snapshot, sensor_snapshot),
    )
    return process, baseline, current


def test_nonsoftware_evidence_currentness_uses_only_generic_target_semantics() -> None:
    target, baseline, current = _simulation_snapshots()
    claim = Claim(statement="The simulation remains stable", target=target)
    evidence = Evidence(
        evidence_type="support",
        data={"maximum_temperature": 24.0},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        target_snapshot=baseline,
        weight=0.7,
    )
    policy = RSIKernel().targets

    comparison = policy.evidence_currentness(evidence, current)

    assert comparison.disposition == "stale"
    assert comparison.baseline == baseline
    assert comparison.current == current
    assert policy.is_current(current, current)
    assert not policy.is_current(baseline, current)


def test_old_evidence_cannot_be_required_as_current() -> None:
    target, baseline, current = _simulation_snapshots()
    claim = Claim(statement="The simulation remains stable", target=target)
    evidence = Evidence(
        evidence_type="support",
        data={"maximum_temperature": 24.0},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        target_snapshot=baseline,
        weight=0.7,
    )
    policy = TargetPolicy()

    try:
        policy.require_evidence_current(evidence, current)
    except ValueError as error:
        assert "stale" in str(error)
    else:  # pragma: no cover - explicit safety assertion
        raise AssertionError("stale evidence was accepted as current")

    current_evidence = Evidence(
        evidence_type="support",
        data={"maximum_temperature": 23.0},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        target_snapshot=current,
        weight=0.7,
    )
    assert policy.require_evidence_current(current_evidence, current).disposition == "current"


def test_multicomponent_snapshots_compare_atomically_and_canonically() -> None:
    process, baseline, current = _process_target()
    policy = TargetPolicy()

    comparison = policy.compare(baseline, current)

    assert tuple(component.component_id for component in process.components) == (
        "controller",
        "sensor",
        "vessel",
    )
    assert tuple(snapshot.target.target_id for snapshot in baseline.components) == (
        "controller",
        "temperature-sensor",
        "vessel",
    )
    assert comparison.disposition == "stale"
    assert comparison.component_currentness == {
        "controller": False,
        "sensor": True,
        "vessel": True,
    }
    assert policy.compare(current, current).component_currentness == {
        "controller": True,
        "sensor": True,
        "vessel": True,
    }


def test_parent_state_is_part_of_atomic_composite_currentness() -> None:
    process, baseline, _ = _process_target()
    same_components_new_parent = TargetSnapshot(
        target=process,
        state={"mode": "manual"},
        revision=baseline.revision,
        components=baseline.components,
    )

    comparison = TargetPolicy().compare(baseline, same_components_new_parent)

    assert comparison.disposition == "stale"
    assert all(comparison.component_currentness.values())


def test_opaque_externally_owned_target_needs_no_local_mutation_capability() -> None:
    target = TargetRef(target_id="external-instrument", kind="opaque-external")
    capabilities = TargetPolicy.capabilities(
        target,
        supported=("inspect",),
        locally_available=(),
    )
    snapshot = TargetPolicy.snapshot(
        target,
        state={"opaque_state_root": "state-001"},
    )

    assert capabilities.supports("inspect")
    assert not capabilities.supports("mutate")
    assert not capabilities.is_locally_available("inspect")
    assert TargetPolicy().require_current(snapshot, snapshot).disposition == "current"


def test_target_records_and_comparison_round_trip_losslessly() -> None:
    process, baseline, current = _process_target()
    comparison = TargetPolicy().compare(baseline, current)
    records = (
        process.components[0].capabilities,
        process.components[0],
        process,
        baseline,
        comparison,
    )

    for record in records:
        assert record is not None
        assert deserialize_record(serialize_record(record)) == record

    assert isinstance(comparison, TargetComparison)


def test_target_alias_and_kernel_expose_independent_low_level_owner() -> None:
    target: Target = TargetRef(target_id="document", kind="structured-document")
    snapshot = RSIKernel().targets.snapshot(target, state={"sections": 4})

    assert isinstance(target, TargetRef)
    assert snapshot.target == target
    assert isinstance(TargetPolicy.capabilities(target), TargetCapabilities)
