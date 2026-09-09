"""Opt-in, serialized adaptive strategy operation for embedded consumers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from ..capabilities import Reviewer
from ..comparison import ComparativeSelectionPolicy
from ..identity import digest, thaw
from ..improvement import ImprovementBudget, ImprovementRequest, ImprovementResult
from ..intent import OperationalizationPolicy, OperationalizationRequest
from ..investigation import InvestigationRequest, InvestigationResult
from ..reasoning import (
    ReasoningBackend,
    ReasoningRequest,
    ReasoningResult,
    ReasoningResultValidator,
    make_reasoning_action,
    make_reasoning_action_result,
    make_reasoning_failure,
    reasoning_result_from_action_result,
)
from ..records import Hypothesis, Observation, Outcome, Question, TargetSnapshot, record_from_dict
from ..rsi import (
    MetaTargetDeclaration,
    RSIRequest,
    RSIResult,
    SelfChangeGovernancePolicy,
    SelfChangePolicy,
)
from ..runtime import Run, RunBudget, RuntimeEngine, RuntimeFailure, RuntimeStore
from .learning_host import LearningHost, case_from_record
from .learning_records import LearningAdapter, LearningCase, LearningPolicy, TaskMeasurement
from .learning_store import LearningStore
from .learning_workflows import improve, investigate, recorded_action, recurse

LearningTerminal = Outcome | InvestigationResult | ImprovementResult | RSIResult


@dataclass(frozen=True)
class LearningResult:
    """A view of a native terminal result, never an independent acceptance decision."""

    pass_id: str
    native: LearningTerminal
    strategy_after: TargetSnapshot

    @property
    def disposition(self) -> str:
        if isinstance(self.native, Outcome):
            return self.native.status
        if isinstance(self.native, InvestigationResult):
            return (
                "no-supported-revision"
                if self.native.terminal_status == "completed"
                else self.native.terminal_status
            )
        return self.native.disposition

    @property
    def adopted(self) -> bool:
        return isinstance(self.native, RSIResult) and self.native.disposition == "verified"


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

    def _cases(self, cases: Sequence[LearningCase]) -> tuple[LearningCase, ...]:
        if not isinstance(cases, Sequence):
            raise TypeError("evaluation cases require a finite sequence")
        if not 2 <= len(cases) <= self.policy.max_cases:
            raise ValueError("evaluation case count must be between 2 and max_cases")
        items = tuple(cases)
        if any(not isinstance(item, LearningCase) for item in items):
            raise TypeError("evaluation cases must be LearningCase values")
        if len({item.case_id for item in items}) != len(items):
            raise ValueError("evaluation case ids must be unique")
        if len({digest(item.payload) for item in items}) != len(items):
            raise ValueError("evaluation cases must contain distinct payloads")
        return items

    def _inputs(
        self,
        pass_id: str,
        shadow: tuple[LearningCase, ...],
        verification: tuple[LearningCase, ...],
        activate: bool,
    ) -> Observation | None:
        if not isinstance(pass_id, str) or not pass_id.strip() or type(activate) is not bool:
            raise ValueError("learning requires a pass id and boolean activation choice")
        configuration = {
            "policy": self.policy.to_dict(),
            "adapter_id": self.adapter.adapter_id,
            "proposer_id": self.proposer_id,
            "reviewer_id": self.reviewer_id,
            "activate": activate,
            "shadow": [item.record.to_dict() for item in shadow],
            "verification": [item.record.to_dict() for item in verification],
        }
        existing = self.store.pass_input(pass_id)
        if existing is not None:
            if digest(existing.value["configuration"]) != digest(configuration):
                raise ValueError("pass id already names different configuration or cases")
            return existing
        if self.store.pending_pass is not None:
            raise RuntimeError("another learning pass is pending")
        consumed: set[str] = set()
        for previous in self.store.pass_ids:
            inputs = self.store.pass_input(previous)
            assert inputs is not None
            consumed.update(item["root"] for item in inputs.value["feedback"])
        feedback = tuple(item for item in self.store.feedback() if item.root not in consumed)
        if len(feedback) < self.policy.min_new_feedback:
            return None
        feedback = feedback[-min(self.policy.max_feedback, self.policy.max_cases) :]
        if len(feedback) < self.policy.min_new_feedback:
            raise ValueError("max_cases cannot satisfy the configured feedback trigger")
        if any(
            item.value["adapter_id"] != self.adapter.adapter_id
            or item.value["metric_root"] != self.policy.metric.root
            for item in feedback
        ):
            raise ValueError("feedback scoring semantics changed; use a separate profile")
        training = self._cases(
            tuple(
                case_from_record(record_from_dict(thaw(item.value["case"])))  # type: ignore[arg-type]
                for item in feedback
            )
        )
        if {case.case_id for case in training} & {case.case_id for case in shadow} or {
            digest(case.payload) for case in training
        } & {digest(case.payload) for case in shadow}:
            raise ValueError("forward-shadow cases must be held out from training")
        baseline = self.store.active
        inputs = Observation(
            kind="learning.pass",
            target_snapshot=baseline,
            value={
                "pass_id": pass_id,
                "configuration": configuration,
                "feedback": [item.to_dict() for item in feedback],
                "training": [case.record.to_dict() for case in training],
                "shadow": configuration["shadow"],
                "verification": configuration["verification"],
            },
            source_refs=(baseline.ref, *(item.ref for item in feedback)),
        )
        self.store.begin_pass(inputs)
        return inputs

    def _propose(self, host: LearningHost) -> ReasoningResult | Outcome:
        feedback = tuple(
            cast(Observation, record_from_dict(thaw(item)))
            for item in host.inputs.value["feedback"]
        )
        if any(not isinstance(item, Observation) for item in feedback):
            raise ValueError("pass feedback must contain exact observations")
        refs = (host.baseline.ref, *(item.ref for item in feedback))
        request = ReasoningRequest(
            request_id=f"{host.pass_id}:ideas",
            kind="hypothesis-generation",
            instruction=(
                f"Propose 2 to {self.policy.max_candidates} distinct revisions to the active strategy "
                "using measured task feedback. Each causal_model must contain only configuration: "
                "a complete replacement JSON object valid for this adapter. Do not repeat the baseline."
            ),
            input_refs=refs,
            target_snapshot=host.baseline,
            lineage=refs,
            context={
                "configuration": host.baseline.state,
                "policy": self.policy.to_dict(),
                "adapter_id": self.adapter.adapter_id,
                "proposer_id": self.proposer_id,
                "feedback": [
                    {
                        "task_id": item.value["task_id"],
                        "case": case_from_record(
                            cast(Observation, record_from_dict(thaw(item.value["case"])))
                        ).payload,
                        "output": item.value["output"],
                        "value": item.value["value"],
                        "strategy": item.target_snapshot.root if item.target_snapshot else None,
                        "feedback": item.root,
                    }
                    for item in feedback
                ],
            },
        )
        run = Run(
            run_id=f"{host.pass_id}:ideas",
            intent=request.ref,
            target_snapshot=host.baseline,
            budget=RunBudget(
                max_actions=1, max_failures=1, max_retries=0, resource_limits={"calls": 1}
            ),
            lineage=(request.ref,),
        )
        state = self.store.runtime.resume(run.run_id)
        if state is None:
            update = RuntimeEngine.start(run)
            assert update.transition is not None
            state = self.store.runtime.append(update.transition)
        if state.run != run:
            raise ValueError("proposal run inputs have drifted")
        if state.status == "active" and not state.results:
            action = make_reasoning_action(
                run=run,
                action_id=request.request_id,
                request=request,
                budget_reservation={"calls": 1},
            )
            update = RuntimeEngine.request(state, action)
            assert update.transition is not None
            state = self.store.runtime.append(update.transition)
        if state.status == "waiting":
            action = state.pending_actions[0]

            def execute(item):
                try:
                    proposal = self.proposer.respond(request)
                    result = make_reasoning_action_result(
                        action=item, result=proposal, resource_usage={"calls": 1}
                    )
                    hypotheses = proposal.content["hypotheses"]
                    if not 2 <= len(hypotheses) <= self.policy.max_candidates:
                        raise ValueError("proposal count exceeds the candidate allowance")
                    roots = set()
                    for hypothesis in hypotheses:
                        model = hypothesis["causal_model"]
                        if set(model) != {"configuration"}:
                            raise ValueError("strategy proposal must contain only configuration")
                        configuration = model["configuration"]
                        self.adapter.validate_configuration(configuration)
                        snapshot = self.store.snapshot(configuration)
                        if snapshot == host.baseline or snapshot.root in roots:
                            raise ValueError("proposals must be distinct revisions of the baseline")
                        roots.add(snapshot.root)
                    return result
                except Exception as error:
                    return make_reasoning_failure(
                        action=item,
                        resource_usage={"calls": 1},
                        failure=RuntimeFailure(
                            classification="invalid-result"
                            if isinstance(error, (ValueError, TypeError, KeyError))
                            else "execution",
                            message=str(error) or type(error).__name__,
                            retryable=False,
                        ),
                    )

            result = recorded_action(self.store, host.pass_id, action, execute)
            ReasoningResultValidator().validate(state, result)
            update = RuntimeEngine.submit(state, result)
            assert update.transition is not None
            state = self.store.runtime.append(update.transition)
        if state.status == "failed":
            assert state.outcome is not None
            return state.outcome
        proposal = reasoning_result_from_action_result(state.results[-1])
        if state.status != "completed":
            update = RuntimeEngine.complete(
                state,
                Outcome(
                    intent=request.ref,
                    status="proposed",
                    target_snapshot=host.baseline,
                    conclusions=(
                        "Bounded strategy revisions proposed; acceptance remains unevaluated",
                    ),
                    lineage=(proposal.ref,),
                ),
            )
            assert update.transition is not None
            self.store.runtime.append(update.transition)
        return proposal

    def learn(
        self,
        pass_id: str,
        *,
        shadow_cases: Sequence[LearningCase],
        verification_cases: Sequence[LearningCase] | None = None,
        activate: bool = False,
    ) -> LearningResult | None:
        """Resume an exact pass, or start one when enough unused feedback exists.

        Returns None when not due. Reusing a completed pass id returns its historical
        result without repeating work. Use a new id and fresh feedback for the next pass.
        """
        shadow = self._cases(shadow_cases)
        verification = shadow if verification_cases is None else self._cases(verification_cases)
        inputs = self._inputs(pass_id, shadow, verification, activate)
        if inputs is None:
            return None
        host = LearningHost(self.store, inputs, self.policy, self.adapter)
        cached = self.store.cached(pass_id, "result")
        if cached is not None:
            if self.store.pending_pass == pass_id:
                return self._finish(host, cached)  # type: ignore[arg-type]
            return self._result(host, cached)  # type: ignore[arg-type]
        proposal = self._propose(host)
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
        if not isinstance(native, (Outcome, InvestigationResult, ImprovementResult, RSIResult)):
            raise ValueError("pass result is not a native terminal result")
        if isinstance(native, RSIResult):
            matches = (
                native.request.rsi_id == host.pass_id
                and native.request.declaration.target_snapshot == host.baseline
            )
        elif isinstance(native, ImprovementResult):
            matches = (
                native.request.request_id == host.pass_id
                and native.request.baseline == host.baseline
            )
        elif isinstance(native, InvestigationResult):
            matches = (
                native.investigation.investigation_id == f"{host.pass_id}:investigate"
                and native.investigation.target_snapshot == host.baseline
            )
        else:
            state = host.store.runtime.resume(f"{host.pass_id}:ideas")
            matches = state is not None and state.status == "failed" and state.outcome == native
        if not matches:
            raise ValueError("terminal result belongs to another learning pass")
        after = native.authoritative_snapshot if isinstance(native, RSIResult) else host.baseline
        if after is None:
            raise RuntimeError("native result leaves strategy authority unresolved")
        return LearningResult(host.pass_id, native, after)

    def _finish(self, host: LearningHost, native: LearningTerminal) -> LearningResult:
        result = self._result(host, native)
        if self.store.active != result.strategy_after:
            raise RuntimeError("active strategy does not match the native terminal result")
        self.store.finish_pass(host.pass_id, native)
        return result
