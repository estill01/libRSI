from __future__ import annotations

import pytest

from librsi import ImprovementWorkflow, LibRSI, SQLiteRuntimeStore, persist_transitions
from librsi.improvement import cycle_request_from_action, make_cycle_failure
from tests.block14_support import comparison_context
from tests.block15_support import DeterministicCycleProvider, improvement_request
from tests.test_block7_runtime_store import _MemoryRuntimeStore


def test_completed_cycle_survives_next_provider_exception_and_sqlite_restart(tmp_path) -> None:
    context = comparison_context()
    request = improvement_request(context, patience=3)
    provider = DeterministicCycleProvider(context, (False,))
    attempted = []

    class InterruptingProvider:
        resource_claim = provider.resource_claim

        def improve_cycle(self, action):
            attempted.append(cycle_request_from_action(action).directive.iteration)
            if len(attempted) == 2:
                raise RuntimeError("second cycle interrupted")
            return provider.improve_cycle(action)

    database = tmp_path / "runtime.sqlite"
    with (
        SQLiteRuntimeStore(database) as store,
        LibRSI(runtime_store=store, improvement_provider=InterruptingProvider()) as library,
    ):
        handle = library.start(request)
        with pytest.raises(RuntimeError, match="second cycle interrupted"):
            handle.run()
        saved = store.resume(handle.state.run.run_id)
        assert saved == handle.state
        assert len(saved.results) == 1
        assert len(handle.progress.iterations) == 1
        first_result = saved.results[0]

    class ResumedProvider:
        resource_claim = provider.resource_claim

        def improve_cycle(self, action):
            attempted.append(cycle_request_from_action(action).directive.iteration)
            return make_cycle_failure(action=action, message="bounded stop", retryable=False)

    with SQLiteRuntimeStore(database) as store:
        workflow = ImprovementWorkflow()
        resumed = workflow.resume(
            request, store.resume(request.canonical_run().run_id), current_snapshot=request.baseline
        )
        completed = workflow.run_managed(
            resumed.progress,
            provider=ResumedProvider(),
            current_snapshot=request.baseline,
            on_update=lambda update: persist_transitions(store, update.transitions),
        )
        assert completed.progress.terminal
        assert completed.progress.state.results[0] == first_result
        assert store.resume(request.canonical_run().run_id) == completed.progress.state
    assert attempted == [1, 2, 2]


def test_failed_persistence_prevents_the_next_provider_effect() -> None:
    context = comparison_context()
    request = improvement_request(context)

    class Store(_MemoryRuntimeStore):
        fail = False

        def append(self, transition):
            if self.fail:
                raise OSError("cannot persist")
            return super().append(transition)

    store = Store()

    class Provider:
        calls = 0

        def resource_claim(self, action):
            return action.budget_reservation["units"]

        def improve_cycle(self, action):
            self.calls += 1
            store.fail = True
            return make_cycle_failure(action=action, message="retry", retryable=True)

    provider = Provider()
    with LibRSI(runtime_store=store, improvement_provider=provider) as library:
        handle = library.start(request)
        initial = handle.state
        with pytest.raises(OSError, match="cannot persist"):
            handle.run()
        assert provider.calls == 1
        assert handle.state == initial
        assert store.load(initial.run.run_id) == initial
