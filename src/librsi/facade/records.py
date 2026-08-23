"""Typed convenience results that do not replace canonical workflow outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from ..experiments import ExperimentPolicy
from ..hypotheses import HypothesisPolicy
from ..models import CommandObservation
from ..records import Evidence, ExperimentSpec, Hypothesis


@dataclass(frozen=True, init=False)
class HypothesisTestResult:
    """Factory-derived command evidence and its exact hypothesis update."""

    hypothesis: Hypothesis
    experiment: ExperimentSpec
    observation: CommandObservation
    evidence: Evidence
    updated_hypothesis: Hypothesis

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError("HypothesisTestResult values must be created with from_execution()")

    @classmethod
    def from_execution(
        cls,
        *,
        hypothesis: Hypothesis,
        experiment: ExperimentSpec,
        observation: CommandObservation,
        experiment_policy: ExperimentPolicy,
        hypothesis_policy: HypothesisPolicy,
    ) -> HypothesisTestResult:
        """Derive evidence and the update rather than accepting forgeable projections."""

        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("hypothesis test requires a Hypothesis")
        if not isinstance(experiment, ExperimentSpec):
            raise TypeError("hypothesis test requires an ExperimentSpec")
        if not isinstance(observation, CommandObservation):
            raise TypeError("hypothesis test requires a CommandObservation")
        if not isinstance(experiment_policy, ExperimentPolicy):
            raise TypeError("hypothesis test requires an ExperimentPolicy")
        if not isinstance(hypothesis_policy, HypothesisPolicy):
            raise TypeError("hypothesis test requires a HypothesisPolicy")
        if experiment.lineage != (hypothesis.ref,):
            raise ValueError("hypothesis test experiment belongs to another hypothesis")
        evidence = experiment_policy.evaluate_command(spec=experiment, observation=observation)
        updated = hypothesis_policy.apply(hypothesis=hypothesis, evidence=evidence)
        result = object.__new__(cls)
        object.__setattr__(result, "hypothesis", hypothesis)
        object.__setattr__(result, "experiment", experiment)
        object.__setattr__(result, "observation", observation)
        object.__setattr__(result, "evidence", evidence)
        object.__setattr__(result, "updated_hypothesis", updated)
        return result
