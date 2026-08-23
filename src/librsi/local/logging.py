"""Structured Python logging over canonical transitions."""

from __future__ import annotations

import logging

from ..runtime import Transition


class LoggingTransitionSink:
    """Attach canonical transition fields to a standard-library LogRecord."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        if logger is not None and not isinstance(logger, logging.Logger):
            raise TypeError("transition logger must be a logging.Logger")
        self._logger = logging.getLogger("librsi.local") if logger is None else logger

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    def emit(self, transition: Transition) -> None:
        if not isinstance(transition, Transition):
            raise TypeError("structured logging requires a Transition")
        event = transition.event
        self._logger.info(
            "librsi transition",
            extra={
                "librsi_transition": {
                    "run_id": transition.next_state.run.run_id,
                    "sequence": event.sequence,
                    "kind": event.kind,
                    "event_root": event.root,
                    "transition_root": transition.root,
                    "state_root": transition.next_state.root,
                }
            },
        )
