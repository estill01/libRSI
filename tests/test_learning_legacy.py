"""Replay canonical traces produced by the previously installed c775bb41 wheel."""

from __future__ import annotations

import json
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from librsi import LocalLearningStore, record_from_dict
from librsi.facade.learning_host import case_from_record
from librsi.identity import thaw
from librsi.reasoning import reasoning_request_from_action

EXAMPLE = runpy.run_path(str(Path(__file__).parents[1] / "examples/adaptive_strategy.py"))
FIXTURES = json.loads((Path(__file__).parent / "fixtures/learning_legacy.json").read_text())


@pytest.mark.parametrize("mode", ["pending", "completed"])
def test_actual_legacy_pending_and_completed_passes_keep_exact_request_shape(tmp_path, mode):
    fixture = FIXTURES["fixtures"][mode]
    with LocalLearningStore(
        tmp_path, profile_id=fixture["profile_id"], initial_configuration={"offsets": [1]}
    ) as store:
        for record in fixture["feedback"]:
            store.record_feedback(record_from_dict(record))
        inputs = record_from_dict(fixture["inputs"])
        store.begin_pass(inputs)
        for transition in fixture["transitions"]:
            state = store.runtime.append(record_from_dict(transition))
        assert state.root == fixture["state_root"]
        if mode == "completed":
            store.finish_pass("legacy", record_from_dict(fixture["native"]))
        shadow = tuple(
            case_from_record(record_from_dict(thaw(row))) for row in inputs.value["shadow"]
        )
        engine = EXAMPLE["make_loop"](store)
        called = []

        class Failed:
            def respond(self, request):
                called.append(request)
                assert request == reasoning_request_from_action(state.pending_actions[0])
                assert (
                    "history" not in request.context
                    and "history_limit" not in request.context["policy"]
                )
                raise OSError("legacy recorded provider failure")

        engine.proposer = Failed()
        result = engine.learn("legacy", shadow_cases=shadow)
        assert result.disposition == "failed" and len(called) == (mode == "pending")
        assert store.pass_input("legacy") == inputs
        assert engine.learn("legacy", shadow_cases=shadow) == result
        history = engine.history()[0]
        assert history.sequence is None and history.reflection is None
        assert all("learning_operation" not in row.metadata for row in history.operations)
        if mode == "completed":
            assert result.native == record_from_dict(fixture["native"])
        engine.policy = replace(engine.policy, reflect_on_failure=True)
        with pytest.raises(ValueError, match="different configuration"):
            engine.learn("legacy", shadow_cases=shadow)
