"""Deterministic canonical results reused by Block 19 projection tests."""

from __future__ import annotations

from functools import lru_cache

from librsi import (
    Action,
    ActionResult,
    Claim,
    Evidence,
    InvestigationEvidenceBatch,
    InvestigationResult,
    Question,
    ReasoningResult,
    RSIResult,
    ValidationResult,
    improve,
    investigate,
    investigation_experiment_request_from_action,
    make_investigation_experiment_result,
    make_investigation_observation_content,
    make_reasoning_action_result,
    reasoning_request_from_action,
    recurse,
    validate,
)
from librsi.improvement import ImprovementResult
from tests.block14_support import comparison_context
from tests.block15_support import DeterministicCycleProvider, improvement_request
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import (
    DeterministicGovernanceProvider,
    self_change_registry,
    self_change_request,
)


class _CompetingReasoner:
    def reason(self, action: Action) -> ActionResult:
        request = reasoning_request_from_action(action)
        content: dict[str, object]
        if request.kind == "hypothesis-generation":
            content = {
                "hypotheses": [
                    {
                        "statement": "The inlet is limiting the observed rate",
                        "causal_model": {"cause": "inlet"},
                        "predictions": [{"signal": "inlet-pressure"}],
                        "confidence": 0.9,
                    },
                    {
                        "statement": "The outlet is limiting the observed rate",
                        "causal_model": {"cause": "outlet"},
                        "predictions": [{"signal": "outlet-pressure"}],
                        "confidence": 0.1,
                    },
                ]
            }
        else:
            content = make_investigation_observation_content(
                request,
                measurements=("pressure-response",),
            )
        return make_reasoning_action_result(
            action=action,
            result=ReasoningResult.propose(request=request, content=content),
        )


class _DiscriminatingExperimenter:
    def experiment(self, action: Action) -> ActionResult:
        request = investigation_experiment_request_from_action(action)
        relationship = "counterexample" if request.branch.branch_id == "hypothesis-1" else "support"
        evidence = tuple(
            Evidence(
                evidence_type=relationship,
                data={"sample": sample, "branch": request.branch.branch_id},
                subject_refs=(request.branch.hypothesis.ref,),
                source_refs=(request.experiment.ref,),
                target_snapshot=request.investigation.target_snapshot,
                weight=1.0,
            )
            for sample in (1, 2)
        )
        return make_investigation_experiment_result(
            action=action,
            batch=InvestigationEvidenceBatch.collected(request=request, evidence=evidence),
        )


@lru_cache(maxsize=1)
def workflow_results() -> tuple[
    ValidationResult,
    InvestigationResult,
    ImprovementResult,
    RSIResult,
]:
    claim = Claim(statement="The invariant holds", kind="invariant")
    validation = validate(
        claim=claim,
        validation_id="block19-validation",
        evidence=tuple(
            Evidence(
                evidence_type="support",
                data={"sample": sample},
                subject_refs=(claim.ref,),
                source_refs=(claim.ref,),
                weight=1.0,
            )
            for sample in (1, 2)
        ),
    )
    investigation = investigate(
        question=Question(prompt="What limits the observed process rate?"),
        investigation_id="block19-investigation",
        reasoner=_CompetingReasoner(),
        experimenter=_DiscriminatingExperimenter(),
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    improvement_context = comparison_context()
    improvement = improve(
        improvement_request(improvement_context),
        provider=DeterministicCycleProvider(improvement_context, (True,)),
        current_snapshot=improvement_context.baseline_snapshot,
    )
    rsi_context = comparison_context(target_kind="improvement-policy-bundle")
    rsi_request = self_change_request(rsi_context)
    rsi = recurse(
        rsi_request,
        current_snapshot=rsi_context.baseline_snapshot,
        registry=self_change_registry(
            DeterministicGovernanceProvider(rsi_context),
            DeterministicApplicationTarget(rsi_context.baseline_snapshot),
        ),
    )
    if not isinstance(rsi, RSIResult):  # pragma: no cover - managed recursion contract
        raise RuntimeError("managed RSI fixture did not return a result")
    return validation, investigation, improvement, rsi
