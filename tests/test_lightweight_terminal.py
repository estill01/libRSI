from __future__ import annotations

import pytest

from librsi import CapabilityRegistry, LibRSI, ManagedBounds, record_from_dict
from librsi.runtime import ActionResult, RuntimeFailure
from librsi.service import LibRSIService
from tests.block20_support import workflow_cases
from tests.block21_support import automatic_admission


@pytest.fixture(scope="module")
def cases():
    return {case.command: case for case in workflow_cases()}


@pytest.mark.parametrize(
    ("workflow", "disposition"),
    [(name, "failed") for name in ("validate", "investigate", "improve", "rsi")]
    + [(name, "cancelled") for name in ("validate", "investigate", "improve")],
)
def test_terminal_failure_remains_retrievable_after_restart(
    tmp_path, cases, workflow, disposition
) -> None:
    case = cases[workflow]
    failure = RuntimeFailure(
        classification="cancelled" if disposition == "cancelled" else "execution",
        message="bounded terminal failure",
    )
    with LibRSIService.local(tmp_path) as service:
        service.submit_target(case.admission)
        started = service.start(case.request, admission_id=case.admission.admission_id)
        run_id = started["run_id"]
        action = record_from_dict(service.next_actions(run_id)["data"]["action"])
        failed = ActionResult(action=action, disposition=disposition, failure=failure)
        status = service.submit_result(run_id, failed, authority="external")["data"]
        assert status["terminal"] is True
        assert status["status"] == disposition
        assert status["pending_action_roots"] == []
        assert status["failures"][-1] == failure.to_dict()
        outcome = service.get_outcome(run_id)
        if workflow == "improve":
            assert outcome["data"]["projection"] is None
            assert outcome["data"]["failures"][-1] == failure.to_dict()
            assert record_from_dict(outcome["data"]["outcome"]).status == disposition

    with LibRSIService.local(tmp_path) as restarted:
        assert restarted.get_outcome(run_id) == outcome
        stopped = restarted.run_managed(run_id, ManagedBounds(max_actions=1))
        assert stopped.terminal and stopped.stop_reason == "outcome"
        assert stopped.executed_action_roots == ()
        with pytest.raises(ValueError, match="terminal; use outcome"):
            restarted.next_actions(run_id)
        with pytest.raises(ValueError, match="does not accept another result"):
            restarted.submit_result(run_id, failed, authority="external")

    library = (
        LibRSI(
            capability_registry=CapabilityRegistry(
                routes=tuple(item.route() for item in case.admission.capabilities)
            )
        )
        if workflow == "rsi"
        else LibRSI()
    )
    with library:
        handle = library.start(case.request, current_snapshot=case.admission.target_snapshot)
        handle.submit(failed)
        assert handle.terminal and handle.next() is None
        assert handle.state.status == status["status"]


def test_managed_improvement_failure_stops_without_another_provider_call(tmp_path, cases) -> None:
    case = cases["improve"]
    admission = automatic_admission(case.admission)

    class Provider:
        calls = 0

        def reason(self, action):
            self.calls += 1
            return ActionResult(
                action=action,
                disposition="failed",
                failure=RuntimeFailure(classification="execution", message="provider failed"),
            )

    provider = Provider()
    registry = CapabilityRegistry(
        routes=tuple(item.route() for item in admission.capabilities), implementations=(provider,)
    )
    with LibRSIService.local(tmp_path, registry=registry) as service:
        service.submit_target(admission)
        run_id = service.start(case.request, admission_id=admission.admission_id)["run_id"]
        for _ in range(2):
            result = service.run_managed(run_id, ManagedBounds(max_actions=2))
            assert result.terminal and result.status == "failed"
        assert provider.calls == 1


def test_retryable_improvement_remains_waiting(tmp_path, cases) -> None:
    case = cases["improve"]
    with LibRSIService.local(tmp_path) as service:
        service.submit_target(case.admission)
        run_id = service.start(case.request, admission_id=case.admission.admission_id)["run_id"]
        action = record_from_dict(service.next_actions(run_id)["data"]["action"])
        status = service.submit_result(
            run_id,
            ActionResult(
                action=action,
                disposition="failed",
                failure=RuntimeFailure(
                    classification="execution", message="try again", retryable=True
                ),
            ),
            authority="external",
        )["data"]
        assert status["terminal"] is False and status["pending_action_roots"]
        with pytest.raises(ValueError, match="no terminal outcome"):
            service.get_outcome(run_id)
