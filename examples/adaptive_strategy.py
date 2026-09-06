"""Consumer template: measured feedback -> governed strategy change -> next task.

Run with an installed libRSI wheel; no optional dependencies or model calls:
    python examples/adaptive_strategy.py --data-dir ./adaptive-demo

Replace IdeaAdapter with your consumer's isolated executor/scorer, FeedbackProposer
with a configured ReasoningBackend, and EvidenceReviewer with independent review.
The orchestration remains unchanged. Each profile gets its own directory.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any

from librsi import (
    Action,
    ActionResult,
    AdaptiveLoop,
    CandidateReview,
    LearningCase,
    LearningPolicy,
    LocalLearningStore,
    Metric,
    ReasoningRequest,
    ReasoningResult,
    TaskMeasurement,
    make_review_result,
    review_command_from_action,
)


class IdeaAdapter:
    """A tiny idea generator with an actual measurable outcome for every task."""

    adapter_id = "integer-idea-adapter-v1"

    def validate_configuration(self, configuration: Mapping[str, Any]) -> None:
        if set(configuration) != {"offsets"} or not configuration["offsets"]:
            raise ValueError("strategy requires nonempty offsets")
        if any(type(value) is not int for value in configuration["offsets"]):
            raise ValueError("strategy offsets must be integers")

    def evaluate(self, configuration: Mapping[str, Any], case: LearningCase) -> TaskMeasurement:
        ideas = [case.payload["base"] + offset for offset in configuration["offsets"]]
        error = min(abs(case.payload["target"] - idea) for idea in ideas)
        return TaskMeasurement(output={"ideas": ideas}, value=error)


class FeedbackProposer:
    """Derive competing revisions from observed task needs, without a canned decision.

    A model-backed ReasoningBackend receives the same active configuration, objective,
    actual task inputs, generated ideas, scores, and producing strategy identities.
    It returns hypotheses; libRSI owns every subsequent acceptance decision.
    """

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        offsets = sorted(
            {item["case"]["target"] - item["case"]["base"] for item in request.context["feedback"]}
        )
        alternatives = (offsets, [max(offsets)])
        return ReasoningResult.propose(
            request=request,
            content={
                "hypotheses": [
                    {
                        "statement": f"Generate ideas at observed offsets {values}",
                        "causal_model": {"configuration": {"offsets": values}},
                        "predictions": [{"error": "decrease"}],
                        "confidence": 0.6,
                    }
                    for values in alternatives
                ]
            },
        )


class EvidenceReviewer:
    """Independent deterministic review for this fully specified numerical domain."""

    def review(self, action: Action) -> ActionResult:
        command = review_command_from_action(action)
        passes = command.evaluation.disposition == "passed"
        return make_review_result(
            action=action,
            review=CandidateReview(
                review_id=f"{action.action_id}:review",
                reviewer_id="idea-reviewer-v1",
                candidate=command.candidate,
                experiment=command.experiment,
                evaluation=command.evaluation,
                disposition="accepted" if passes else "rejected",
                findings=("Held-out measured criterion passes" if passes else "Criterion failed",),
                lineage=(command.candidate.ref, command.experiment.ref, command.evaluation.ref),
            ),
        )


class DemoPause(BaseException):
    """Simulate process interruption at a durable, not-yet-executed proposal action."""


class PausedProposer(FeedbackProposer):
    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        raise DemoPause()


def make_loop(store: LocalLearningStore, *, pause: bool = False) -> AdaptiveLoop:
    return AdaptiveLoop(
        store,
        adapter=IdeaAdapter(),
        proposer=PausedProposer() if pause else FeedbackProposer(),
        proposer_id="feedback-proposer-v1",
        reviewer=EvidenceReviewer(),
        reviewer_id="idea-reviewer-v1",
        policy=LearningPolicy(
            objective="Reduce error of generated ideas",
            metric=Metric(metric_id="error", direction="decrease", unit="distance"),
            minimum_effect=0.5,
            min_new_feedback=2,
            max_feedback=2,
            max_cases=2,
            max_candidates=2,
        ),
    )


def run_demo(directory: Path, *, profile_id: str = "idea-generator") -> dict[str, Any]:
    training = (
        LearningCase("ordinary-a", {"base": 0, "target": 3}),
        LearningCase("ordinary-b", {"base": 10, "target": 14}),
    )
    shadow = (
        LearningCase("held-out-a", {"base": 20, "target": 25}),
        LearningCase("held-out-b", {"base": 30, "target": 36}),
    )
    with LocalLearningStore(
        directory, profile_id=profile_id, initial_configuration={"offsets": [1]}
    ) as store:
        engine = make_loop(store, pause=True)
        feedback = tuple(engine.run_task(case) for case in training)
        baseline = feedback[0].target_snapshot
        assert baseline is not None
        with suppress(DemoPause):
            engine.learn("learn-1", shadow_cases=shadow, activate=True)
    with LocalLearningStore(directory, profile_id=profile_id) as store:
        resumed = store.pending_pass == "learn-1"
        result = make_loop(store).learn("learn-1", shadow_cases=shadow, activate=True)
        if result is None or not result.adopted or result.strategy_after == baseline:
            raise RuntimeError("the native workflow did not adopt a changed strategy")
    # A distinct ordinary task after another reopen must use the adopted revision.
    with LocalLearningStore(directory, profile_id=profile_id) as store:
        next_task = make_loop(store).run_task(
            LearningCase("ordinary-next", {"base": 40, "target": 44})
        )
        if (
            next_task.target_snapshot != result.strategy_after
            or store.active != result.strategy_after
        ):
            raise RuntimeError("the next task did not use the accepted strategy")
        return {
            "profile": profile_id,
            "resumed_saved_pass": resumed,
            "native_disposition": result.disposition,
            "native_result_root": result.native.root,
            "baseline_root": baseline.root,
            "active_root": store.active.root,
            "configuration": dict(store.active.state),
            "initial_errors": [item.value["value"] for item in feedback],
            "next_task_strategy_root": next_task.target_snapshot.root,
            "next_task_error": next_task.value["value"],
            "next_task_ideas": list(next_task.value["output"]["ideas"]),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--profile", default="idea-generator")
    args = parser.parse_args()
    print(json.dumps(run_demo(args.data_dir, profile_id=args.profile), indent=2))
