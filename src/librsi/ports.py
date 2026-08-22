from __future__ import annotations

from typing import Protocol

from .models import CommandExperimentInput, CommandObservation


class ExperimentRunner(Protocol):
    """Host effect port for executing an exact experiment input.

    Canonical command runners must copy ``experiment.exact_input_root`` into the
    returned ``CommandObservation.exact_input_root``. The evaluator rejects missing
    or mismatched roots so observations cannot be paired with a different spec.
    """

    def run(
        self, experiment: CommandExperimentInput, *, timeout_seconds: int
    ) -> CommandObservation: ...
