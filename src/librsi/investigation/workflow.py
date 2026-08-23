"""Bounded competing-hypothesis investigation over the canonical runtime."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..capabilities import Experimenter, Reasoner
from ..epistemics import EVIDENCE_RELATIONSHIPS
from ..knowledge import KnowledgeQuery, KnowledgeStore, label_currentness
from ..reasoning import ReasoningResult, reasoning_result_from_action_result
from ..records import Evidence, EvidenceRef, Hypothesis, Outcome, Question, TargetSnapshot
from ..runtime import Action, ActionResult, RunState, RuntimeEngine, RuntimeFailure, Transition
from .actions import (
    INVESTIGATION_EXPERIMENT_ACTION_KIND,
    INVESTIGATION_REASONING_ACTION_KIND,
    InvestigationExperimentResultValidator,
    InvestigationReasoningResultValidator,
    _investigation_reasoning_context,
    derive_investigation_action,
    investigation_batch_from_action_result,
)
from .policy import InvestigationPolicy
from .records import (
    InvestigationBranch,
    InvestigationRequest,
    InvestigationResult,
)


def investigation_outcome(result: InvestigationResult) -> Outcome:
    """Derive the canonical terminal Outcome owned by investigation semantics."""

    if not isinstance(result, InvestigationResult):
        raise TypeError("investigation outcome requires an InvestigationResult")
    if result.terminal_status in {"failed", "cancelled"}:
        terminal_result = result.failure_result
        failure = result.terminal_failure
        if terminal_result is None or failure is None:  # pragma: no cover - record invariant
            raise RuntimeError("investigation failure settlement is incomplete")
        return Outcome(
            intent=result.investigation.question.ref,
            status=result.terminal_status,
            target_snapshot=result.investigation.target_snapshot,
            unresolved=(failure.message,),
            lineage=(terminal_result.ref, failure.ref),
        )
    evidence_refs = tuple(EvidenceRef.from_evidence(item) for item in result.evidence)
    return Outcome(
        intent=result.investigation.question.ref,
        status=result.disposition,
        target_snapshot=result.investigation.target_snapshot,
        conclusions=tuple(item.statement for item in result.findings),
        evidence_refs=evidence_refs,
        unresolved=result.unresolved,
        next_actions=(),
        lineage=(result.ref, *(item.ref for item in result.findings), *evidence_refs),
    )


@dataclass(frozen=True)
class InvestigationProgress:
    """Workflow projection; RunState remains the only lifecycle authority."""

    investigation: InvestigationRequest
    state: RunState
    branches: tuple[InvestigationBranch, ...]
    result: InvestigationResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.investigation, InvestigationRequest):
            raise TypeError("investigation progress requires an InvestigationRequest")
        if not isinstance(self.state, RunState):
            raise TypeError("investigation progress requires a RunState")
        run = self.state.run
        if (
            run.run_id != self.investigation.investigation_id
            or run.intent != self.investigation.question.ref
            or run.target_snapshot != self.investigation.target_snapshot
            or run.lineage != (self.investigation.ref,)
        ):
            raise ValueError("investigation progress runtime does not match its request")
        branches = tuple(self.branches)
        if any(not isinstance(item, InvestigationBranch) for item in branches):
            raise TypeError("investigation progress branches must be InvestigationBranch records")
        if any(item.investigation != self.investigation for item in branches):
            raise ValueError("investigation progress branches belong to another request")
        if len({item.branch_id for item in branches}) != len(branches):
            raise ValueError("investigation progress branch ids must be unique")
        object.__setattr__(self, "branches", branches)
        if self.result is not None:
            if not isinstance(self.result, InvestigationResult):
                raise TypeError("investigation progress result must be an InvestigationResult")
            if self.result.investigation != self.investigation:
                raise ValueError("investigation result belongs to another request")
            if self.result.run != self.state.run.ref or self.result.branches != branches:
                raise ValueError("investigation result does not match its progress projection")
            if self.state.status not in {"completed", "failed", "cancelled"}:
                raise ValueError("investigation result requires a terminal runtime state")
            if self.result.terminal_status != self.state.status:
                raise ValueError("investigation result settlement does not match runtime status")
            if self.state.status in {"failed", "cancelled"} and (
                not self.state.results
                or not self.state.failures
                or self.result.failure_result != self.state.results[-1]
                or self.result.terminal_failure != self.state.failures[-1]
            ):
                raise ValueError("investigation result lost exact runtime failure settlement")
        elif self.state.status in {"completed", "failed", "cancelled"}:
            raise ValueError("terminal investigation progress requires a result")


@dataclass(frozen=True)
class InvestigationUpdate:
    progress: InvestigationProgress
    transitions: tuple[Transition, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.progress, InvestigationProgress):
            raise TypeError("investigation updates require InvestigationProgress")
        transitions = tuple(self.transitions)
        if any(not isinstance(item, Transition) for item in transitions):
            raise TypeError("investigation updates require Transition values")
        object.__setattr__(self, "transitions", transitions)


@dataclass(frozen=True)
class InvestigationStep:
    state: RunState
    actions: tuple[Action, ...]
    branches: tuple[InvestigationBranch, ...]
    result: InvestigationResult | None

    @property
    def terminal(self) -> bool:
        return self.result is not None


class InvestigationWorkflow:
    """Question-oriented composition with one deterministic action frontier."""

    def __init__(self, policy: InvestigationPolicy | None = None) -> None:
        self._policy = (
            InvestigationPolicy() if policy is None else InvestigationPolicy.owned_canonical(policy)
        )

    def _knowledge(
        self,
        investigation: InvestigationRequest,
        hypothesis: Hypothesis,
        store: KnowledgeStore | None,
    ) -> tuple[Evidence, ...]:
        if store is None:
            return ()
        if not isinstance(store, KnowledgeStore):
            raise TypeError("investigation knowledge must implement KnowledgeStore")
        query = KnowledgeQuery(
            record_types=("evidence",),
            target=investigation.question.target,
            current_snapshot=investigation.target_snapshot,
            subject_refs=(hypothesis.ref,),
            evidence_types=tuple(sorted(EVIDENCE_RELATIONSHIPS)),
            valid=True,
            currentness="current" if investigation.target_snapshot is not None else None,
        )
        evidence: dict[str, Evidence] = {}
        for stored in store.query(query):
            record = stored.record
            if not isinstance(record, Evidence):
                raise ValueError("investigation knowledge returned non-evidence state")
            if stored.valid is not True:
                raise ValueError("investigation knowledge returned invalid evidence state")
            if record.subject_refs != (hypothesis.ref,):
                raise ValueError("investigation knowledge leaked evidence between hypotheses")
            currentness = label_currentness(record, investigation.target_snapshot)
            if stored.currentness != currentness:
                raise ValueError("investigation knowledge currentness projection has drifted")
            if investigation.target_snapshot is not None and currentness != "current":
                raise ValueError("investigation knowledge returned noncurrent evidence")
            if investigation.target_snapshot is None and currentness not in {
                "unassessed",
                "unbound",
            }:
                raise ValueError("investigation knowledge returned incomparable evidence")
            if record.evidence_type not in EVIDENCE_RELATIONSHIPS:
                raise ValueError("investigation knowledge returned inadmissible evidence")
            if not record.source_refs or record.weight is None:
                raise ValueError("investigation knowledge evidence lacks exact provenance")
            self._policy.belief(investigation, hypothesis, (record,))
            evidence[record.root] = record
        return tuple(evidence[root] for root in sorted(evidence))

    def _seed_branches(
        self,
        investigation: InvestigationRequest,
        knowledge_store: KnowledgeStore | None,
    ) -> tuple[InvestigationBranch, ...]:
        return tuple(
            self._policy.initial_branch(
                investigation=investigation,
                branch_id=f"hypothesis-{index}",
                hypothesis=hypothesis,
                evidence=self._knowledge(investigation, hypothesis, knowledge_store),
            )
            for index, hypothesis in enumerate(investigation.initial_hypotheses, start=1)
        )

    def _branches_from_reasoning(
        self,
        investigation: InvestigationRequest,
        result: ReasoningResult,
        knowledge_store: KnowledgeStore | None,
    ) -> tuple[InvestigationBranch, ...]:
        hypotheses = self._policy.hypotheses_from_result(
            investigation=investigation,
            result=result,
        )
        return tuple(
            self._policy.initial_branch(
                investigation=investigation,
                branch_id=f"hypothesis-{index}",
                hypothesis=hypothesis,
                evidence=self._knowledge(investigation, hypothesis, knowledge_store),
            )
            for index, hypothesis in enumerate(hypotheses, start=1)
        )

    def _normalize_branches(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
    ) -> tuple[InvestigationBranch, ...]:
        items = tuple(branches)
        total_experiments = sum(len(item.experiments) for item in items)
        normalized: list[InvestigationBranch] = []
        for branch in items:
            if branch.status != "active":
                normalized.append(branch)
                continue
            if branch.experiments and not self._policy.experiment_has_evidence(branch):
                normalized.append(branch)
                continue
            if total_experiments >= investigation.max_experiments:
                normalized.append(self._policy.retire(branch, "experiment-budget"))
            elif branch.experiments and (
                branch.redesign_count >= investigation.max_redesigns_per_hypothesis
            ):
                normalized.append(self._policy.retire(branch, "redesign-budget"))
            else:
                normalized.append(branch)
        return tuple(normalized)

    def _next_action(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
    ) -> Action | None:
        items = tuple(branches)
        return derive_investigation_action(investigation, items)

    def _apply_success(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
        result: ActionResult,
        knowledge_store: KnowledgeStore | None,
    ) -> tuple[InvestigationBranch, ...]:
        items = tuple(branches)
        if result.action.kind == INVESTIGATION_REASONING_ACTION_KIND:
            proposal = reasoning_result_from_action_result(result)
            action_investigation, frontier, selected_branch, _ = _investigation_reasoning_context(
                result.action
            )
            if action_investigation != investigation or frontier.branches != items:
                raise ValueError("investigation reasoning does not match the complete frontier")
            if proposal.kind == "hypothesis-generation":
                if items or selected_branch is not None:
                    raise ValueError("investigation cannot replace existing hypotheses")
                return self._branches_from_reasoning(
                    investigation,
                    proposal,
                    knowledge_store,
                )
            if proposal.kind != "experiment-design":
                raise ValueError("investigation reasoning kind is outside the workflow")
            branch = selected_branch
            expected_action = derive_investigation_action(investigation, items)
            if branch is None or result.action != expected_action:
                raise ValueError("investigation design does not match the exact branch frontier")
            experiment = self._policy.build_experiment(
                investigation=investigation,
                branch=branch,
                result=proposal,
            )
            return tuple(
                self._policy.add_experiment(item, experiment)
                if item.branch_id == branch.branch_id
                else item
                for item in items
            )
        if result.action.kind != INVESTIGATION_EXPERIMENT_ACTION_KIND:
            raise ValueError("investigation action kind is outside the workflow")
        batch = investigation_batch_from_action_result(result)
        if batch.request.investigation != investigation or batch.request.frontier.branches != items:
            raise ValueError("investigation evidence does not match the complete frontier")
        branch = next(
            (item for item in items if item.branch_id == batch.request.branch.branch_id),
            None,
        )
        if branch is None or branch != batch.request.branch:
            raise ValueError("investigation evidence does not match the current branch")
        return tuple(
            self._policy.apply_batch(item, batch) if item.branch_id == branch.branch_id else item
            for item in items
        )

    @staticmethod
    def _outcome(result: InvestigationResult) -> Outcome:
        return investigation_outcome(result)

    def _result(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
        *,
        failure_result: ActionResult | None = None,
        terminal_status: str = "completed",
        terminal_failure: RuntimeFailure | None = None,
    ) -> InvestigationResult:
        items = tuple(branches)
        return self._policy.build_result(
            investigation=investigation,
            branches=items,
            failure_result=failure_result,
            terminal_status=terminal_status,
            terminal_failure=terminal_failure,
        )

    def _reconstruct(
        self,
        investigation: InvestigationRequest,
        state: RunState,
        knowledge_store: KnowledgeStore | None,
    ) -> tuple[InvestigationBranch, ...]:
        if state.run != investigation.canonical_run():
            raise ValueError("persisted investigation run envelope has drifted")
        if len(state.pending_actions) > 1:
            raise ValueError("persisted investigation has a noncanonical action frontier")
        if len(state.results) > len(state.actions):
            raise ValueError("persisted investigation has more results than actions")
        if len(state.actions) - len(state.results) != len(state.pending_actions):
            raise ValueError("persisted investigation action/result frontier is incomplete")

        branches = self._seed_branches(investigation, knowledge_store)
        for position, action in enumerate(state.actions):
            branches = self._normalize_branches(investigation, branches)
            expected = self._next_action(investigation, branches)
            if expected is None or action != expected:
                raise ValueError("persisted investigation action is not policy-derived")
            if position >= len(state.results):
                if (
                    position != len(state.actions) - 1
                    or state.pending_actions != (action,)
                    or state.status != "waiting"
                ):
                    raise ValueError("persisted investigation has an invalid pending frontier")
                break
            result = state.results[position]
            if result.action != action:
                raise ValueError("persisted investigation result order has drifted")
            if action.kind == INVESTIGATION_REASONING_ACTION_KIND:
                InvestigationReasoningResultValidator().validate(state, result)
            elif action.kind == INVESTIGATION_EXPERIMENT_ACTION_KIND:
                InvestigationExperimentResultValidator().validate(state, result)
            else:
                raise ValueError("persisted investigation contains an unsupported action")
            if result.disposition != "succeeded":
                if position != len(state.actions) - 1 or state.status not in {
                    "failed",
                    "cancelled",
                }:
                    raise ValueError("persisted investigation continued after runtime failure")
                break
            branches = self._apply_success(
                investigation,
                branches,
                result,
                knowledge_store,
            )
        return self._normalize_branches(investigation, branches)

    def _finish(
        self,
        investigation: InvestigationRequest,
        state: RunState,
        branches: Sequence[InvestigationBranch],
    ) -> InvestigationUpdate:
        result = self._result(investigation, branches)
        completed = RuntimeEngine.complete(state, self._outcome(result))
        if completed.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("investigation completion lost its transition")
        return InvestigationUpdate(
            progress=InvestigationProgress(
                investigation=investigation,
                state=completed.state,
                branches=tuple(branches),
                result=result,
            ),
            transitions=(completed.transition,),
        )

    def start(
        self,
        investigation: InvestigationRequest,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> InvestigationUpdate:
        if not isinstance(investigation, InvestigationRequest):
            raise TypeError("investigation start requires an InvestigationRequest")
        started = RuntimeEngine.start(investigation.canonical_run())
        if started.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("investigation start lost its transition")
        resumed = self.resume(
            investigation,
            started.state,
            knowledge_store=knowledge_store,
        )
        return InvestigationUpdate(
            progress=resumed.progress,
            transitions=(started.transition, *resumed.transitions),
        )

    def resume(
        self,
        investigation: InvestigationRequest,
        state: RunState,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> InvestigationUpdate:
        if not isinstance(investigation, InvestigationRequest):
            raise TypeError("investigation resume requires an InvestigationRequest")
        if not isinstance(state, RunState):
            raise TypeError("investigation resume requires a RunState")
        branches = self._reconstruct(investigation, state, knowledge_store)

        if state.status in {"failed", "cancelled"}:
            if not state.failures or not state.results or state.outcome is None:
                raise ValueError("terminal investigation failure has incomplete runtime state")
            failure = state.failures[-1]
            settled = self._policy.settle(
                investigation,
                branches,
                reason="runtime-failure",
            )
            result = self._result(
                investigation,
                settled,
                failure_result=state.results[-1],
                terminal_status=state.status,
                terminal_failure=failure,
            )
            if state.outcome != self._outcome(result):
                raise ValueError("persisted investigation failure outcome has drifted")
            return InvestigationUpdate(
                progress=InvestigationProgress(
                    investigation=investigation,
                    state=state,
                    branches=settled,
                    result=result,
                ),
                transitions=(),
            )

        if state.status == "completed":
            if state.outcome is None:
                raise ValueError("completed investigation lost its outcome")
            result = self._result(investigation, branches)
            if state.outcome != self._outcome(result):
                raise ValueError("persisted investigation outcome has drifted")
            return InvestigationUpdate(
                progress=InvestigationProgress(
                    investigation=investigation,
                    state=state,
                    branches=branches,
                    result=result,
                ),
                transitions=(),
            )

        progress = InvestigationProgress(
            investigation=investigation,
            state=state,
            branches=branches,
        )
        if state.status == "waiting":
            return InvestigationUpdate(progress=progress, transitions=())
        action = self._next_action(investigation, branches)
        if action is None:
            settled = self._policy.settle(investigation, branches)
            return self._finish(investigation, state, settled)
        requested = RuntimeEngine.request(state, action)
        if requested.transition is None:  # pragma: no cover - runtime invariant
            raise RuntimeError("investigation action request lost its transition")
        return InvestigationUpdate(
            progress=InvestigationProgress(
                investigation=investigation,
                state=requested.state,
                branches=branches,
            ),
            transitions=(requested.transition,),
        )

    def _require_canonical_frontier(
        self,
        progress: InvestigationProgress,
        knowledge_store: KnowledgeStore | None,
    ) -> None:
        if not isinstance(progress, InvestigationProgress):
            raise TypeError("investigation progress must be an InvestigationProgress")
        resumed = self.resume(
            progress.investigation,
            progress.state,
            knowledge_store=knowledge_store,
        )
        if resumed.transitions or resumed.progress != progress:
            raise ValueError("investigation progress is not the canonical persisted frontier")

    def submit(
        self,
        progress: InvestigationProgress,
        action_result: ActionResult,
        *,
        knowledge_store: KnowledgeStore | None = None,
    ) -> InvestigationUpdate:
        if not isinstance(progress, InvestigationProgress):
            raise TypeError("investigation submission requires InvestigationProgress")
        if progress.result is not None or len(progress.state.pending_actions) != 1:
            raise ValueError("investigation submission requires one pending action")
        self._require_canonical_frontier(progress, knowledge_store)
        pending = progress.state.pending_actions[0]
        if not isinstance(action_result, ActionResult) or action_result.action != pending:
            raise ValueError("investigation result does not match the exact pending action")
        if pending.kind == INVESTIGATION_REASONING_ACTION_KIND:
            InvestigationReasoningResultValidator().validate(progress.state, action_result)
        elif pending.kind == INVESTIGATION_EXPERIMENT_ACTION_KIND:
            InvestigationExperimentResultValidator().validate(progress.state, action_result)
        else:  # pragma: no cover - canonical frontier invariant
            raise RuntimeError("investigation pending action kind is unsupported")
        submitted = RuntimeEngine.submit(progress.state, action_result)
        if submitted.transition is None:
            raise ValueError("investigation workflow does not accept duplicate submissions")
        resumed = self.resume(
            progress.investigation,
            submitted.state,
            knowledge_store=knowledge_store,
        )
        return InvestigationUpdate(
            progress=resumed.progress,
            transitions=(submitted.transition, *resumed.transitions),
        )

    @staticmethod
    def step(progress: InvestigationProgress) -> InvestigationStep:
        if not isinstance(progress, InvestigationProgress):
            raise TypeError("investigation step requires InvestigationProgress")
        return InvestigationStep(
            state=progress.state,
            actions=progress.state.pending_actions,
            branches=progress.branches,
            result=progress.result,
        )

    def run_managed(
        self,
        progress: InvestigationProgress,
        *,
        reasoner: Reasoner | None = None,
        experimenter: Experimenter | None = None,
        knowledge_store: KnowledgeStore | None = None,
    ) -> InvestigationUpdate:
        transitions: list[Transition] = []
        current = progress
        while True:
            self._require_canonical_frontier(current, knowledge_store)
            if current.result is not None:
                break
            action = current.state.pending_actions[0]
            if action.kind == INVESTIGATION_REASONING_ACTION_KIND:
                if not isinstance(reasoner, Reasoner):
                    raise TypeError("managed investigation reasoning requires a Reasoner")
                result = reasoner.reason(action)
            elif action.kind == INVESTIGATION_EXPERIMENT_ACTION_KIND:
                if not isinstance(experimenter, Experimenter):
                    raise TypeError("managed investigation experiments require an Experimenter")
                result = experimenter.experiment(action)
            else:  # pragma: no cover - canonical frontier invariant
                raise RuntimeError("managed investigation action kind is unsupported")
            update = self.submit(
                current,
                result,
                knowledge_store=knowledge_store,
            )
            transitions.extend(update.transitions)
            current = update.progress
        return InvestigationUpdate(progress=current, transitions=tuple(transitions))


def investigate(
    *,
    question: Question,
    target_snapshot: TargetSnapshot | None = None,
    investigation_id: str = "investigation",
    initial_hypotheses: Sequence[Hypothesis] = (),
    portfolio_mode: str = "parallel",
    max_hypotheses: int = 4,
    max_experiments: int = 6,
    max_redesigns_per_hypothesis: int = 1,
    knowledge_store: KnowledgeStore | None = None,
    reasoner: Reasoner | None = None,
    experimenter: Experimenter | None = None,
    policy: InvestigationPolicy | None = None,
) -> InvestigationResult:
    """Complete one managed investigation over the same public transitions."""

    if not isinstance(question, Question):
        raise TypeError("investigate requires a Question")
    request = InvestigationRequest.for_question(
        investigation_id=investigation_id,
        question=question,
        target_snapshot=target_snapshot,
        initial_hypotheses=initial_hypotheses,
        portfolio_mode=portfolio_mode,
        max_hypotheses=max_hypotheses,
        max_experiments=max_experiments,
        max_redesigns_per_hypothesis=max_redesigns_per_hypothesis,
    )
    workflow = InvestigationWorkflow(policy)
    started = workflow.start(request, knowledge_store=knowledge_store)
    completed = workflow.run_managed(
        started.progress,
        reasoner=reasoner,
        experimenter=experimenter,
        knowledge_store=knowledge_store,
    )
    if completed.progress.result is None:  # pragma: no cover - managed invariant
        raise RuntimeError("managed investigation did not produce a result")
    return completed.progress.result
