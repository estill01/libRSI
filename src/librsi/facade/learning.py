"""Opt-in, serialized adaptive strategy operation for embedded consumers."""

from __future__ import annotations

from collections.abc import Sequence

from ..capabilities import Reviewer
from ..comparison import ComparativeSelectionPolicy
from ..identity import digest
from ..improvement import ImprovementBudget, ImprovementRequest
from ..intent import OperationalizationPolicy, OperationalizationRequest
from ..investigation import InvestigationRequest
from ..reasoning import (
    ReasoningBackend,
)
from ..records import Hypothesis, Observation, Outcome, Question
from ..rsi import (
    MetaTargetDeclaration,
    RSIRequest,
    SelfChangeGovernancePolicy,
    SelfChangePolicy,
)
from ..runtime import RuntimeStore
from .learning_history import LearningAttempt, history
from .learning_host import LearningHost
from .learning_inputs import cases, prepare
from .learning_reasoning import reason
from .learning_records import LearningAdapter, LearningCase, LearningPolicy, TaskMeasurement
from .learning_requests import proposal_request, reflection_request
from .learning_results import LearningResult, LearningTerminal, learning_result
from .learning_store import LearningStore
from .learning_workflows import improve, investigate, recurse


class AdaptiveLoop:
    """Run ordinary tasks and explicitly requested bounded learning passes.

    Use one serialized owner per profile. The caller schedules passes, supplies held-out
    cases, versions adapter/provider identities, and bounds individual host calls.
    ``activate=False`` evaluates without changing the active strategy.
    """

    def __init__(
        self,
        store: LearningStore,
        *,
        adapter: LearningAdapter,
        proposer: ReasoningBackend,
        proposer_id: str,
        reviewer: Reviewer,
        reviewer_id: str,
        policy: LearningPolicy,
    ) -> None:
        if not isinstance(store, LearningStore):
            raise TypeError("adaptive operation requires a LearningStore")
        if not isinstance(store.runtime, RuntimeStore):
            raise TypeError("adaptive operation requires a RuntimeStore")
        if not isinstance(policy, LearningPolicy):
            raise TypeError("adaptive operation requires a LearningPolicy")
        if not isinstance(adapter, LearningAdapter) or not isinstance(proposer, ReasoningBackend):
            raise TypeError("adaptive operation requires an adapter and ReasoningBackend")
        if not callable(getattr(reviewer, "review", None)):
            raise TypeError("independent reviewer must implement review(Action)")
        ids = (adapter.adapter_id, proposer_id, reviewer_id)
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("adapter, proposer, and reviewer require versioned identities")
        if proposer_id == reviewer_id or proposer is reviewer:
            raise ValueError("proposer and reviewer must be independent")
        adapter.validate_configuration(store.active.state)
        self.store, self.adapter, self.proposer = store, adapter, proposer
        self.proposer_id, self.reviewer, self.reviewer_id = proposer_id, reviewer, reviewer_id
        self.policy = policy

    def history(self, *, limit: int = 2) -> tuple[LearningAttempt, ...]:
        """Inspect bounded native attempts; use only attempt.feedback for reasoning."""
        return history(self.store, limit=limit)

    def run_task(self, case: LearningCase) -> Observation:
        if not isinstance(case, LearningCase):
            raise TypeError("ordinary tasks require LearningCase")
        existing = self.store.feedback(case.case_id)
        if existing:
            item = existing[0]
            if (
                digest(item.value["case"]) != digest(case.record.to_dict())
                or item.value["adapter_id"] != self.adapter.adapter_id
                or item.value["metric_root"] != self.policy.metric.root
            ):
                raise ValueError("task id already names different inputs or scoring")
            return item
        if self.store.pending_pass is not None:
            raise RuntimeError("resume the pending learning pass before ordinary tasks")
        snapshot = self.store.active
        measured = self.adapter.evaluate(snapshot.state, case)
        if not isinstance(measured, TaskMeasurement):
            raise TypeError("learning adapter must return TaskMeasurement")
        return self.store.record_feedback(
            Observation(
                kind="learning.feedback",
                target_snapshot=snapshot,
                value={
                    "task_id": case.case_id,
                    "case": case.record.to_dict(),
                    "output": measured.output,
                    "value": measured.value,
                    "adapter_id": self.adapter.adapter_id,
                    "metric_id": self.policy.metric.metric_id,
                    "metric_root": self.policy.metric.root,
                },
                source_refs=(case.record.ref, snapshot.ref),
            )
        )

    def learn(
        self,
        pass_id: str,
        *,
        shadow_cases: Sequence[LearningCase],
        verification_cases: Sequence[LearningCase] | None = None,
        activate: bool = False,
        follow_up_to: str | None = None,
    ) -> LearningResult | None:
        """Resume an exact pass, or start one when enough unused feedback exists.

        Returns None when not due. Reusing a completed pass id returns its historical
        result without repeating work. A new pass normally requires fresh feedback.
        ``follow_up_to`` names a completed unsuccessful predecessor for one bounded
        retry using its training batch and new held-out cases. Policy controls the
        finite lineage allowance, retained history and optional reflection call.
        """
        shadow = cases(self.policy, shadow_cases)
        verification = (
            shadow if verification_cases is None else cases(self.policy, verification_cases)
        )
        inputs = prepare(
            self.store,
            policy=self.policy,
            adapter_id=self.adapter.adapter_id,
            proposer_id=self.proposer_id,
            reviewer_id=self.reviewer_id,
            pass_id=pass_id,
            shadow=shadow,
            verification=verification,
            activate=activate,
            follow_up_to=follow_up_to,
        )
        if inputs is None:
            return None
        host = LearningHost(self.store, inputs, self.policy, self.adapter)
        cached = self.store.cached(pass_id, "result")
        if cached is not None:
            if self.store.pending_pass == pass_id:
                return self._finish(host, cached)  # type: ignore[arg-type]
            return self._result(host, cached)  # type: ignore[arg-type]
        reflection = None
        reflection_task = reflection_request(inputs)
        if reflection_task is not None:
            reflected = reason(host, self.proposer, reflection_task)
            if isinstance(reflected, Outcome):
                return self._finish(host, reflected)
            reflection = reflected
        proposal = reason(host, self.proposer, proposal_request(inputs, reflection))
        if isinstance(proposal, Outcome):
            return self._finish(host, proposal)
        question = Question(
            prompt=self.policy.objective,
            target=self.store.target,
            context={"baseline": host.baseline.root},
        )
        hypotheses = tuple(
            Hypothesis(
                statement=item["statement"],
                causal_model=item["causal_model"],
                predictions=tuple(item["predictions"]),
                confidence=item["confidence"],
                target=self.store.target,
                source_refs=(question.ref, proposal.ref),
            )
            for item in proposal.content["hypotheses"]
        )
        investigation = investigate(
            host,
            InvestigationRequest.for_question(
                investigation_id=f"{pass_id}:investigate",
                question=question,
                target_snapshot=host.baseline,
                initial_hypotheses=hypotheses,
                max_hypotheses=len(hypotheses),
                max_experiments=len(hypotheses),
                max_redesigns_per_hypothesis=0,
            ),
        )
        candidates = host.candidates(investigation)
        if not candidates:
            return self._finish(host, investigation)
        contract = host.contract()
        governance = SelfChangeGovernancePolicy.strict()
        declaration = MetaTargetDeclaration.create(
            declaration_id=f"{pass_id}:strategy",
            target_snapshot=host.baseline,
            change_classes=("reasoner",),
            candidate_author_id=self.proposer_id,
        )
        batches = tuple(host.compare(contract, candidate, "training") for candidate in candidates)
        selection = ComparativeSelectionPolicy.select(
            selection_id=f"{pass_id}:screen",
            contract=contract,
            batches=batches,
            risk_policy=governance.risk_policy,
        )
        self.store.remember(pass_id, "screening", selection)
        if selection.selected:
            # Native single-objective rank, with its canonical reference order breaking ties.
            batches = tuple(item for item in batches if item.candidate.ref == selection.selected[0])
        request = ImprovementRequest.create(
            request_id=pass_id,
            question=question,
            initial_hypotheses=hypotheses,
            operationalization=OperationalizationPolicy().accept_typed(
                OperationalizationRequest.create(
                    request_id=pass_id, goal=contract.goal, current_snapshot=host.baseline
                ),
                contract,
            ),
            risk_policy=governance.risk_policy,
            governance_requirement=SelfChangePolicy.requirement(declaration, governance),
            budget=ImprovementBudget(
                max_iterations=1,
                max_experiments=len(hypotheses) + len(batches),
                max_retries=0,
                max_resource_units=1,
            ),
        )
        improvement = improve(host, request, investigation, batches)
        if improvement.handoff is None:
            return self._finish(host, improvement)
        result = recurse(
            host,
            RSIRequest.create(
                rsi_id=pass_id,
                declaration=declaration,
                improvement=improvement,
                governance=governance,
                requested_by=self.proposer_id,
                activate=activate,
            ),
            self.reviewer,
        )
        return self._finish(host, result)

    @staticmethod
    def _result(host: LearningHost, native: LearningTerminal) -> LearningResult:
        return learning_result(host.store, host.inputs, native)

    def _finish(self, host: LearningHost, native: LearningTerminal) -> LearningResult:
        result = self._result(host, native)
        if self.store.active != result.strategy_after:
            raise RuntimeError("active strategy does not match the native terminal result")
        self.store.finish_pass(host.pass_id, native)
        return result
