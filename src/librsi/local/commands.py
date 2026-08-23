"""Authority-scoped local execution for canonical command experiments."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

from ..models import CommandExperimentInput, CommandObservation


def _roots(values: Sequence[str | Path]) -> tuple[Path, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise TypeError("allowed command roots must be a sequence")
    roots = tuple(Path(value).expanduser().resolve() for value in values)
    if not roots:
        raise ValueError("local command execution requires an allowed root")
    if any(not item.is_dir() for item in roots):
        raise ValueError("every allowed command root must identify a directory")
    return tuple(dict.fromkeys(roots))


def _output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


class LocalCommandRunner:
    """Run argv directly, never through a shell, under explicit cwd authority."""

    def __init__(self, *, allowed_roots: Sequence[str | Path]) -> None:
        self._allowed_roots = _roots(allowed_roots)

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        return self._allowed_roots

    def run(
        self,
        experiment: CommandExperimentInput,
        *,
        timeout_seconds: int,
    ) -> CommandObservation:
        if not isinstance(experiment, CommandExperimentInput):
            raise TypeError("local command execution requires CommandExperimentInput")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int):
            raise TypeError("command timeout must be an integer")
        if timeout_seconds <= 0:
            raise ValueError("command timeout must be positive")
        cwd = Path(experiment.cwd).expanduser().resolve()
        if not cwd.is_dir():
            raise ValueError("command working directory must identify a directory")
        if not any(cwd == root or cwd.is_relative_to(root) for root in self._allowed_roots):
            raise PermissionError("command working directory is outside configured authority")
        try:
            completed = subprocess.run(
                experiment.command,
                cwd=cwd,
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as error:
            return CommandObservation(
                exit_code=None,
                stdout=_output(error.stdout),
                stderr=_output(error.stderr) or "command timed out",
                invalid=True,
                exact_input_root=experiment.exact_input_root,
            )
        except OSError as error:
            return CommandObservation(
                exit_code=None,
                stdout="",
                stderr=str(error),
                invalid=True,
                exact_input_root=experiment.exact_input_root,
            )
        return CommandObservation(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            exact_input_root=experiment.exact_input_root,
        )
