"""Claim-only validation over the authoritative runtime state machine."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..capabilities import Experimenter
from ..knowledge import KnowledgeQuery, KnowledgeStore, label_currentness
from ..records import BeliefState, Claim, Evidence, EvidenceRef, Outcome, TargetSnapshot
from ..runtime import (
    Action,
    ActionResult,
    RunState,
    RuntimeEngine,
    Transition,
)
from .actions import (
    ValidationEvidenceResultValidator,
    make_validation_evidence_action,
    make_validation_evidence_result,
    validation_batch_from_action_result,
    validation_evidence_request_from_action,
)
from .policy import ValidationPolicy
from .records import (
    ValidationEvidenceBatch,
    ValidationEvidenceRequest,
    ValidationRequest,
    ValidationResult,
)


def validation_outcome(result: ValidationResult) -> Outcome:
    """Derive the canonical terminal Outcome owned by validation semantics."""

    if not isinstance(result, ValidationResult):
        raise TypeError("validation outcome requires a ValidationResult")
    if result.terminal_status in {"failed", "cancelled"}:
        terminal_result = result.terminal_result
        failure = result.terminal_failure
        if terminal_result is None or failure is None:  # pragma: no cover - record invariant
            raise RuntimeError("validation failure settlement is incomplete")
        return Outcome(
            intent=result.validation.claim.ref,
            status=result.terminal_status,
            target_snapshot=result.validation.target_snapshot,
            unresolved=(failure.message,),
            lineage=(terminal_result.ref, failure.ref),
        )
    conclusions: tuple[str, ...] = ()
    if result.disposition == "supported":
        conclusions = (f"Supported: {result.validation.claim.statement}",)
    elif result.disposition == "contradicted":
        conclusions = (f"Contradicted: {result.validation.claim.statement}",)
    elif result.disposition == "bounded":
        conclusions = (f"Bounded: {result.validation.claim.statement}",)
    return Outcome(
        intent=result.validation.claim.ref,
        status=result.disposition,
        target_snapshot=result.validation.target_snapshot,
        conclusions=conclusions,
        evidence_refs=tuple(EvidenceRef.from_evidence(item) for item in result.evidence),
        unresolved=result.unresolved,
        next_actions=result.unresolved if result.disposition == "inconclusive" else (),
        lineage=(result.ref, result.belief.ref, *(item.ref for item in result.evidence)),
    )


def validate_validation_terminal_state(
    result: ValidationResult,
    state: RunState,
) -> None:
    """Replay an exceptional result's complete runtime roster to its exact state."""

    if not isinstance(result, ValidationResult):
        raise TypeError("validation terminal replay requires a ValidationResult")
    if not isinstance(state, RunState):
        raise TypeError("validation terminal replay requires a RunState")
    validation = result.validation
    if state.run != validation.canonical_run():
        raise ValueError("validation terminal state does not use the canonical request Run")
    if state.status != result.terminal_status or state.status not in {"failed", "cancelled"}:
        raise ValueError("validation terminal state does not match its exceptional status")
    if (
        not state.results
        or not state.failures
        or state.results[-1] != result.terminal_result
        or state.failures[-1] != result.terminal_failure
    ):
        raise ValueError("validation terminal state lost its exact runtime settlement")

    evidence_by_ref = {EvidenceRef.from_evidence(item): item for item in result.evidence}
    try:
        working = {
            reference: evidence_by_ref[reference] for reference in result.reused_evidence_refs
        }
    except KeyError as exc:  # pragma: no cover - ValidationResult partition invariant
        raise ValueError("validation terminal replay lost reused evidence") from exc
    gathered: dict[EvidenceRef, Evidence] = {}
    policy = ValidationPolicy()
    replayed = RuntimeEngine.start(state.run).state

    for position, action_result in enumerate(state.results, start=1):
        evidence_before = tuple(sorted(working.values(), key=lambda item: item.root))
        belief_before = policy.belief(validation, evidence_before)
        gaps = policy.gaps(belief_before, evidence_before)
        if not gaps:
            raise ValueError("validation terminal state requested work after evidence sufficiency")
        expected_request = ValidationEvidenceRequest.for_gaps(
            validation=validation,
            sequence=position,
            known_evidence_refs=policy.evidence_refs(evidence_before),
            gaps=gaps,
        )
        expected_action = make_validation_evidence_action(
            run=state.run,
            request=expected_request,
        )
        if action_result.action != expected_action:
            raise ValueError("validation terminal action is not reachable from its prior frontier")

        requested = RuntimeEngine.request(replayed, expected_action).state
        ValidationEvidenceResultValidator().validate(requested, action_result)
        replayed = RuntimeEngine.submit(requested, action_result).state
        is_last = position == len(state.results)
        if action_result.disposition != "succeeded":
            if not is_last:
                raise ValueError("validation terminal state continued after a failed action")
            expected_disposition = "cancelled" if state.status == "cancelled" else "failed"
            if action_result.disposition != expected_disposition:
                raise ValueError("validation terminal action does not match runtime status")
            continue

        batch = validation_batch_from_action_result(action_result)
        for item in batch.evidence:
            reference = EvidenceRef.from_evidence(item)
            if reference in working:
                raise ValueError("validation terminal state contains duplicate evidence")
            working[reference] = item
            gathered[reference] = item
        evidence_after = tuple(sorted(working.values(), key=lambda item: item.root))
        disposition = policy.disposition(
            policy.belief(validation, evidence_after),
            evidence_after,
        )
        stopped = (
            batch.disposition == "unavailable"
            or disposition != "inconclusive"
            or position >= validation.max_evidence_actions
        )
        if stopped or is_last:
            raise ValueError("validation terminal state is not reachable past its settled frontier")

    if replayed != state:
        raise ValueError("validation terminal state is not the exact runtime replay result")
    if tuple(sorted(working.values(), key=lambda item: item.root)) != result.evidence:
        raise ValueError("validation terminal replay does not derive the exact result evidence")
    if tuple(sorted(gathered, key=lambda item: item.root)) != result.gathered_evidence_refs:
        raise ValueError("validation terminal replay does not derive gathered evidence")


@dataclass(frozen=True)
class ValidationProgress:
    """Workflow projection; RunState remains the sole lifecycle authority."""

    validation: ValidationRequest
    state: RunState
    belief: BeliefState
    evidence: tuple[Evidence, ...]
    reused_evidence_refs: tuple[EvidenceRef, ...]
    gathered_evidence_refs: tuple[EvidenceRef, ...]
    result: ValidationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.validation, ValidationRequest):
            raise TypeError("validation progress requires a ValidationRequest")
        if not isinstance(self.state, RunState):
            raise TypeError("validation progress requires a RunState")
        if not isinstance(self.belief, BeliefState):
            raise TypeError("validation progress requires a BeliefState")
        if (
            self.state.run.intent != self.validation.claim.ref
            or self.state.run.target_snapshot != self.validation.target_snapshot
            or self.state.run.run_id != self.validation.validation_id
            or self.state.run.lineage != (self.validation.ref,)
        ):
            raise ValueError("validation progress runtime does not match its request")
        raw_evidence = tuple(self.evidence)
        if any(not isinstance(item, Evidence) for item in raw_evidence):
            raise TypeError("validation progress evidence must contain Evidence values")
        evidence = tuple(sorted(raw_evidence, key=lambda item: item.root))
        if self.belief.evidence_refs != tuple(EvidenceRef.from_evidence(item) for item in evidence):
            raise ValueError("validation progress belief does not match its evidence")
        object.__setattr__(self, "evidence", evidence)
        refs = {EvidenceRef.from_evidence(item) for item in evidence}
        reused = tuple(sorted(self.reused_evidence_refs, key=lambda item: item.root))
        gathered = tuple(sorted(self.gathered_evidence_refs, key=lambda item: item.root))
        if set(reused) & set(gathered) or set((*reused, *gathered)) != refs:
            raise ValueError("validation progress evidence provenance is incomplete")
        object.__setattr__(self, "reused_evidence_refs", reused)
        object.__setattr__(self, "gathered_evidence_refs", gathered)
        if self.result is not None:
            if not isinstance(self.result, ValidationResult):
                raise TypeError("validation progress result must be a ValidationResult")
            if self.result.run != self.state.run.ref:
                raise ValueError("validation result does not belong to the progress run")
            if (
                self.result.validation != self.validation
                or self.result.belief != self.belief
                or self.result.evidence != evidence
                or self.result.reused_evidence_refs != reused
                or self.result.gathered_evidence_refs != gathered
            ):
                raise ValueError("validation result does not match its exact progress projection")
            if self.state.status not in {"completed", "failed", "cancelled"}:
                raise ValueError("validation result requires a terminal runtime state")
            if self.result.terminal_status != self.state.status:
                raise ValueError("validation result settlement does not match runtime status")
            if self.state.status in {"failed", "cancelled"} and (
                not self.state.results
                or not self.state.failures
                or self.result.terminal_state != self.state
                or self.result.terminal_result != self.state.results[-1]
                or self.result.terminal_failure != self.state.failures[-1]
            ):
                raise ValueError("validation result lost exact runtime failure settlement")
        elif self.state.status in {"completed", "failed", "cancelled"}:
            raise ValueError("terminal validation progress requires a result")


@dataclass(frozen=True)
class ValidationUpdate:
    progress: ValidationProgress
    transitions: tuple[Transition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.progress, ValidationProgress):
            raise TypeError("validation updates require ValidationProgress")
        transitions = tuple(self.transitions)
        if any(not isinstance(item, Transition) for item in transitions):
            raise TypeError("validation updates require Transition values")
        object.__setattr__(self, "transitions", transitions)


@dataclass(frozen=True)
class ValidationStep:
    state: RunState
    actions: tuple[Action, ...]
    result: ValidationResult | None

    @property
    def terminal(self) -> bool:
        return self.result is not None


class ValidationWorkflow:
    """Bounded vertical composition for validating one exact Claim."""

    def __init__(self, policy: ValidationPolicy | None = None) -> None:
        self._policy = (
            ValidationPolicy() if policy is None else ValidationPolicy.owned_canonical(policy)
        )

    def _knowledge(
        self,
        validation: ValidationRequest,
        store: KnowledgeStore | None,
    ) -> tuple[Evidence, ...]:
        if store is None:
            return ()
        if not isinstance(store, KnowledgeStore):
            raise TypeError("validation knowledge must implement KnowledgeStore")
        query = KnowledgeQuery(
            record_types=("evidence",),
            target=validation.claim.target,
            current_snapshot=validation.target_snapshot,
            subject_refs=(validation.claim.ref,),
            evidence_types=validation.evidence_types,
            valid=True,
            currentness="current" if validation.target_snapshot is not None else None,
        )
        evidence: dict[str, Evidence] = {}
        for stored in store.query(query):
            record = stored.record
            if not isinstance(record, Evidence):
                raise ValueError("validation knowledge query returned non-evidence state")
            if stored.valid is not True:
                raise ValueError("validation knowledge returned invalid evidence state")
            if validation.claim.ref not in record.subject_refs:
                raise ValueError("validation knowledge returned evidence for another claim")
            currentness = label_currentness(record, validation.target_snapshot)
            if stored.currentness != currentness:
                raise ValueError("validation knowledge currentness projection has drifted")
            if validation.target_snapshot is not None and currentness != "current":
                raise ValueError("validation knowledge returned noncurrent evidence")
            if validation.target_snapshot is None and currentness not in {"unassessed", "unbound"}:
                raise ValueError("validation knowledge returned incomparable evidence")
            if record.evidence_type not in validation.evidence_types:
                raise ValueError("validation knowledge returned an inadmissible evidence type")
            self._policy.belief(validation, (record,))
            evidence[record.root] = record
        return tuple(evidence[root] for root in sorted(evidence))

    def _progress(
        self,
        *,
        validation: ValidationRequest,
        state: RunState,
        evidence: Sequence[Evidence],
        reused: Sequence[EvidenceRef],
        gathered: Sequence[EvidenceRef],
        result: ValidationResult | None = None,
    ) -> ValidationProgress:
        items = tuple(sorted(evidence, key=lambda item: item.root))
        return ValidationProgress(
            validation=validation,
            state=state,
            belief=self._policy.belief(validation, items),
            evidence=items,
            reused_evidence_refs=tuple(reused),
            gathered_evidence_refs=tuple(gathered),
            result=result,
        )

    def _result(
        self,
        progress: ValidationProgress,
        *,
        unresolved: Sequence[str] | None = None,
    ) -> ValidationResult:
        return self._build_result(
            validation=progress.validation,
            state=progress.state,
            belief=progress.belief,
            evidence=progress.evidence,
            reused=progress.reused_evidence_refs,
            gathered=progress.gathered_evidence_refs,
            unresolved=unresolved,
        )

    def _build_result(
        self,
        *,
        validation: ValidationRequest,
        state: RunState,
        belief: BeliefState,
        evidence: Sequence[Evidence],
        reused: Sequence[EvidenceRef],
        gathered: Sequence[EvidenceRef],
        unresolved: Sequence[str] | None = None,
    ) -> ValidationResult:
        evidence_items = tuple(sorted(evidence, key=lambda item: item.root))
        disposition = self._policy.disposition(belief, evidence_items)
        items = (
            tuple(unresolved)
            if unresolved is not None
            else self._policy.gaps(belief, evidence_items)
        )
        terminal = state.status in {"failed", "cancelled"}
        terminal_result = state.results[-1] if terminal and state.results else None
        terminal_failure = state.failures[-1] if terminal and state.failures else None
        return ValidationResult(
            validation=validation,
            run=state.run.ref,
            disposition=disposition,
            belief=belief,
            evidence=evidence_items,
            reused_evidence_refs=tuple(reused),
            gathered_evidence_refs=tuple(gathered),
            unresolved=items,
            terminal_status=state.status if terminal else "completed",
            terminal_state=state if terminal else None,
            terminal_result=terminal_result,
            terminal_failure=terminal_failure,
            lineage=(
                validation.ref,
                state.run.ref,
                belief.ref,
                *(item.ref for item in evidence_items),
                *((state.ref,) if terminal else ()),
                *((terminal_result.ref,) if terminal_result is not None else ()),
                *((terminal_failure.ref,) if terminal_failure is not None else ()),
            ),
        )

    @staticmethod
    def _outcome(result: ValidationResult) -> Outcome:
        return validation_outcome(result)

    def _finish(
        self,
        progress: ValidationProgress,
        *,
        unresolved: Sequence[str] | None = None,
    ) -> ValidationUpdate:
        result = self._result(progress, unresolved=unresolved)
        completed = RuntimeEngine.complete(progress.state, self._outcome(result))
        if completed.transition is None:  # pragma: no cover - engine invariant
            raise RuntimeError("validation completion lost its transition")
        return ValidationUpdate(
            progress=self._progress(
                validation=progress.validation,
                state=completed.state,
                evidence=progress.evidence,
                reused=progress.reused_evidence_refs,
                gathered=progress.gathered_evidence_refs,
                result=result,
            ),
            transitions=(completed.transition,),
        )

    def _request(self, progress: ValidationProgress) -> ValidationUpdate:
        sequence = progress.state.action_count + 1
        request = ValidationEvidenceRequest.for_gaps(
            validation=progress.validation,
            sequence=sequence,
            known_evidence_refs=self._policy.evidence_refs(progress.evidence),
            gaps=self._policy.gaps(progress.belief, progress.evidence),
        )
        action = make_validation_evidence_action(run=progress.state.run, request=request)
        requested = RuntimeEngine.request(progress.state, action)
        if requested.transition is None:  # pragma: no cover - engine invariant
            raise RuntimeError("validation evidence request lost its transition")
        return ValidationUpdate(
            progress=self._progress(
                validation=progress.validation,
                state=requested.state,
                evidence=progress.evidence,
                reused=progress.reused_evidence_refs,
                gathered=progress.gathered_evidence_refs,
            ),
            transitions=(requested.transition,),
        )

    def start(
        self,
        validation: ValidationRequest,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> ValidationUpdate:
        if not isinstance(validation, ValidationRequest):
            raise TypeError("validation start requires a ValidationRequest")
        run = validation.canonical_run()
        started = RuntimeEngine.start(run)
        if started.transition is None:  # pragma: no cover - engine invariant
            raise RuntimeError("validation start lost its transition")
        evidence = self._knowledge(validation, knowledge_store)
        reused = tuple(EvidenceRef.from_evidence(item) for item in evidence)
        progress = self._progress(
            validation=validation,
            state=started.state,
            evidence=evidence,
            reused=reused,
            gathered=(),
        )
        if self._policy.disposition(progress.belief, progress.evidence) != "inconclusive":
            finished = self._finish(progress)
            return ValidationUpdate(
                progress=finished.progress,
                transitions=(started.transition, *finished.transitions),
            )
        requested = self._request(progress)
        return ValidationUpdate(
            progress=requested.progress,
            transitions=(started.transition, *requested.transitions),
        )

    def _require_canonical_frontier(
        self,
        progress: ValidationProgress,
        knowledge_store: KnowledgeStore | None,
    ) -> None:
        if not isinstance(progress, ValidationProgress):
            raise TypeError("validation progress must be a ValidationProgress")
        reconciled = self.resume(
            progress.validation,
            progress.state,
            knowledge_store=knowledge_store,
        )
        if reconciled.transitions or reconciled.progress != progress:
            raise ValueError("validation progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: ValidationProgress,
        action_result: ActionResult,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> ValidationUpdate:
        if not isinstance(progress, ValidationProgress):
            raise TypeError("validation submission requires ValidationProgress")
        if progress.result is not None or len(progress.state.pending_actions) != 1:
            raise ValueError("validation submission requires one pending evidence action")
        self._require_canonical_frontier(progress, knowledge_store)
        pending = progress.state.pending_actions[0]
        if not isinstance(action_result, ActionResult) or action_result.action != pending:
            raise ValueError("validation result does not match the exact pending action")
        ValidationEvidenceResultValidator().validate(progress.state, action_result)

        batch: ValidationEvidenceBatch | None = None
        if action_result.disposition == "succeeded":
            batch = validation_batch_from_action_result(action_result)
            known = {EvidenceRef.from_evidence(item) for item in progress.evidence}
            if any(EvidenceRef.from_evidence(item) in known for item in batch.evidence):
                raise ValueError("validation evidence has already been considered")

        submitted = RuntimeEngine.submit(progress.state, action_result)
        if submitted.transition is None:
            raise ValueError("validation workflow does not accept duplicate submissions")
        transitions: tuple[Transition, ...] = (submitted.transition,)

        if batch is None:
            if submitted.state.status == "waiting":
                return ValidationUpdate(
                    progress=self._progress(
                        validation=progress.validation,
                        state=submitted.state,
                        evidence=progress.evidence,
                        reused=progress.reused_evidence_refs,
                        gathered=progress.gathered_evidence_refs,
                    ),
                    transitions=transitions,
                )
            outcome = submitted.state.outcome
            if outcome is None:  # pragma: no cover - terminal runtime invariant
                raise RuntimeError("terminal validation failure lost its outcome")
            unresolved = outcome.unresolved or ("validation evidence execution failed",)
            result = self._build_result(
                validation=progress.validation,
                state=submitted.state,
                belief=progress.belief,
                evidence=progress.evidence,
                reused=progress.reused_evidence_refs,
                gathered=progress.gathered_evidence_refs,
                unresolved=unresolved,
            )
            return ValidationUpdate(
                progress=self._progress(
                    validation=progress.validation,
                    state=submitted.state,
                    evidence=progress.evidence,
                    reused=progress.reused_evidence_refs,
                    gathered=progress.gathered_evidence_refs,
                    result=result,
                ),
                transitions=transitions,
            )

        evidence = tuple((*progress.evidence, *batch.evidence))
        gathered = tuple(
            (
                *progress.gathered_evidence_refs,
                *(EvidenceRef.from_evidence(item) for item in batch.evidence),
            )
        )
        advanced = self._progress(
            validation=progress.validation,
            state=submitted.state,
            evidence=evidence,
            reused=progress.reused_evidence_refs,
            gathered=gathered,
        )
        disposition = self._policy.disposition(advanced.belief, advanced.evidence)
        if disposition != "inconclusive":
            finished = self._finish(advanced)
            return ValidationUpdate(
                progress=finished.progress,
                transitions=(*transitions, *finished.transitions),
            )
        if batch.disposition == "unavailable":
            finished = self._finish(advanced, unresolved=(batch.reason or "evidence unavailable",))
            return ValidationUpdate(
                progress=finished.progress,
                transitions=(*transitions, *finished.transitions),
            )
        if submitted.state.action_count >= progress.validation.max_evidence_actions:
            finished = self._finish(advanced)
            return ValidationUpdate(
                progress=finished.progress,
                transitions=(*transitions, *finished.transitions),
            )
        requested = self._request(advanced)
        return ValidationUpdate(
            progress=requested.progress,
            transitions=(*transitions, *requested.transitions),
        )

    def resume(
        self,
        validation: ValidationRequest,
        state: RunState,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> ValidationUpdate:
        """Reconcile and continue from any exact persisted runtime transition."""

        if not isinstance(validation, ValidationRequest):
            raise TypeError("validation resume requires a ValidationRequest")
        if not isinstance(state, RunState):
            raise TypeError("validation resume requires a RunState")
        if (
            state.run.intent != validation.claim.ref
            or state.run.target_snapshot != validation.target_snapshot
            or state.run.lineage != (validation.ref,)
        ):
            raise ValueError("persisted validation run does not match the exact request")

        expected_run = validation.canonical_run()
        if state.run != expected_run:
            raise ValueError("persisted validation run envelope has drifted")

        requests: list[ValidationEvidenceRequest] = []
        for sequence, action in enumerate(state.actions, start=1):
            request = validation_evidence_request_from_action(action)
            if request.validation != validation or request.sequence != sequence:
                raise ValueError("persisted validation action has drifted from its request")
            if action != make_validation_evidence_action(run=state.run, request=request):
                raise ValueError("persisted validation action is not canonical")
            requests.append(request)

        reused_refs: tuple[EvidenceRef, ...] = ()
        if requests:
            reused_refs = requests[0].known_evidence_refs
        elif state.outcome is not None:
            reused_refs = state.outcome.evidence_refs
        elif state.status == "active":
            reused_refs = tuple(
                EvidenceRef.from_evidence(item)
                for item in self._knowledge(validation, knowledge_store)
            )

        reused: dict[str, Evidence] = {}
        if reused_refs:
            if knowledge_store is None:
                raise ValueError("resuming reused validation evidence requires KnowledgeStore")
            if not isinstance(knowledge_store, KnowledgeStore):
                raise TypeError("validation knowledge must implement KnowledgeStore")
            for reference in reused_refs:
                record = knowledge_store.get(reference.root)
                if not isinstance(record, Evidence) or record.ref != reference:
                    raise ValueError("reused validation evidence is unavailable at its exact root")
                reused[record.root] = record

        gathered: dict[str, Evidence] = {}
        results = {item.action.ref: item for item in state.results}
        pending = {item.ref for item in state.pending_actions}
        for position, (action, request) in enumerate(
            zip(state.actions, requests, strict=True), start=1
        ):
            evidence_before_action = tuple(
                sorted((*reused.values(), *gathered.values()), key=lambda item: item.root)
            )
            belief_before_action = self._policy.belief(validation, evidence_before_action)
            gaps = self._policy.gaps(belief_before_action, evidence_before_action)
            if not gaps:
                raise ValueError("persisted validation requested work after evidence sufficiency")
            expected_request = ValidationEvidenceRequest.for_gaps(
                validation=validation,
                sequence=position,
                known_evidence_refs=self._policy.evidence_refs(evidence_before_action),
                gaps=gaps,
            )
            if request != expected_request:
                raise ValueError("persisted validation request is not policy-derived")
            action_result = results.get(action.ref)
            if action_result is None:
                if (
                    action.ref not in pending
                    or position != len(state.actions)
                    or state.status != "waiting"
                ):
                    raise ValueError("persisted validation has an invalid pending frontier")
                continue
            ValidationEvidenceResultValidator().validate(state, action_result)
            if action_result.disposition != "succeeded":
                if position != len(state.actions) or state.status not in {"failed", "cancelled"}:
                    raise ValueError("persisted validation continued after a terminal failure")
                continue
            batch = validation_batch_from_action_result(action_result)
            for item in batch.evidence:
                if item.root in reused or item.root in gathered:
                    raise ValueError("persisted validation contains duplicate gathered evidence")
                gathered[item.root] = item
            evidence_at_frontier = tuple(item for _, item in sorted({**reused, **gathered}.items()))
            disposition = self._policy.disposition(
                self._policy.belief(validation, evidence_at_frontier),
                evidence_at_frontier,
            )
            terminal = (
                batch.disposition == "unavailable"
                or disposition != "inconclusive"
                or position >= validation.max_evidence_actions
            )
            if terminal:
                if position != len(state.actions) or state.status not in {
                    "active",
                    "completed",
                }:
                    raise ValueError("persisted validation continued past its stopping condition")
            elif position == len(state.actions) and state.status != "active":
                raise ValueError("persisted validation stopped before its next evidence frontier")

        evidence = tuple(item for root, item in sorted({**reused, **gathered}.items()))
        belief = self._policy.belief(validation, evidence)
        reused_evidence_refs = tuple(
            EvidenceRef.from_evidence(reused[root]) for root in sorted(reused)
        )
        gathered_evidence_refs = tuple(
            EvidenceRef.from_evidence(gathered[root]) for root in sorted(gathered)
        )
        result: ValidationResult | None = None
        if state.status in {"completed", "failed", "cancelled"}:
            if state.outcome is None:  # pragma: no cover - RunState invariant
                raise RuntimeError("terminal validation state lost its outcome")
            expected_unresolved = self._policy.gaps(belief, evidence)
            failure = None
            if state.status == "completed":
                if not state.actions:
                    if self._policy.disposition(belief, evidence) == "inconclusive":
                        raise ValueError("persisted validation completed before its first gap")
                else:
                    last_result = state.results[-1]
                    last_batch = validation_batch_from_action_result(last_result)
                    if last_batch.disposition == "unavailable":
                        expected_unresolved = (last_batch.reason or "evidence unavailable",)
            else:
                if not state.results or not state.failures:
                    raise ValueError("terminal validation failure has incomplete runtime state")
                failure = state.failures[-1]
                expected_unresolved = (failure.message,)
            result = self._build_result(
                validation=validation,
                state=state,
                belief=belief,
                evidence=evidence,
                reused=reused_evidence_refs,
                gathered=gathered_evidence_refs,
                unresolved=expected_unresolved,
            )
            if state.outcome != self._outcome(result):
                raise ValueError("persisted validation outcome has drifted from its exact result")

        progress = ValidationProgress(
            validation=validation,
            state=state,
            belief=belief,
            evidence=evidence,
            reused_evidence_refs=reused_evidence_refs,
            gathered_evidence_refs=gathered_evidence_refs,
            result=result,
        )
        if state.status != "active":
            return ValidationUpdate(progress=progress, transitions=())
        if self._policy.disposition(progress.belief, progress.evidence) != "inconclusive":
            return self._finish(progress)
        if state.results:
            last_result = state.results[-1]
            if last_result.disposition != "succeeded":  # pragma: no cover - loop check above
                raise RuntimeError("active validation retained a failed action result")
            last_batch = validation_batch_from_action_result(last_result)
            if last_batch.disposition == "unavailable":
                return self._finish(
                    progress,
                    unresolved=(last_batch.reason or "evidence unavailable",),
                )
        if state.action_count >= validation.max_evidence_actions:
            return self._finish(progress)
        return self._request(progress)

    @staticmethod
    def step(progress: ValidationProgress) -> ValidationStep:
        if not isinstance(progress, ValidationProgress):
            raise TypeError("validation step requires ValidationProgress")
        return ValidationStep(
            state=progress.state,
            actions=progress.state.pending_actions,
            result=progress.result,
        )

    def run_managed(
        self,
        progress: ValidationProgress,
        experimenter: Experimenter,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> ValidationUpdate:
        if not isinstance(experimenter, Experimenter):
            raise TypeError("managed validation requires an Experimenter")
        transitions: list[Transition] = []
        current = progress
        while True:
            self._require_canonical_frontier(current, knowledge_store)
            if current.result is not None:
                break
            step = self.step(current)
            if len(step.actions) != 1:
                raise ValueError("managed validation requires one pending evidence action")
            result = experimenter.experiment(step.actions[0])
            update = self.submit(current, result, knowledge_store=knowledge_store)
            transitions.extend(update.transitions)
            current = update.progress
        return ValidationUpdate(progress=current, transitions=tuple(transitions))


def validate(
    *,
    claim: Claim,
    target_snapshot: TargetSnapshot | None = None,
    validation_id: str = "validation",
    knowledge_store: KnowledgeStore | None = None,
    evidence: Sequence[Evidence] = (),
    experimenter: Experimenter | None = None,
    max_evidence_actions: int = 1,
    policy: ValidationPolicy | None = None,
) -> ValidationResult:
    """Convenience validation over the same start/request/submit/complete transitions."""

    if not isinstance(claim, Claim):
        raise TypeError("validate requires a Claim")
    if target_snapshot is not None and not isinstance(target_snapshot, TargetSnapshot):
        raise TypeError("validation target snapshot must be a TargetSnapshot")
    if isinstance(evidence, (str, bytes, bytearray)) or not isinstance(evidence, Sequence):
        raise TypeError("validate evidence must be a sequence")
    if any(not isinstance(item, Evidence) for item in evidence):
        raise TypeError("validate evidence must contain Evidence values")
    if experimenter is not None and evidence:
        raise ValueError("validate accepts explicit evidence or an Experimenter, not both")
    request = ValidationRequest.for_claim(
        validation_id=validation_id,
        claim=claim,
        target_snapshot=target_snapshot,
        max_evidence_actions=max_evidence_actions,
    )
    workflow = ValidationWorkflow(policy)
    update = workflow.start(request, knowledge_store=knowledge_store)
    if update.progress.result is not None:
        return update.progress.result
    if experimenter is not None:
        completed = workflow.run_managed(
            update.progress,
            experimenter,
            knowledge_store=knowledge_store,
        )
        if completed.progress.result is None:  # pragma: no cover - loop invariant
            raise RuntimeError("managed validation did not produce a result")
        return completed.progress.result
    action = update.progress.state.pending_actions[0]
    request_record = validation_evidence_request_from_action(action)
    batch = (
        ValidationEvidenceBatch.collected(request=request_record, evidence=evidence)
        if evidence
        else ValidationEvidenceBatch.unavailable(
            request=request_record,
            reason="no evidence collector or explicit evidence was supplied",
        )
    )
    completed = workflow.submit(
        update.progress,
        make_validation_evidence_result(action=action, batch=batch),
        knowledge_store=knowledge_store,
    )
    if completed.progress.result is None:  # more work is bounded but unavailable here
        next_action = completed.progress.state.pending_actions[0]
        next_request = validation_evidence_request_from_action(next_action)
        completed = workflow.submit(
            completed.progress,
            make_validation_evidence_result(
                action=next_action,
                batch=ValidationEvidenceBatch.unavailable(
                    request=next_request,
                    reason="no additional explicit evidence was supplied",
                ),
            ),
            knowledge_store=knowledge_store,
        )
    if completed.progress.result is None:  # pragma: no cover - bounded convenience invariant
        raise RuntimeError("validation did not reach a bounded result")
    return completed.progress.result
