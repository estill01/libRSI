from __future__ import annotations

import hashlib
import importlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest
from embedded_service_contract import (  # type: ignore[import-untyped]
    HostContract,
    HostShape,
    assert_lifecycle_conformance,
)
from runtime_manifest import Component, RuntimeManifest, Sha256Root  # type: ignore[import-untyped]

from librsi import Evidence, ImprovementResult, ReasoningResult, record_from_dict
from librsi.conformance import (
    EMBEDDED_SERVICE_HANDOFF,
    QUALIFIED_PACKAGE_SET,
    RUNTIME_MANIFEST_HANDOFF,
    load_shared_utilities,
    validate_shared_package,
)
from librsi.conformance.lifecycle import (
    LifecycleObservation,
    LifecycleProjection,
    require_single_process_owner,
)
from librsi.conformance.manifest import (
    ADAPTER_RUNTIME_FILES,
    _adapter_root,
    build_runtime_manifest,
    compare_runtime_description,
    runtime_manifest_document,
)
from tests.block24_lifecycle_support import (
    embedded_lifecycle_fixture,
    service_lifecycle_fixture,
)
from tests.block24_scenario_support import (
    run_system_improvement,
    system_scenario_input,
)

SYSTEM_ACTION_ROOTS = (
    "7177156a4f6f7c829b3be17a8411b5003adaa0a66d0255681d74ca26e33b404d",
    "fae7619b63c69b98cca3590846b22e6c65d48ee71604ba404538ac0b105083ff",
)
SYSTEM_RESULT_ROOT = "aa061bc0d8c92e9f3cdd8f5311054d3ccca4eabfbb66b3af7aa537849b48b841"
SYSTEM_OUTCOME_ROOT = "25443d2238e70a2dc38ebf2ede9778318824cdda8e05d59909d9fa916baf5630"
SYSTEM_PROJECTION_ROOT = "72ce0e66a9d6d53261e6e2ac049063533405c0202bde0a70927239f4af60124a"


def test_exact_qualified_shared_package_set_and_descriptive_manifest_are_consumed() -> None:
    lifecycle, manifest_api = load_shared_utilities()
    validate_shared_package(lifecycle, EMBEDDED_SERVICE_HANDOFF)
    validate_shared_package(manifest_api, RUNTIME_MANIFEST_HANDOFF)
    assert QUALIFIED_PACKAGE_SET.producer_revision == "a5659745a7cbcbb002b5f06051f6ed9826f721a7"
    assert QUALIFIED_PACKAGE_SET.posture == "program-qualified/no-license-selected/unpublished"

    manifest = build_runtime_manifest()
    document = runtime_manifest_document()
    adapter_root, protocol_schema_root = _adapter_root()
    assert "shared-utilities.json" in ADAPTER_RUNTIME_FILES
    assert adapter_root == "cd54bf6ffa4cd1d9ee450fb86a5f52f569c01571bed23adae5fd2b274fc5eae9"
    assert (
        protocol_schema_root == "89edd647d75977f1b33dba9173118ae5490f1699a9e5725e28207961b8fd4e1a"
    )
    assert (
        hashlib.sha256(document.encode()).hexdigest()
        == "d2cd2b04c0549ae51ed48fd43b21ded14cc05882e2f7b1045a8285f2e4228cec"
    )
    assert manifest_api.parse_manifest(document) == manifest
    assert manifest.component.name == "librsi"
    assert {item.name for item in manifest.dependencies} == {
        "codex-app-server-client",
        "embedded-service-contract",
        "runtime-manifest",
    }
    assert compare_runtime_description(manifest).compatible is True

    drifted = RuntimeManifest(
        component=Component("librsi", "0.2.0", Sha256Root("0" * 64)),
        protocols=manifest.protocols,
        capabilities=manifest.capabilities,
        dependencies=manifest.dependencies,
    )
    diagnostic = compare_runtime_description(drifted)
    assert diagnostic.compatible is False
    assert [reason.kind.value for reason in diagnostic.unavailable_reasons] == ["component-root"]


def test_real_embedded_and_service_hosts_pass_exact_structural_conformance(tmp_path) -> None:
    embedded_fixture = embedded_lifecycle_fixture()
    service_fixture = service_lifecycle_fixture(tmp_path)
    embedded = assert_lifecycle_conformance(embedded_fixture)
    service = assert_lifecycle_conformance(service_fixture)
    embedded_contract = embedded_fixture.host_factory("owner").contract
    service_contract = service_fixture.host_factory("owner").contract

    assert embedded.shape is HostShape.EMBEDDED and embedded.scenarios == 3
    assert service.shape is HostShape.SERVICE and service.scenarios == 3
    require_single_process_owner((embedded_contract, service_contract))
    with pytest.raises(ValueError, match="exactly one process owner"):
        require_single_process_owner((service_contract, service_contract))


def test_external_and_managed_system_improvement_have_exact_roots_and_outcomes(tmp_path) -> None:
    scenario = system_scenario_input()
    codex = scenario.proposal
    assert type(codex) is ReasoningResult
    assert len(codex.content["hypotheses"]) == 2
    assert not isinstance(codex, Evidence)
    assert scenario.executor.policy.owner == "embedding-host"
    assert scenario.executor.process_owner_count == 0
    assert scenario.executor.requests == [codex.request]
    assert codex.request.target_snapshot is not None
    assert all(codex.ref in item.source_refs for item in scenario.request.initial_hypotheses)
    assert all(
        codex.request.ref in item.lineage and codex.request.target_snapshot.ref in item.lineage
        for item in scenario.request.initial_hypotheses
    )
    provider_contract = HostContract(
        shape=HostShape.EMBEDDED,
        process_owner_count=scenario.executor.process_owner_count,
    )
    service_contract = (
        service_lifecycle_fixture(tmp_path / "composition")
        .host_factory("system-provider-owner")
        .contract
    )
    require_single_process_owner((provider_contract, service_contract))

    external = run_system_improvement(tmp_path / "external", managed=False, scenario=scenario)
    managed = run_system_improvement(tmp_path / "managed", managed=True, scenario=scenario)
    assert external.request == managed.request == scenario.request
    assert external.execution_stop_reason == managed.execution_stop_reason == "outcome"
    assert external.projection == managed.projection
    assert [item.root for item in external.provider.actions] == [
        item.root for item in managed.provider.actions
    ]
    assert tuple(item.root for item in managed.provider.actions) == SYSTEM_ACTION_ROOTS
    assert managed.projection["result_root"] == SYSTEM_RESULT_ROOT
    assert managed.projection["outcome_root"] == SYSTEM_OUTCOME_ROOT
    assert managed.projection["projection_root"] == SYSTEM_PROJECTION_ROOT

    result = record_from_dict(managed.projection["result"])
    assert type(result) is ImprovementResult
    assert len(result.iterations) == 2
    first, second = result.iterations
    assert first.selection.disposition == "none-accepted"
    assert first.next_direction == "broaden"
    assert second.selection.disposition == "selected"
    assert second.next_direction == "stop"
    assert len(second.selection.assessments) == 2
    assert len(second.selection.selected) == 1
    losing = {
        assessment.candidate_ref
        for assessment in second.selection.assessments
        if assessment.candidate_ref not in second.selection.selected
    }
    assert losing and losing.isdisjoint(second.selection.selected)
    for iteration in result.iterations:
        branches = iteration.proposal.investigation.branches
        assert {branch.status for branch in branches} == {"retired", "supported"}
        retired = next(branch for branch in branches if branch.status == "retired")
        assert retired.belief.status not in {"supported", "rejected"}
        assert retired.evidence and {item.evidence_type for item in retired.evidence} == {"null"}


def test_shared_utility_substitutes_missing_lanes_and_manifest_authority_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, _ = load_shared_utilities()
    copied = ModuleType("embedded_service_contract")
    copied.__file__ = lifecycle.__file__
    copied.__version__ = lifecycle.__version__
    copied.__all__ = lifecycle.__all__
    for name in copied.__all__:
        setattr(copied, name, getattr(lifecycle, name))
    with pytest.raises(RuntimeError, match="active imported module"):
        validate_shared_package(copied, EMBEDDED_SERVICE_HANDOFF)

    lifecycle_shadow = ModuleType("embedded_service_contract")
    lifecycle_shadow.__file__ = lifecycle.__file__
    lifecycle_shadow.__version__ = lifecycle.__version__
    lifecycle_shadow.__all__ = lifecycle.__all__
    for name in lifecycle_shadow.__all__:
        setattr(lifecycle_shadow, name, getattr(lifecycle, name))
    lifecycle_shadow.HostContract = object()
    monkeypatch.setitem(sys.modules, "embedded_service_contract", lifecycle_shadow)
    with pytest.raises(RuntimeError, match="operational export owner"):
        validate_shared_package(lifecycle_shadow, EMBEDDED_SERVICE_HANDOFF)
    monkeypatch.undo()

    _, manifest_api = load_shared_utilities()
    manifest_shadow = ModuleType("runtime_manifest")
    manifest_shadow.__file__ = manifest_api.__file__
    manifest_shadow.__version__ = manifest_api.__version__
    manifest_shadow.__all__ = manifest_api.__all__
    for name in manifest_shadow.__all__:
        setattr(manifest_shadow, name, getattr(manifest_api, name))
    manifest_shadow.compare_manifests = object()
    monkeypatch.setitem(sys.modules, "runtime_manifest", manifest_shadow)
    with pytest.raises(RuntimeError, match="operational export owner"):
        validate_shared_package(manifest_shadow, RUNTIME_MANIFEST_HANDOFF)
    monkeypatch.undo()

    monkeypatch.setattr(lifecycle, "__version__", "0.1.1")
    with pytest.raises(RuntimeError, match="version"):
        validate_shared_package(lifecycle, EMBEDDED_SERVICE_HANDOFF)
    monkeypatch.undo()

    import librsi.conformance.shared_handoff as handoff_module

    original_import = importlib.import_module

    def missing(name: str):
        if name == "runtime_manifest":
            raise ModuleNotFoundError("mapped runtime-manifest lane is unavailable")
        return original_import(name)

    monkeypatch.setattr(handoff_module.importlib, "import_module", missing)
    with pytest.raises(ModuleNotFoundError, match="mapped runtime-manifest"):
        load_shared_utilities()
    monkeypatch.undo()

    with pytest.raises(TypeError, match="RuntimeManifest"):
        compare_runtime_description(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exactly one process owner|HostContract"):
        require_single_process_owner((object(),))  # type: ignore[arg-type]


def test_lifecycle_projection_rejects_implicit_or_malformed_semantics() -> None:
    lifecycle, _ = load_shared_utilities()
    with pytest.raises(TypeError, match="HostShape"):
        LifecycleProjection(shape="service", lineage="bad", execute=lambda _: None)  # type: ignore[arg-type,return-value]
    with pytest.raises(ValueError, match="lineage"):
        LifecycleProjection(
            shape=lifecycle.HostShape.EMBEDDED,
            lineage="",
            execute=lambda _: LifecycleObservation.running(value=None, event=None),
        )
    with pytest.raises(TypeError, match="callable executor"):
        LifecycleProjection(
            shape=lifecycle.HostShape.EMBEDDED,
            lineage="bad-executor",
            execute=None,  # type: ignore[arg-type]
        )
    malformed = LifecycleProjection(
        shape=lifecycle.HostShape.EMBEDDED,
        lineage="malformed",
        execute=lambda _: object(),  # type: ignore[return-value]
    )
    with pytest.raises(TypeError, match="LifecycleObservation"):
        malformed.start(object())
    with pytest.raises(ValueError, match="unsupported lifecycle"):
        LifecycleObservation("accepted", None, None)  # type: ignore[arg-type]

    good = LifecycleProjection(
        shape=lifecycle.HostShape.EMBEDDED,
        lineage="unknown",
        execute=lambda _: LifecycleObservation.running(value=None, event=None),
    )
    with pytest.raises(lifecycle.UnknownRunError):
        good.status(lifecycle.RunRef("missing"))
    with pytest.raises(lifecycle.InvalidCursorError):
        good.events(good.start(object()), after_sequence=-1)

    active = sys.modules.pop("runtime_manifest")
    try:
        with pytest.raises(RuntimeError, match="active imported module"):
            validate_shared_package(active, RUNTIME_MANIFEST_HANDOFF)
    finally:
        sys.modules["runtime_manifest"] = active

    with pytest.raises(TypeError, match="sequence"):
        require_single_process_owner("service")  # type: ignore[arg-type]


def test_shared_handoff_metadata_and_runtime_validation_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import librsi.conformance.shared_handoff as handoff_module

    with pytest.raises(RuntimeError, match="invalid text"):
        handoff_module._text(None, "text")
    with pytest.raises(RuntimeError, match="invalid digest"):
        handoff_module._sha256("not-a-digest", "digest")
    with pytest.raises(RuntimeError, match="invalid revision"):
        handoff_module._git_oid("not-a-revision", "revision")

    document = deepcopy(handoff_module._DOCUMENT)
    malformed = deepcopy(document)
    malformed["packages"] = {}
    with pytest.raises(RuntimeError, match="package set"):
        handoff_module._package(malformed, "embedded-service-contract")
    malformed = deepcopy(document)
    malformed["packages"]["embedded-service-contract"].pop("version")
    with pytest.raises(RuntimeError, match="metadata is not exact"):
        handoff_module._package(malformed, "embedded-service-contract")
    malformed = deepcopy(document)
    malformed["packages"]["embedded-service-contract"]["runtime_files"] = []
    with pytest.raises(RuntimeError, match="package files"):
        handoff_module._package(malformed, "embedded-service-contract")

    metadata_root = tmp_path / "metadata"
    metadata_root.mkdir()
    monkeypatch.setattr(handoff_module.resources, "files", lambda _name: metadata_root)
    with pytest.raises(RuntimeError, match="metadata is unavailable"):
        handoff_module._metadata()
    (metadata_root / "shared-utilities.json").write_text("{}")
    with pytest.raises(RuntimeError, match="unexpected shape"):
        handoff_module._metadata()
    bad_schema = deepcopy(document)
    bad_schema["schema_version"] = 2
    (metadata_root / "shared-utilities.json").write_text(json.dumps(bad_schema))
    with pytest.raises(RuntimeError, match="unsupported schema"):
        handoff_module._metadata()
    monkeypatch.undo()

    no_origin = ModuleType("embedded_service_contract")
    with pytest.raises(RuntimeError, match="stable filesystem origin"):
        handoff_module._runtime_content_root(no_origin, EMBEDDED_SERVICE_HANDOFF)
    lifecycle, _ = load_shared_utilities()
    missing_runtime = replace(EMBEDDED_SERVICE_HANDOFF, runtime_files=("missing.py",))
    with pytest.raises(RuntimeError, match="runtime file is unavailable"):
        handoff_module._runtime_content_root(lifecycle, missing_runtime)

    missing_contract = replace(
        EMBEDDED_SERVICE_HANDOFF,
        public_contracts=(("missing.json", "0" * 64),),
    )
    with pytest.raises(RuntimeError, match="public contract is unavailable"):
        handoff_module._validate_contracts(tmp_path, missing_contract)
    contract_root = tmp_path / "_contract"
    contract_root.mkdir()
    (contract_root / "drift.json").write_text("drift")
    drifted_contract = replace(
        EMBEDDED_SERVICE_HANDOFF,
        public_contracts=(("drift.json", "0" * 64),),
    )
    with pytest.raises(RuntimeError, match="contract root has drifted"):
        handoff_module._validate_contracts(tmp_path, drifted_contract)

    with pytest.raises(TypeError, match="imported module"):
        validate_shared_package(object(), EMBEDDED_SERVICE_HANDOFF)  # type: ignore[arg-type]
    wrong_name = ModuleType("wrong")
    with pytest.raises(RuntimeError, match="import root"):
        validate_shared_package(wrong_name, EMBEDDED_SERVICE_HANDOFF)
    no_origin.__version__ = EMBEDDED_SERVICE_HANDOFF.version
    monkeypatch.setitem(sys.modules, "embedded_service_contract", no_origin)
    with pytest.raises(RuntimeError, match="filesystem origin"):
        validate_shared_package(no_origin, EMBEDDED_SERVICE_HANDOFF)
    monkeypatch.undo()

    stale = replace(EMBEDDED_SERVICE_HANDOFF, runtime_content_root_sha256="0" * 64)
    with pytest.raises(RuntimeError, match="runtime content root"):
        validate_shared_package(lifecycle, stale)
    monkeypatch.setattr(lifecycle, "__all__", tuple(lifecycle.__all__)[:-1])
    with pytest.raises(RuntimeError, match="public surface"):
        validate_shared_package(lifecycle, EMBEDDED_SERVICE_HANDOFF)
    monkeypatch.undo()


def test_runtime_manifest_adapter_root_validation_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import librsi.conformance.manifest as manifest_module

    with pytest.raises(RuntimeError, match="adapter file is unavailable"):
        manifest_module._content_root(tmp_path, ("missing.py",))

    monkeypatch.setattr(manifest_module, "__file__", str(tmp_path / "pkg" / "manifest.py"))
    with pytest.raises(RuntimeError, match="protocol schema is unavailable"):
        manifest_module._adapter_root()
