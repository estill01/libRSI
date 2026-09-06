"""Translate consumer measurements into the existing workflow capability contracts."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import fmean
from typing import Literal

from ..application import (
    APPLY_CANDIDATE_ACTION_KIND,
    application_command_from_action,
    make_application_success,
    make_rollback_success,
    make_verification_result,
    rollback_input_from_action,
    verification_input_from_action,
)
from ..comparison import CandidateTrialBatch
from ..evaluation import ExperimentEvaluator
from ..identity import thaw
from ..intent import Baseline, EvaluationContract, Objective, StoppingRule
from ..interventions import CandidateSnapshot, InterventionImplementationRequest, InterventionSpec
from ..investigation import (
    INVESTIGATION_EXPERIMENT_ACTION_KIND,
    InvestigationEvidenceBatch,
    InvestigationResult,
    investigation_experiment_request_from_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
)
from ..local.learning import LocalLearningStore
from ..reasoning import ReasoningResult, make_reasoning_action_result, reasoning_request_from_action
from ..records import (
    DecisionRule,
    Evidence,
    Goal,
    Hypothesis,
    Measurement,
    Observation,
    TargetSnapshot,
    record_from_dict,
)
from ..rsi import evaluation_command_from_action, make_evaluation_result
from ..runtime import Action, ActionResult
from .learning_records import LearningAdapter, LearningCase, LearningPolicy, TaskMeasurement


def case_from_record(record: Observation) -> LearningCase:
    if not isinstance(record, Observation) or record.kind != "learning.case":
        raise ValueError("expected an exact learning case")
    case = LearningCase(record.value["case_id"], record.value["payload"])
    if case.record != record:
        raise ValueError("learning case has unexpected data or lineage")
    return case


class LearningHost:
    """Internal capability adapter; semantic acceptance remains in native policies."""

    def __init__(
        self,
        store: LocalLearningStore,
        inputs: Observation,
        policy: LearningPolicy,
        adapter: LearningAdapter,
    ) -> None:
        self.store, self.inputs, self.policy, self.adapter = store, inputs, policy, adapter
        self.pass_id = inputs.value["pass_id"]
        assert inputs.target_snapshot is not None
        self.baseline = inputs.target_snapshot
        self.training = self._cases("training")
        self.shadow = self._cases("shadow")
        self.verification = self._cases("verification")

    def _cases(self, key: str) -> tuple[LearningCase, ...]:
        return tuple(
            case_from_record(record_from_dict(thaw(value)))  # type: ignore[arg-type]
            for value in self.inputs.value[key]
        )

    def measure(self, snapshot: TargetSnapshot, case: LearningCase, stage: str) -> Observation:
        key = f"measure:{stage}:{snapshot.root}:{case.record.root}"
        expected_refs = (self.inputs.ref, snapshot.ref, case.record.ref)
        cached = self.store.cached(self.pass_id, key)
        if cached is not None:
            if (
                not isinstance(cached, Observation)
                or cached.kind != "learning.measurement"
                or cached.source_refs != expected_refs
                or cached.target_snapshot != snapshot
                or cached.value["adapter_id"] != self.adapter.adapter_id
            ):
                raise ValueError("cached measurement does not match its exact inputs")
            TaskMeasurement(cached.value["output"], cached.value["value"])
            return cached
        measured = self.adapter.evaluate(snapshot.state, case)
        if not isinstance(measured, TaskMeasurement):
            raise TypeError("learning adapter must return TaskMeasurement")
        observation = Observation(
            kind="learning.measurement",
            value={
                "output": measured.output,
                "value": measured.value,
                "adapter_id": self.adapter.adapter_id,
            },
            target_snapshot=snapshot,
            source_refs=expected_refs,
        )
        self.store.remember(self.pass_id, key, observation)
        return observation

    def contract(self) -> EvaluationContract:
        metric = self.policy.metric
        goal = Goal(statement=self.policy.objective, target=self.baseline.target)
        baseline_value = fmean(
            self.measure(self.baseline, case, "training").value["value"] for case in self.training
        )
        return EvaluationContract.create(
            contract_id=f"{self.pass_id}:objective",
            goal=goal,
            baseline=Baseline.create(
                snapshot=self.baseline, measurements={metric.metric_id: baseline_value}
            ),
            objectives=(
                Objective.create(
                    objective_id=f"{self.pass_id}:score",
                    metric=metric,
                    semantics="maximize" if metric.direction == "increase" else "minimize",
                    goal=goal,
                    minimum_effect=self.policy.minimum_effect,
                ),
            ),
            constraints=(),
            guardrails=(),
            stopping_rules=(
                StoppingRule(
                    rule_id="sufficient-improvement",
                    kind="criteria-sufficient",
                    condition="Stop after a candidate meets the measured criterion",
                ),
            ),
        )

    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        return make_reasoning_action_result(
            action=action,
            result=ReasoningResult.propose(
                request=request,
                content=make_investigation_observation_content(
                    request,
                    measurements=(self.policy.metric.metric_id,),
                ),
            ),
        )

    def experiment(self, action: Action) -> ActionResult:
        if action.kind != INVESTIGATION_EXPERIMENT_ACTION_KIND:
            command = evaluation_command_from_action(action)
            return make_evaluation_result(
                action=action,
                batch=self.compare(command.contract, command.candidate, command.stage),
            )
        request = investigation_experiment_request_from_action(action)
        hypothesis = request.branch.hypothesis
        candidate = self.store.snapshot(hypothesis.causal_model["configuration"])
        evidence = []
        for case in self.training:
            before = self.measure(self.baseline, case, "training")
            after = self.measure(candidate, case, "training")
            delta = after.value["value"] - before.value["value"]
            favorable = delta if self.policy.metric.direction == "increase" else -delta
            evidence.append(
                Evidence(
                    evidence_type="support" if favorable > 0 else "counterexample",
                    data={
                        "case": case.case_id,
                        "baseline": before.value["value"],
                        "candidate": after.value["value"],
                    },
                    subject_refs=(hypothesis.ref,),
                    source_refs=(request.experiment.ref,),
                    lineage=(request.experiment.ref, before.ref, after.ref),
                    target_snapshot=self.baseline,
                    weight=1,
                )
            )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )

    def candidates(self, investigation: InvestigationResult) -> tuple[CandidateSnapshot, ...]:
        candidates = []
        for branch in investigation.branches:
            if branch.status != "supported":
                continue
            snapshot = self.store.snapshot(branch.hypothesis.causal_model["configuration"])
            intervention = InterventionSpec.create(
                intervention_id=f"{self.pass_id}:{snapshot.root}",
                baseline=self.baseline,
                kind="strategy-configuration",
                specification=snapshot.state,
                rationale=(branch.hypothesis.statement,),
                supporting_refs=(branch.hypothesis.ref,),
                evidence=tuple(item for item in branch.evidence if item.evidence_type == "support"),
                expected_effects={self.policy.metric.metric_id: self.policy.metric.direction},
                risks=("A strategy may not generalize to held-out tasks",),
                constraints=(),
                validation_plan={"historical": True, "forward_shadow": True, "verify": True},
                rollback_expectations={"snapshot": self.baseline.root},
            )
            candidates.append(
                CandidateSnapshot.prepared(
                    request=InterventionImplementationRequest.for_intervention(
                        intervention,
                        candidate_id=f"{self.pass_id}:{snapshot.root}",
                    ),
                    snapshot=snapshot,
                )
            )
        return tuple(candidates)

    def compare(
        self,
        contract: EvaluationContract,
        candidate: CandidateSnapshot,
        stage: str,
    ) -> CandidateTrialBatch:
        cases: Sequence[LearningCase] = {
            "training": self.training,
            "historical": self.training,
            "forward-shadow": self.shadow,
            "verification": self.verification,
        }[stage]
        metric = self.policy.metric
        evaluator = ExperimentEvaluator()
        experiment = evaluator.design(
            experiment_id=f"{self.pass_id}:{stage}:{candidate.snapshot.root}",
            subject=Hypothesis(
                statement="The proposed strategy improves the configured objective",
                target=self.baseline.target,
                lineage=(candidate.ref, contract.ref),
            ),
            kind="controlled-strategy-comparison",
            metrics=(metric,),
            decision_rules=(
                DecisionRule(
                    metric=metric.ref,
                    kind="baseline_delta",
                    minimum_effect=self.policy.minimum_effect,
                    required_valid_trials=2,
                ),
            ),
            baseline_snapshot=self.baseline,
            candidate_snapshot=candidate.snapshot,
            repetitions=len(cases),
            seeds=tuple(range(len(cases))),
            validity_requirements={"require_all_metrics": True},
        )
        results = []
        roles: tuple[Literal["baseline", "candidate"], ...] = ("baseline", "candidate")
        for role in roles:
            snapshot = self.baseline if role == "baseline" else candidate.snapshot
            for index, case in enumerate(cases):
                measured = self.measure(snapshot, case, stage)
                trial = evaluator.prepare_trial(experiment, index=index, role=role)
                observation = Observation(
                    kind="learning.trial",
                    value=measured.value["value"],
                    target_snapshot=snapshot,
                    source_refs=(trial.ref, measured.ref),
                )
                measurement = Measurement(
                    metric=metric.metric_id,
                    metric_ref=metric.ref,
                    value=measured.value["value"],
                    unit=metric.unit,
                    target_snapshot=snapshot,
                    observation_refs=(observation.ref,),
                )
                results.append(
                    evaluator.record_result(
                        experiment,
                        trial=trial,
                        disposition="valid",
                        observations=(observation,),
                        measurements=(measurement,),
                    )
                )
        return CandidateTrialBatch.create(
            contract=contract,
            candidate=candidate,
            experiment=experiment,
            results=results,
        )

    def apply(self, action: Action) -> ActionResult:
        if action.kind == APPLY_CANDIDATE_ACTION_KIND:
            command = application_command_from_action(action)
            if command.governance_authority is None:
                raise ValueError(
                    "adaptive strategy activation requires native self-change approval"
                )
            observed = self.store.apply_snapshot(
                expected=command.prior_snapshot,
                replacement=command.candidate.snapshot,
                effect_root=action.root,
            )
            return make_application_success(action=action, produced_snapshot=observed)
        application, _ = rollback_input_from_action(action)
        restored = self.store.apply_snapshot(
            expected=application.produced_snapshot,
            replacement=application.prior_snapshot,
            effect_root=action.root,
        )
        return make_rollback_success(action=action, restored_snapshot=restored)

    def verify(self, action: Action) -> ActionResult:
        application = verification_input_from_action(action)
        command = application_command_from_action(application.action)
        observed = self.store.active
        actual = CandidateSnapshot.prepared(request=command.candidate.request, snapshot=observed)
        return make_verification_result(
            action=action,
            observed_snapshot=observed,
            batch=self.compare(command.contract, actual, "verification"),
        )
