from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .errors import RSITransitionError
from .evaluation import ExperimentEvaluator
from .identity import digest, thaw
from .models import (
    CommandExperimentInput,
    CommandObservation,
    EvidenceType,
    ExperimentDisposition,
    ExperimentEvaluation,
)
from .records import (
    DecisionRule,
    Evidence,
    ExperimentSpec,
    Hypothesis,
    Metric,
    RecordRef,
    TargetRef,
    TargetSnapshot,
)

_COMMAND_CRITERIA = frozenset({"accepted_exit_codes", "stdout_contains", "stderr_not_contains"})


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _require_exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if value == "":
        raise ValueError(f"{label} is required")
    return value


def _optional_mapping(value: Mapping[str, Any] | None, label: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _normalize_command(command: Sequence[str]) -> tuple[str, ...]:
    if isinstance(command, (str, bytes, bytearray)) or not isinstance(command, Sequence):
        raise TypeError("command experiment argv must be a sequence of strings")
    result: list[str] = []
    for index, part in enumerate(command):
        if not isinstance(part, str):
            raise TypeError("command experiment argv must contain only strings")
        if index == 0 and part == "":
            raise ValueError("command experiment executable is required")
        result.append(part)
    if not result:
        raise ValueError("command experiment requires a nonempty argv")
    return tuple(result)


def _measurement_names(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("requested measurements must be a sequence of strings")
    measurements = tuple(_require_text(item, "requested measurement") for item in value)
    if not measurements:
        raise ValueError("command experiments require at least one requested measurement")
    return measurements


def _string_sequence(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{label} must contain only strings")
        if item == "":
            raise ValueError(f"{label} cannot contain empty strings")
        result.append(item)
    return tuple(result)


def _exit_codes(value: Any) -> tuple[int, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("accepted_exit_codes must be a sequence of integers")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise TypeError("accepted_exit_codes must contain only integers")
        result.append(item)
    if not result:
        raise ValueError("accepted_exit_codes cannot be empty")
    return tuple(result)


def _validate_command_criteria(
    criteria: Mapping[str, Any],
) -> tuple[tuple[int, ...], tuple[str, ...], tuple[str, ...]]:
    if not isinstance(criteria, Mapping) or not criteria:
        raise ValueError("command experiment success criteria are required")
    unknown = sorted(set(criteria) - _COMMAND_CRITERIA)
    if unknown:
        raise ValueError(f"unsupported command success criteria: {', '.join(unknown)}")
    accepted_codes = _exit_codes(criteria.get("accepted_exit_codes", (0,)))
    required_stdout = _string_sequence(criteria.get("stdout_contains", ()), "stdout_contains")
    forbidden_stderr = _string_sequence(
        criteria.get("stderr_not_contains", ()),
        "stderr_not_contains",
    )
    return accepted_codes, required_stdout, forbidden_stderr


def _validate_observation(observation: CommandObservation, *, expected_input_root: str) -> None:
    if not isinstance(observation, CommandObservation):
        raise TypeError("command evaluation requires a CommandObservation")
    if not isinstance(observation.invalid, bool):
        raise TypeError("command observation invalid must be a boolean")
    if observation.exit_code is not None and (
        isinstance(observation.exit_code, bool) or not isinstance(observation.exit_code, int)
    ):
        raise TypeError("command observation exit_code must be an integer or None")
    if not isinstance(observation.stdout, str) or not isinstance(observation.stderr, str):
        raise TypeError("command observation stdout and stderr must be strings")
    if observation.exact_input_root is None:
        raise ValueError("canonical command observations require the exact input root")
    if not isinstance(observation.exact_input_root, str):
        raise TypeError("command observation exact_input_root must be a string")
    if observation.exact_input_root != expected_input_root:
        raise ValueError("command observation does not match the exact experiment input")


def _command_spec_context(
    spec: ExperimentSpec,
) -> tuple[
    RecordRef,
    tuple[str, ...],
    str,
    tuple[int, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    if not isinstance(spec, ExperimentSpec):
        raise TypeError("command execution requires an ExperimentSpec")
    if spec.kind != "command":
        raise RSITransitionError("experiment is not a command experiment")
    if spec.target_snapshot is None:
        raise ValueError("canonical command experiments require a target snapshot")
    if not spec.design:
        raise ValueError("canonical command experiments require a nonempty design")
    _measurement_names(spec.requested_measurements)

    hypothesis_refs = tuple(ref for ref in spec.lineage if ref.record_type == "hypothesis")
    if len(hypothesis_refs) != 1:
        raise ValueError("canonical command experiments require exactly one hypothesis reference")

    accepted_codes, required_stdout, forbidden_stderr = _validate_command_criteria(spec.criteria)
    command = spec.inputs.get("command")
    cwd = spec.inputs.get("cwd")
    if not isinstance(command, tuple):
        raise ValueError("command ExperimentSpec is missing canonical argv")
    argv = _normalize_command(command)
    if not isinstance(cwd, str):
        raise ValueError("command ExperimentSpec is missing canonical cwd")
    working_directory = _require_exact_text(cwd, "command working directory")
    return (
        hypothesis_refs[0],
        argv,
        working_directory,
        accepted_codes,
        required_stdout,
        forbidden_stderr,
    )


@dataclass(frozen=True)
class ExperimentPolicy:
    """Design and interpretation policy for falsifying experiments.

    The canonical Block 2 path is ``design_command`` → ``prepare_command`` →
    ``evaluate_command``. Evaluation consumes the immutable ``ExperimentSpec`` itself;
    there is no evaluation-time criteria argument that can replace the reviewed design.
    The returned host execution input and host observation also carry the exact spec root,
    preventing an observation from one command/spec from being evaluated as another.

    ``command_input`` and ``evaluate_command_result`` remain deprecated ``0.2.0``
    compatibility wrappers. They intentionally preserve their historical signatures and
    hashes and therefore do not provide the stronger canonical referential guarantees.
    """

    conclusive_evidence_weight: float = 0.7

    @staticmethod
    def validate_design(*, design: Mapping[str, Any], success_criteria: Mapping[str, Any]) -> None:
        """Legacy broad design validation retained for compatibility."""

        if not design or not success_criteria:
            raise ValueError("experiment design and success criteria are required")

    def design_command(
        self,
        *,
        experiment_id: str,
        hypothesis: Hypothesis,
        target_snapshot: TargetSnapshot,
        design: Mapping[str, Any],
        success_criteria: Mapping[str, Any],
        command: Sequence[str],
        cwd: str,
        inputs: Mapping[str, Any] | None = None,
        environment: Mapping[str, Any] | None = None,
        requested_measurements: Sequence[str] = ("command.passed",),
    ) -> ExperimentSpec:
        """Create an exact immutable command experiment bound to a hypothesis.

        Command argv/cwd are preserved byte-for-byte as Python strings rather than
        normalized, while design, criteria, target snapshot, additional inputs,
        environment requirements, requested measurements, and the exact hypothesis
        version are all identity-bearing content of the returned ``ExperimentSpec``.
        """

        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("command experiments require a canonical Hypothesis")
        if not isinstance(hypothesis.target, TargetRef):
            raise ValueError("command experiment hypotheses require an exact target")
        if not isinstance(target_snapshot, TargetSnapshot):
            raise TypeError("command experiments require an exact TargetSnapshot")
        if target_snapshot.target != hypothesis.target:
            raise ValueError("experiment target snapshot does not match the hypothesis target")
        if not isinstance(design, Mapping) or not design:
            raise ValueError("experiment design is required")

        _validate_command_criteria(success_criteria)
        argv = _normalize_command(command)
        working_directory = _require_exact_text(cwd, "command working directory")
        parameters = _optional_mapping(inputs, "command experiment inputs")
        environment_requirements = _optional_mapping(
            environment,
            "command experiment environment",
        )
        measurement_names = _measurement_names(requested_measurements)
        if "command.passed" not in measurement_names:
            raise ValueError("command experiments must request the command.passed Metric")
        command_metrics = tuple(
            Metric(
                metric_id=name,
                direction="increase" if name == "command.passed" else "target",
                role="objective" if name == "command.passed" else "diagnostic",
            )
            for name in measurement_names
        )
        command_metric = next(
            item for item in command_metrics if item.metric_id == "command.passed"
        )
        command_rule = DecisionRule(
            metric=command_metric.ref,
            kind="threshold",
            operator=">=",
            threshold=1.0,
        )

        return ExperimentSpec(
            experiment_id=_require_text(experiment_id, "experiment id"),
            kind="command",
            target_snapshot=target_snapshot,
            design=design,
            criteria=success_criteria,
            inputs={
                "command": list(argv),
                "cwd": working_directory,
                "parameters": parameters,
            },
            environment=environment_requirements,
            requested_measurements=measurement_names,
            metrics=command_metrics,
            decision_rules=(command_rule,),
            repetitions=1,
            validity_requirements={"require_all_metrics": False},
            lineage=(hypothesis.ref,),
        )

    @staticmethod
    def prepare_command(spec: ExperimentSpec) -> CommandExperimentInput:
        """Materialize host execution input from a fully bound command spec."""

        _, argv, working_directory, _, _, _ = _command_spec_context(spec)
        return CommandExperimentInput(spec.root, argv, working_directory)

    def evaluate_command(
        self,
        *,
        spec: ExperimentSpec,
        observation: CommandObservation,
    ) -> Evidence:
        """Interpret an exactly correlated observation using the criteria in ``spec``.

        The resulting evidence names the exact hypothesis version from the experiment
        lineage, the exact experiment spec as its source, and the exact target snapshot.
        Infrastructure-invalid observations become zero-weight null evidence.
        """

        (
            hypothesis_ref,
            _,
            _,
            accepted_codes,
            required_stdout,
            forbidden_stderr,
        ) = _command_spec_context(spec)
        _validate_observation(observation, expected_input_root=spec.root)
        self._validate_evidence_weight()
        if spec.metrics:
            ExperimentEvaluator.projection(spec)

        passed = (
            not observation.invalid
            and observation.exit_code in accepted_codes
            and all(value in observation.stdout for value in required_stdout)
            and all(value not in observation.stderr for value in forbidden_stderr)
        )
        disposition: ExperimentDisposition = (
            "invalid" if observation.invalid else "passed" if passed else "failed"
        )
        evidence_type: EvidenceType
        if disposition == "passed":
            evidence_type = "support"
            evidence_weight = float(self.conclusive_evidence_weight)
        elif disposition == "failed":
            evidence_type = "counterexample"
            evidence_weight = float(self.conclusive_evidence_weight)
        else:
            evidence_type = "null"
            evidence_weight = 0.0

        return Evidence(
            evidence_type=evidence_type,
            data={
                "experiment_root": spec.root,
                "observation_input_root": observation.exact_input_root,
                "passed": passed,
                "disposition": disposition,
                "exit_code": observation.exit_code,
                "stdout": observation.stdout,
                "stderr": observation.stderr,
                "criteria": thaw(spec.criteria),
            },
            subject_refs=(hypothesis_ref,),
            source_refs=(spec.ref,),
            target_snapshot=spec.target_snapshot,
            weight=evidence_weight,
        )

    def _validate_evidence_weight(self) -> None:
        value = self.conclusive_evidence_weight
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("conclusive evidence weight must be numeric")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("conclusive evidence weight must be between zero and one")

    @staticmethod
    def command_input(
        *,
        experiment_id: str,
        experiment_type: str,
        status: str,
        design: Mapping[str, Any],
        success_criteria: Mapping[str, Any],
        command: Sequence[str],
        cwd: str,
    ) -> CommandExperimentInput:
        """Deprecated ``0.2.0`` command-input wrapper preserving legacy identity."""

        warnings.warn(
            "ExperimentPolicy.command_input() is a legacy compatibility wrapper; "
            "use design_command() and prepare_command() for immutable criteria binding",
            DeprecationWarning,
            stacklevel=2,
        )
        if experiment_type != "command":
            raise RSITransitionError("experiment is not a command experiment")
        if status != "designed":
            raise RSITransitionError("experiment is not awaiting execution")
        normalized_command = tuple(str(part) for part in command)
        if not normalized_command or any(not part for part in normalized_command):
            raise ValueError("command experiment requires a nonempty argv")
        exact_input_root = digest(
            {
                "experiment_id": experiment_id,
                "design": dict(design),
                "success_criteria": dict(success_criteria),
                "command": list(normalized_command),
                "cwd": cwd,
            }
        )
        return CommandExperimentInput(exact_input_root, normalized_command, cwd)

    def evaluate_command_result(
        self,
        *,
        exact_input_root: str,
        success_criteria: Mapping[str, Any],
        observation: CommandObservation,
    ) -> ExperimentEvaluation:
        """Deprecated ``0.2.0`` evaluation wrapper preserving legacy behavior."""

        warnings.warn(
            "ExperimentPolicy.evaluate_command_result() is a legacy compatibility wrapper; "
            "use evaluate_command(spec=..., observation=...) so criteria cannot be replaced",
            DeprecationWarning,
            stacklevel=2,
        )
        accepted_codes = success_criteria.get("accepted_exit_codes", [0])
        passed = (
            not observation.invalid
            and isinstance(accepted_codes, list)
            and observation.exit_code in accepted_codes
        )
        required_stdout = success_criteria.get("stdout_contains", [])
        forbidden_stderr = success_criteria.get("stderr_not_contains", [])
        if isinstance(required_stdout, list):
            passed = passed and all(str(value) in observation.stdout for value in required_stdout)
        if isinstance(forbidden_stderr, list):
            passed = passed and all(
                str(value) not in observation.stderr for value in forbidden_stderr
            )
        disposition: ExperimentDisposition = (
            "invalid" if observation.invalid else "passed" if passed else "failed"
        )
        evidence_root = digest(
            {
                "input_root": exact_input_root,
                "exit_code": observation.exit_code,
                "stdout": observation.stdout,
                "stderr": observation.stderr,
                "disposition": disposition,
            }
        )
        evidence_type: EvidenceType
        if disposition == "passed":
            evidence_type = "support"
            evidence_weight = self.conclusive_evidence_weight
        elif disposition == "failed":
            evidence_type = "counterexample"
            evidence_weight = self.conclusive_evidence_weight
        else:
            # Infrastructure failure is not evidence against the hypothesis.
            evidence_type = "null"
            evidence_weight = 0.0
        return ExperimentEvaluation(
            passed=passed,
            disposition=disposition,
            evidence_root=evidence_root,
            measurement={"passed": passed, "criteria": dict(success_criteria)},
            hypothesis_evidence_type=evidence_type,
            hypothesis_evidence_weight=evidence_weight,
        )
