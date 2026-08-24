from __future__ import annotations

from dataclasses import replace

import pytest

from librsi import (
    APPLY_CANDIDATE_ACTION_KIND,
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    CapabilityRegistry,
    ImprovementResult,
    KnowledgeQuery,
    ManagedBounds,
    ServiceLimits,
    record_from_dict,
)
from librsi.service import LibRSIService
from tests.block14_support import comparison_context
from tests.block15_support import DeterministicCycleProvider
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import DeterministicGovernanceProvider, self_change_request
from tests.block20_support import (
    target_admission,
    validation_request,
    validation_result,
    workflow_cases,
)
from tests.block21_support import (
    AutomaticValidationExperimenter,
    InconclusiveValidationExperimenter,
    ManagedImprovementProvider,
    automatic_admission,
    automatic_validation_admission,
    service,
)


def test_managed_and_external_service_runs_share_exact_canonical_outcomes(tmp_path) -> None:
    request = validation_request()
    managed_provider = AutomaticValidationExperimenter()
    managed = service(tmp_path / "managed", managed_provider)
    managed_admission = automatic_validation_admission()
    managed.submit_target(managed_admission)
    managed.validate(request, admission_id=managed_admission.admission_id)
    execution = managed.run_managed(request.validation_id, ManagedBounds(max_actions=4))
    managed_outcome = managed.get_outcome(request.validation_id)

    external = service(tmp_path / "external")
    external_admission = target_admission()
    external.submit_target(external_admission)
    external.validate(request, admission_id=external_admission.admission_id)
    pending = external.next_actions(request.validation_id)
    action = pending["data"]["action"]
    from librsi import record_from_dict
    from librsi.runtime import Action

    action_record = record_from_dict(action)
    assert type(action_record) is Action
    external.submit_result(
        request.validation_id,
        validation_result(action_record),
        authority="external",
    )
    external_outcome = external.get_outcome(request.validation_id)

    assert execution.stop_reason == "outcome"
    assert execution.terminal is True
    assert managed_provider.calls == 1
    assert managed_outcome["data"]["projection"] == external_outcome["data"]["projection"]
    managed.close()
    external.close()


def test_managed_service_stops_at_bounds_unavailable_capabilities_and_authority(tmp_path) -> None:
    request = validation_request()

    inconclusive_provider = InconclusiveValidationExperimenter()
    bounded = service(tmp_path / "bounded", inconclusive_provider)
    automatic = automatic_validation_admission()
    bounded_request = replace(request, max_evidence_actions=2)
    bounded.submit_target(automatic)
    bounded.start(bounded_request, admission_id=automatic.admission_id)
    execution = bounded.run_managed(
        bounded_request.validation_id,
        ManagedBounds(max_actions=1),
    )
    assert execution.stop_reason == "action-bound"
    assert execution.terminal is False
    assert execution.status == "waiting"
    assert inconclusive_provider.calls == 1
    with pytest.raises(ValueError, match="configured action bound"):
        bounded.run_managed(bounded_request.validation_id, ManagedBounds(max_actions=101))
    bounded.close()

    unavailable = service(tmp_path / "unavailable")
    unavailable.submit_target(automatic)
    unavailable.start(request, admission_id=automatic.admission_id)
    stopped = unavailable.run_managed(request.validation_id, ManagedBounds(max_actions=1))
    assert stopped.stop_reason == "capability-unavailable"
    unavailable.close()

    external = service(tmp_path / "authority")
    admission = target_admission()
    external.submit_target(admission)
    external.start(request, admission_id=admission.admission_id)
    stopped = external.run_managed(request.validation_id, ManagedBounds(max_actions=1))
    assert stopped.stop_reason == "authority-gate"
    with pytest.raises(PermissionError, match="reserved for managed execution"):
        external.submit_result(
            request.validation_id,
            validation_result(
                record_from_dict(external.next_actions(request.validation_id)["data"]["action"])
            ),
            authority="automatic",
        )
    external.close()


def test_managed_improvement_generates_competing_tests_selects_and_iterates(tmp_path) -> None:
    context = comparison_context()
    case = next(item for item in workflow_cases() if item.command == "improve")
    admission = automatic_admission(case.admission)
    cycles = DeterministicCycleProvider(context, (False, True))
    provider = ManagedImprovementProvider(cycles)
    registry = CapabilityRegistry(
        routes=tuple(binding.route() for binding in admission.capabilities),
        implementations=(provider,),
    )
    managed = LibRSIService.local(tmp_path, registry=registry)
    managed.submit_target(admission)
    managed.improve(case.request, admission_id=admission.admission_id)

    execution = managed.run_managed(
        case.request.canonical_run().run_id,
        ManagedBounds(max_actions=4),
    )
    projection = managed.get_outcome(case.request.canonical_run().run_id)["data"]["projection"]
    result = record_from_dict(projection["result"])

    assert execution.stop_reason == "outcome"
    assert type(result) is ImprovementResult
    assert len(result.iterations) == 2
    assert result.iterations[0].selection.disposition == "none-accepted"
    assert result.iterations[0].next_direction == "broaden"
    assert result.iterations[1].selection.disposition == "selected"
    assert all(len(item.proposal.investigation.branches) == 2 for item in result.iterations)
    assert all(
        {branch.status for branch in item.proposal.investigation.branches}
        == {"supported", "rejected"}
        for item in result.iterations
    )
    assert all(item.proposal.investigation.findings for item in result.iterations)
    assert len(cycles.actions) == 2
    managed.close()


def test_managed_rsi_stops_before_apply_then_verifies_and_rolls_back_when_authorized(
    tmp_path,
) -> None:
    context = comparison_context()
    case = next(item for item in workflow_cases() if item.command == "rsi")
    admission = automatic_admission(case.admission)
    request = self_change_request(context, activate=True)
    governance = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        context=context,
        verification="rejected",
    )
    registry = CapabilityRegistry(
        routes=tuple(binding.route() for binding in admission.capabilities),
        implementations=(governance, target),
    )
    managed = LibRSIService.local(
        tmp_path,
        registry=registry,
        current_snapshot_resolver=lambda _expected: target.snapshot,
    )
    managed.submit_target(admission)
    managed.recurse(request, admission_id=admission.admission_id)

    gated = managed.run_managed(
        request.canonical_run().run_id,
        ManagedBounds(max_actions=8),
    )
    assert gated.stop_reason == "application-authority"
    assert gated.terminal is False
    assert target.apply_calls == []

    target.snapshot = replace(context.baseline_snapshot, revision="out-of-band-drift")
    drifted = managed.run_managed(
        request.canonical_run().run_id,
        ManagedBounds(max_actions=8, allow_application=True),
    )
    assert drifted.stop_reason == "currentness-gate"
    assert target.apply_calls == []
    target.snapshot = context.baseline_snapshot

    completed = managed.run_managed(
        request.canonical_run().run_id,
        ManagedBounds(max_actions=8, allow_application=True),
    )
    seen = {
        *(action.kind for action in governance.experiment_actions),
        *(action.kind for action in governance.review_actions),
        *(action.kind for action in target.apply_calls),
        *(action.kind for action in target.verify_calls),
    }
    assert completed.stop_reason == "outcome"
    assert completed.terminal is True
    assert seen == {
        HISTORICAL_EVALUATION_ACTION_KIND,
        FORWARD_SHADOW_ACTION_KIND,
        INDEPENDENT_REVIEW_ACTION_KIND,
        APPLY_CANDIDATE_ACTION_KIND,
        VERIFY_APPLICATION_ACTION_KIND,
        ROLLBACK_APPLICATION_ACTION_KIND,
    }
    assert target.snapshot == context.baseline_snapshot
    assert (
        managed.get_outcome(request.canonical_run().run_id)["data"]["projection"]["workflow"]
        == "rsi"
    )
    managed.close()


def test_service_handles_survive_restart_and_duplicate_results_fail_closed(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    first = service(tmp_path)
    first.submit_target(admission)
    started = first.start(request, admission_id=admission.admission_id)
    pending = first.next_actions(request.validation_id)
    first.close()

    restarted = service(tmp_path)
    assert restarted.get_run(request.validation_id)["state_root"] == started["state_root"]
    assert restarted.next_actions(request.validation_id) == pending
    from librsi import record_from_dict
    from librsi.runtime import Action

    action = record_from_dict(pending["data"]["action"])
    assert type(action) is Action
    result = validation_result(action)
    completed = restarted.submit_result(request.validation_id, result, authority="external")
    assert completed["data"]["terminal"] is True
    with pytest.raises(ValueError, match="does not accept another result"):
        restarted.submit_result(request.validation_id, result, authority="external")
    restarted.close()


def test_service_hosts_multiple_runs_and_bounds_knowledge_and_capability_projection(
    tmp_path,
) -> None:
    provider = AutomaticValidationExperimenter()
    managed = service(tmp_path, provider)
    admission = automatic_validation_admission()
    managed.submit_target(admission)
    first = validation_request()
    second = replace(first, validation_id="external-validation-two")
    managed.start(first, admission_id=admission.admission_id)
    managed.start(second, admission_id=admission.admission_id)
    managed.run_managed(first.validation_id, ManagedBounds(max_actions=2))
    managed.run_managed(second.validation_id, ManagedBounds(max_actions=2))

    assert managed.get_status(first.validation_id)["data"]["terminal"] is True
    assert managed.get_status(second.validation_id)["data"]["terminal"] is True
    capabilities = managed.capabilities()
    assert capabilities["data"]["configured_families"] == ["experimenter"]
    assert "service-secret-must-not-project" not in str(capabilities)
    knowledge = managed.query_knowledge(KnowledgeQuery(limit=2))
    assert knowledge["data"]["count"] <= 2
    with pytest.raises(ValueError, match="configured result limit"):
        small = service(tmp_path / "small", provider)
        try:
            small.limits = ServiceLimits(max_query_results=1)
            small.query_knowledge(KnowledgeQuery(limit=2))
        finally:
            small.close()
    managed.close()


def test_closed_service_fails_readiness_and_operational_calls(tmp_path) -> None:
    managed = service(tmp_path)
    assert managed.health()["data"] == {"status": "ok"}
    assert managed.readiness()["data"] == {"status": "ready"}
    managed.close()
    with pytest.raises(RuntimeError, match="closed"):
        managed.health()
