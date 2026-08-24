from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from librsi import TargetPolicy, TargetRef, TargetSnapshot
from librsi.conformance import ComponentState, CompositeSnapshot, map_composite_snapshot
from tests.block23_reference_consumer import (
    governed_application_disabled_run,
    ordinary_multi_component_run,
)


class EqualitySpoofTarget(TargetRef):
    def __eq__(self, other: object) -> bool:
        return True


class EqualitySpoofSnapshot(TargetSnapshot):
    def __eq__(self, other: object) -> bool:
        return True


def test_ordinary_multi_component_consumer_returns_evidence_bound_candidate() -> None:
    run = ordinary_multi_component_run()
    assert run.validation.disposition == "supported"
    assert run.candidate.status == "prepared"
    assert run.candidate.evidence_refs
    assert run.candidate.snapshot != run.mapped.snapshot
    assert run.candidate.snapshot.target == run.mapped.target
    assert run.validation.ref not in run.candidate.evidence_refs
    assert run.candidate_trials.candidate == run.candidate
    assert run.candidate_trials.experiment.baseline_snapshot == run.mapped.snapshot
    assert run.candidate_trials.experiment.candidate_snapshot == run.candidate.snapshot
    assert run.candidate_trials.evaluation.disposition == "passed"
    assert run.candidate_trials.evaluation.subject_refs == (run.candidate_trials.experiment.ref,)


def test_candidate_workspace_never_becomes_authoritative_target() -> None:
    run = ordinary_multi_component_run()
    assert TargetPolicy.compare(run.mapped.snapshot, run.mapped.snapshot).disposition == "current"
    assert run.candidate.snapshot.root != run.mapped.snapshot.root
    comparison = TargetPolicy.compare(run.mapped.snapshot, run.candidate.snapshot)
    assert comparison.disposition == "stale"
    assert comparison.component_currentness == {"library": True, "service": False}
    with pytest.raises(ValueError, match="stale"):
        TargetPolicy().require_current(run.mapped.snapshot, run.candidate.snapshot)


def test_governed_self_target_run_is_application_disabled_and_effect_free() -> None:
    result = governed_application_disabled_run()
    assert result.disposition == "activation-disabled"
    assert result.application is None
    assert result.authoritative_snapshot == result.request.declaration.target_snapshot
    assert result.governance.disposition == "accepted"


def test_mapping_rejects_partial_ambiguous_or_duplicate_components() -> None:
    component = ComponentState(component_id="one", kind="opaque", revision="v1", state={"value": 1})
    with pytest.raises(ValueError, match="unique"):
        map_composite_snapshot(target_id="duplicate", components=(component, component))
    with pytest.raises(ValueError, match="exact ComponentState"):
        map_composite_snapshot(target_id="empty", components=())
    with pytest.raises(ValueError, match="component state"):
        replace(component, state={})
    with pytest.raises(TypeError, match="sequence"):
        map_composite_snapshot(target_id="invalid", components=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="component component_id"):
        replace(component, component_id=" ")
    with pytest.raises(TypeError, match="locator"):
        ComponentState(
            component_id="bad",
            kind="opaque",
            revision="v1",
            state={"value": 1},
            locator=object(),  # type: ignore[arg-type]
        )

    other = TargetRef(target_id="other", kind="opaque")
    other_snapshot = TargetSnapshot(target=other, revision="v1", state={"value": 1})
    with pytest.raises(ValueError, match="must match"):
        CompositeSnapshot(target=component_target(), snapshot=other_snapshot)


def test_composite_wrapper_rejects_record_subclasses_and_equality_spoofs() -> None:
    target = component_target()
    snapshot = TargetSnapshot(target=target, revision="v1", state={"value": 1})
    spoof_target = EqualitySpoofTarget(target_id="spoof", kind="opaque")

    assert spoof_target == target
    assert spoof_target.root != target.root
    with pytest.raises(TypeError, match="canonical target and snapshot"):
        CompositeSnapshot(target=spoof_target, snapshot=snapshot)
    with pytest.raises(TypeError, match="canonical target and snapshot"):
        CompositeSnapshot(
            target=target,
            snapshot=EqualitySpoofSnapshot(
                target=target,
                revision="v1",
                state={"value": 1},
            ),
        )
    with pytest.raises(TypeError, match="snapshot target.*canonical"):
        CompositeSnapshot(
            target=target,
            snapshot=TargetSnapshot(
                target=spoof_target,
                revision="v1",
                state={"value": 1},
            ),
        )


def test_mapping_is_canonical_across_caller_component_order() -> None:
    first = ComponentState(component_id="one", kind="opaque", revision="v1", state={"value": 1})
    second = ComponentState(component_id="two", kind="opaque", revision="v2", state={"value": 2})
    forward = map_composite_snapshot(target_id="ordered", components=(first, second))
    reverse = map_composite_snapshot(target_id="ordered", components=(second, first))
    assert reverse == forward


def component_target() -> TargetRef:
    return TargetRef(target_id="component", kind="opaque")


def test_reference_consumer_uses_public_imports_and_library_has_no_reverse_dependency() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture = root / "tests" / "block23_reference_consumer.py"
    tree = ast.parse(fixture.read_text(encoding="utf-8"))
    librsi_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("librsi")
    ]
    assert librsi_imports
    assert {node.module for node in librsi_imports} <= {"librsi", "librsi.conformance"}
    assert all(not alias.name.startswith("_") for node in librsi_imports for alias in node.names)

    for source in (root / "src" / "librsi").rglob("*.py"):
        library_tree = ast.parse(source.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(library_tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        } | {
            alias.name
            for node in ast.walk(library_tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert not any(
            module == "tests"
            or module.startswith("tests.")
            or module == "software_factory"
            or module.startswith("software_factory.")
            for module in imported_modules
        ), source
