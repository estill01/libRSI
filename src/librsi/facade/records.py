"""Typed convenience results that do not replace canonical workflow outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from ..models import CommandObservation
from ..records import Evidence, ExperimentSpec, Hypothesis


@dataclass(frozen=True)
class HypothesisTestResult:
    """One exact command experiment and its evidence-bound hypothesis update."""

    hypothesis: Hypothesis
    experiment: ExperimentSpec
    observation: CommandObservation
    evidence: Evidence
    updated_hypothesis: Hypothesis

    def __post_init__(self) -> None:
        if not isinstance(self.hypothesis, Hypothesis):
            raise TypeError("hypothesis test requires a Hypothesis")
        if not isinstance(self.experiment, ExperimentSpec):
            raise TypeError("hypothesis test requires an ExperimentSpec")
        if not isinstance(self.observation, CommandObservation):
            raise TypeError("hypothesis test requires a CommandObservation")
        if not isinstance(self.evidence, Evidence):
            raise TypeError("hypothesis test requires Evidence")
        if not isinstance(self.updated_hypothesis, Hypothesis):
            raise TypeError("hypothesis test requires an updated Hypothesis")
        if self.experiment.lineage != (self.hypothesis.ref,):
            raise ValueError("hypothesis test experiment belongs to another hypothesis")
        if self.observation.exact_input_root != self.experiment.root:
            raise ValueError("hypothesis test observation belongs to another experiment")
        if (
            self.hypothesis.ref not in self.evidence.subject_refs
            or self.experiment.ref not in self.evidence.source_refs
        ):
            raise ValueError("hypothesis test evidence lost exact experiment lineage")
        if tuple(self.updated_hypothesis.lineage)[-2:] != (
            self.hypothesis.ref,
            self.evidence.ref,
        ):
            raise ValueError("hypothesis test update lost exact evidence lineage")
