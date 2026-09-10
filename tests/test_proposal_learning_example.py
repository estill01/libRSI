from __future__ import annotations

import json
import runpy
from dataclasses import replace
from pathlib import Path

import pytest

from librsi import LearningCase, ReasoningRequest, ReasoningResult, TaskMeasurement
from librsi.identity import canonical_json

DEMO = runpy.run_path(str(Path(__file__).parents[1] / "examples/failure_informed_proposals.py"))


def test_generator_receives_observations_and_score_depends_on_actual_probe_execution():
    adapter = DEMO["ProposalAdapter"]()
    case = DEMO["make_case"]("ordinary", 2, 3)
    original = adapter.evaluate(DEMO["BASE_GENERATOR"], case)
    improved = adapter.evaluate({"family": "affine", "estimator": "pair"}, case)
    assert original.value == 0 and improved.value == 0.5
    assert set(improved.output["generator_input"]) == {"baseline_program", "observations", "budget"}
    assert "probes" not in improved.output["generator_input"]
    assert improved.output["evaluated"][0]["outputs"] == (25.0, 29.0)
    # Keep generation inputs unchanged but change scoring answers. No canned score.
    changed = LearningCase(
        "changed-probes", {**case.payload, "probes": [{"x": 11, "y": -999}, {"x": 13, "y": -998}]}
    )
    assert adapter.evaluate({"family": "affine", "estimator": "pair"}, changed).value == 0


@pytest.mark.parametrize(
    "bad", [{}, {"slope": True, "intercept": 3}, {"slope": float("nan"), "intercept": 3}]
)
def test_bad_proposals_cannot_inflate_the_score_or_poison_canonical_output(bad):
    value, output = DEMO["score"](
        [bad, {"slope": 2, "intercept": 3}], DEMO["make_case"]("case", 2, 3)
    )
    assert value == 0.5 and output["evaluated"][0]["status"] == "invalid"
    TaskMeasurement(output, value)


def test_duplicate_equivalent_or_extra_programs_do_not_get_more_credit():
    good = {"slope": 2, "intercept": 3}
    case = DEMO["make_case"]("case", 2, 3)
    for second in (good, {"slope": 2.0, "intercept": 3.0}, {"slope": 2, "intercept": 3 + 1e-12}):
        value, output = DEMO["score"]([good, second], case)
        assert value == 0.5 and output["evaluated"][1]["status"] == "duplicate"
    assert DEMO["score"]([good] * 3, case)[0] == 0
    assert DEMO["score"]([], case)[0] == 0


def test_measured_residuals_drive_reflection_and_valid_ablation_not_pass_identity(tmp_path):
    from librsi import LocalLearningStore

    adapter = DEMO["ProposalAdapter"]()
    cases = (DEMO["make_case"]("a", 2, 3), DEMO["make_case"]("b", 3, -2))
    trials = []
    for estimator in ("mean", "last"):
        configuration = {"family": "offset", "estimator": estimator}
        for case in cases:
            measured = adapter.evaluate(configuration, case)
            trials.append(
                {
                    "configuration": configuration,
                    "case_id": case.case_id,
                    "value": measured.value,
                    "output": measured.output,
                    "status": "measured",
                }
            )
    history = [{"trials": trials, "baseline_configuration": DEMO["BASE_GENERATOR"]}]
    assert DEMO["diagnose"](history)["test_affine"]
    # Mere rejected history is insufficient if measured residuals are constant.
    flat = json.loads(canonical_json(history))
    for trial in flat[0]["trials"]:
        trial["output"]["generator_input"]["observations"] = [
            {"x": x, "y": x + 3} for x in (1, 3, 5)
        ]
    assert not DEMO["diagnose"](flat)["test_affine"]
    with LocalLearningStore(
        tmp_path, profile_id="reasoning", initial_configuration=DEMO["BASE_GENERATOR"]
    ) as store:
        feedback = [DEMO["make_loop"](store).run_task(case) for case in cases]
        refs = (store.active.ref, *(row.ref for row in feedback))
        context = {
            "configuration": store.active.state,
            "history": history,
            "feedback": [{"feedback": row.root, "output": row.value["output"]} for row in feedback],
        }
        request = ReasoningRequest(
            request_id="any-id",
            kind="reflection",
            instruction="Inspect measurements",
            input_refs=refs,
            lineage=refs,
            target_snapshot=store.active,
            context=context,
        )
        backend = DEMO["FailureInformedProposer"]()
        reflection = backend.respond(request)
        proposal_request = replace(
            request,
            request_id="proposal",
            kind="hypothesis-generation",
            context={**context, "reflection": reflection.content},
        )
        result = backend.respond(proposal_request)
        renamed = backend.respond(replace(proposal_request, request_id="entirely-different"))
        assert result.content == renamed.content
        assert all(
            row["causal_model"]["configuration"]["family"] == "affine"
            for row in result.content["hypotheses"]
        )
        control = DEMO["counterfactual"](proposal_request)
        assert isinstance(control, ReasoningResult)
        assert all(
            row["causal_model"]["configuration"]["family"] == "offset"
            for row in control.content["hypotheses"]
        )
        assert len(control.content["hypotheses"]) == 2
        json.dumps(control.to_dict(), allow_nan=False)
