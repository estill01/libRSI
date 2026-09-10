"""Bounded native history and a deliberately separate proposer-safe projection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from ..identity import thaw
from ..reasoning import ReasoningResult, reasoning_result_from_action_result
from ..records import Observation, record_from_dict
from ..runtime import ActionResult
from .learning_host import case_from_record
from .learning_records import TaskMeasurement
from .learning_requests import proposal_request, reasoning_run, reflection_request
from .learning_results import LearningResult, LearningTerminal, learning_result
from .learning_store import LearningStore


def ordered_inputs(store: LearningStore) -> tuple[Observation, ...]:
    """Legacy order is unknown; new passes carry an explicit logical sequence."""
    rows: list[Observation] = []
    sequences: set[int] = set()
    ids = store.pass_ids
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate learning pass identity")
    for pass_id in ids:
        inputs = store.pass_input(pass_id)
        if (
            not isinstance(inputs, Observation)
            or inputs.kind != "learning.pass"
            or inputs.value["pass_id"] != pass_id
            or inputs.target_snapshot is None
            or inputs.target_snapshot.target != store.target
        ):
            raise ValueError("learning history input belongs to another pass or profile")
        sequence = inputs.value.get("sequence")
        version = inputs.value.get("learning_version")
        if version is not None and (type(version) is not int or version != 2):
            raise ValueError("unsupported learning history version")
        if version == 2 or "sequence" in inputs.value:
            if type(sequence) is not int or sequence <= 0 or sequence in sequences:
                raise ValueError("learning history sequence is invalid or ambiguous")
            sequences.add(sequence)
        rows.append(inputs)
    return tuple(
        sorted(rows, key=lambda item: (item.value.get("sequence", 0), item.value["pass_id"]))
    )


@dataclass(frozen=True)
class LearningAttempt:
    """Operator view; native results/operations can contain held-out material.

    Only ``feedback`` is intended for proposal context. Historical success never
    asserts that this revision is still active. Legacy missing costs are unknown.
    """

    inputs: Observation
    result: LearningResult | None
    proposal: ReasoningResult | None
    reflection: ReasoningResult | None
    operations: tuple[ActionResult, ...]
    measurements: tuple[Observation, ...]

    @property
    def pass_id(self) -> str:
        return self.inputs.value["pass_id"]

    @property
    def sequence(self) -> int | None:
        return self.inputs.value.get("sequence")

    @property
    def disposition(self) -> str:
        return "pending" if self.result is None else self.result.disposition

    @property
    def feedback(self) -> Observation:
        """Training-only data and safe disposition codes; no terminal-tree dump."""
        baseline = self.inputs.target_snapshot
        assert baseline is not None
        configuration = self.inputs.value["configuration"]
        cases = {
            record_from_dict(thaw(value)).ref: case_from_record(
                cast(Observation, record_from_dict(thaw(value)))
            )
            for value in self.inputs.value["training"]
        }
        trials = []
        for observation in self.measurements:
            case = cases[observation.source_refs[2]]
            snapshot = observation.target_snapshot
            assert snapshot is not None
            row = {
                "case_id": case.case_id,
                "case": case.payload,
                "configuration": snapshot.state,
                "strategy_root": snapshot.root,
                "measurement_root": observation.root,
                "status": "measured" if observation.kind == "learning.measurement" else "failed",
            }
            if observation.kind == "learning.measurement":
                row.update(output=observation.value["output"], value=observation.value["value"])
            # Error/review messages may quote held-out data. Never forward them.
            trials.append(row)
        refs = [self.inputs.ref]
        if self.result is not None:
            refs.append(self.result.native.ref)
        if self.proposal is not None:
            refs.append(self.proposal.ref)
        refs.extend(item.ref for item in self.measurements)
        return Observation(
            kind="learning.attempt-feedback",
            target_snapshot=baseline,
            value={
                "pass_id": self.pass_id,
                "sequence": self.sequence,
                "disposition": self.disposition,
                "adapter_id": configuration["adapter_id"],
                "proposer_id": configuration["proposer_id"],
                "metric_root": record_from_dict(thaw(configuration["policy"]["metric"])).root,
                "objective": configuration["policy"]["objective"],
                "baseline_configuration": baseline.state,
                "hypotheses": () if self.proposal is None else self.proposal.content["hypotheses"],
                "trials": trials,
                "failure_classes": sorted(
                    {item.failure.classification for item in self.operations if item.failure}
                ),
                "historical_only": True,
            },
            source_refs=tuple(refs),
        )


def attempt(store: LearningStore, inputs: Observation) -> LearningAttempt:
    pass_id = inputs.value["pass_id"]
    baseline = inputs.target_snapshot
    assert baseline is not None
    native = store.cached(pass_id, "result")
    result = (
        None if native is None else learning_result(store, inputs, cast(LearningTerminal, native))
    )
    proposal = None
    reflection = None
    operations: list[ActionResult] = []
    # These are the existing facade's canonical bounded run identities, not a
    # new runtime registry. Missing native submission proves neither success nor
    # absence of a host effect interrupted before submission.
    for suffix in (
        "reflection",
        "ideas",
        "investigate",
        "improvement",
        "governance",
        "activation:application",
    ):
        state = store.runtime.resume(f"{pass_id}:{suffix}")
        if state is None:
            continue
        if state.run.run_id != f"{pass_id}:{suffix}" or state.run.target_snapshot != baseline:
            raise ValueError("learning operation belongs to another baseline")
        if suffix in {"ideas", "reflection"}:
            request = (
                reflection_request(inputs)
                if suffix == "reflection"
                else proposal_request(inputs, reflection)
            )
            if request is None or state.run != reasoning_run(request):
                raise ValueError("historical proposal run does not match its frozen inputs")
        operations.extend(state.results)
        if (
            suffix == "reflection"
            and state.results
            and state.results[-1].disposition == "succeeded"
        ):
            reflection = reasoning_result_from_action_result(state.results[-1])
            if reflection.request != reflection_request(inputs):
                raise ValueError("historical reflection belongs to another request")
        if suffix == "ideas" and state.results and state.results[-1].disposition == "succeeded":
            proposal = reasoning_result_from_action_result(state.results[-1])
            if proposal.request != proposal_request(inputs, reflection):
                raise ValueError("historical proposal belongs to another request")
    snapshots = {baseline.root: baseline}
    if proposal is not None:
        hypotheses = proposal.content["hypotheses"]
        maximum = inputs.value["configuration"]["policy"]["max_candidates"]
        if not 2 <= len(hypotheses) <= maximum:
            raise ValueError("historical proposal exceeds its candidate allowance")
        roots = set()
        for hypothesis in hypotheses:
            if set(hypothesis["causal_model"]) != {"configuration"}:
                raise ValueError("historical proposal must contain only configuration")
            snapshot = store.snapshot(hypothesis["causal_model"]["configuration"])
            if snapshot == baseline or snapshot.root in roots:
                raise ValueError("historical proposals must be distinct baseline revisions")
            roots.add(snapshot.root)
            snapshots[snapshot.root] = snapshot
    measurements = []
    for value in inputs.value["training"]:
        case = case_from_record(cast(Observation, record_from_dict(thaw(value))))
        for snapshot in snapshots.values():
            key = f"measure:training:{snapshot.root}:{case.record.root}"
            row = store.cached(pass_id, key)
            if row is None:
                continue
            if (
                not isinstance(row, Observation)
                or row.kind not in {"learning.measurement", "learning.measurement-failure"}
                or row.source_refs != (inputs.ref, snapshot.ref, case.record.ref)
                or row.target_snapshot != snapshot
                or row.value["adapter_id"] != inputs.value["configuration"]["adapter_id"]
            ):
                raise ValueError("historical measurement does not match its training inputs")
            if row.kind == "learning.measurement":
                TaskMeasurement(row.value["output"], row.value["value"])
            measurements.append(row)
    return LearningAttempt(
        inputs, result, proposal, reflection, tuple(operations), tuple(measurements)
    )


def history(store: LearningStore, *, limit: int = 2) -> tuple[LearningAttempt, ...]:
    if type(limit) is not int or limit < 0:
        raise ValueError("history limit must be a nonnegative integer")
    if limit == 0:
        return ()
    return tuple(attempt(store, inputs) for inputs in ordered_inputs(store)[-limit:])
