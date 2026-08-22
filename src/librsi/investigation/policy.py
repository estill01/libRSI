"""Deterministic hypothesis-lane, budget, and stopping policy for investigation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from ..epistemics import EVIDENCE_RELATIONSHIPS, EpistemicPolicy, LinearEvidenceAggregator
from ..identity import FrozenMap
from ..portfolios import PortfolioPolicy
from ..reasoning import ReasoningRequest, ReasoningResult
from ..records import BeliefState, Evidence, EvidenceRef, ExperimentSpec, Hypothesis, RecordRef
from ..runtime import ActionResult
from .records import (
    InvestigationBranch,
    InvestigationEvidenceBatch,
    InvestigationFinding,
    InvestigationRequest,
    InvestigationResult,
    _investigation_stop_reason,
    investigation_unresolved,
)

INVESTIGATION_OBSERVATION_METHODS = frozenset({"measure", "observe", "retrieve"})
INVESTIGATION_OBSERVATION_METHOD_ORDER = ("measure", "observe", "retrieve")
INVESTIGATION_EVIDENCE_RELATIONSHIPS = tuple(sorted(EVIDENCE_RELATIONSHIPS))
_MEASUREMENT_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")
_DESIGN_KEYS = frozenset({"method", "measurements"})
_CRITERIA_KEYS = frozenset({"accepted_relationships", "minimum_evidence_items"})


def _measurement_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("investigation measurements must be a sequence")
    items = tuple(value)
    if not items or any(
        type(item) is not str or _MEASUREMENT_ID.fullmatch(item) is None for item in items
    ):
        raise ValueError("investigation measurements require bounded identifier values")
    if len(set(items)) != len(items):
        raise ValueError("investigation measurements must be unique")
    return cast(tuple[str, ...], items)


def make_investigation_observation_content(
    request: ReasoningRequest,
    *,
    measurements: Sequence[str],
    method: str = "measure",
) -> dict[str, object]:
    """Build the closed provider-facing content for one investigation design request."""

    if not isinstance(request, ReasoningRequest) or request.kind != "experiment-design":
        raise TypeError("investigation observation content requires an experiment-design request")
    if request.context.get("workflow") != "investigation":
        raise ValueError("investigation observation content requires an investigation request")
    allowed_methods = request.context.get("allowed_design_methods")
    if allowed_methods != INVESTIGATION_OBSERVATION_METHOD_ORDER:
        raise ValueError("investigation design request lost its canonical method contract")
    if type(method) is not str or method not in allowed_methods:
        raise ValueError("investigation observation method must be observation-only")
    items = _measurement_ids(measurements)
    objective = request.context.get("required_objective")
    if type(objective) is not str:
        raise ValueError("investigation design request lost its required objective")
    criteria = request.context.get("required_criteria")
    if not isinstance(criteria, FrozenMap):
        raise ValueError("investigation design request lost its required criteria")
    relationships = criteria.get("accepted_relationships")
    minimum = criteria.get("minimum_evidence_items")
    if (
        not isinstance(relationships, tuple)
        or any(type(item) is not str for item in relationships)
        or relationships != INVESTIGATION_EVIDENCE_RELATIONSHIPS
        or type(minimum) is not int
        or minimum != 1
    ):
        raise ValueError("investigation design request lost its canonical evidence contract")
    return {
        "experiments": [
            {
                "objective": objective,
                "design": {"method": method, "measurements": list(items)},
                "criteria": {
                    "accepted_relationships": list(relationships),
                    "minimum_evidence_items": minimum,
                },
                "requested_measurements": list(items),
            }
        ]
    }


@dataclass(frozen=True, slots=True)
class InvestigationPolicy:
    """Owned built-in epistemic and portfolio semantics for bounded investigation."""

    epistemics: EpistemicPolicy = field(default_factory=EpistemicPolicy)
    portfolios: PortfolioPolicy = field(default_factory=PortfolioPolicy)

    def __post_init__(self) -> None:
        self._require_canonical()

    def _require_canonical(self) -> None:
        if (
            type(self) is not InvestigationPolicy
            or type(self.epistemics) is not EpistemicPolicy
            or type(self.portfolios) is not PortfolioPolicy
            or getattr(self.portfolios, "__dict__", None) != {}
        ):
            raise ValueError(
                "investigation policy changes require a versioned semantic policy contract"
            )
        aggregator = self.epistemics.aggregator
        canonical_fields = (
            ("support_scale", float, 0.2),
            ("counterexample_scale", float, 0.2),
            ("qualification_scale", float, 0.05),
            ("supported_threshold", float, 0.75),
            ("rejected_threshold", float, 0.2),
            ("null_is_neutral", bool, True),
        )
        if type(aggregator) is not LinearEvidenceAggregator or any(
            type(getattr(aggregator, name)) is not expected_type
            or getattr(aggregator, name) != expected_value
            for name, expected_type, expected_value in canonical_fields
        ):
            raise ValueError(
                "investigation policy changes require a versioned semantic policy contract"
            )

    @classmethod
    def owned_canonical(cls, value: InvestigationPolicy) -> InvestigationPolicy:
        if type(value) is not cls:
            raise TypeError("investigation workflows require an InvestigationPolicy")
        value._require_canonical()
        return cls()

    def belief(
        self,
        investigation: InvestigationRequest,
        hypothesis: Hypothesis,
        evidence: Sequence[Evidence],
    ) -> BeliefState:
        if not isinstance(investigation, InvestigationRequest):
            raise TypeError("investigation belief requires an InvestigationRequest")
        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("investigation belief requires a Hypothesis")
        items = tuple(sorted(evidence, key=lambda item: item.root))
        prior = BeliefState(
            subject_ref=hypothesis.ref,
            status="proposed",
            confidence=0.5,
            target_snapshot=investigation.target_snapshot,
        )
        if not items:
            return prior
        return self.epistemics.aggregate(
            subject=hypothesis,
            evidence=items,
            prior=prior,
            current_snapshot=investigation.target_snapshot,
        )

    def initial_branch(
        self,
        *,
        investigation: InvestigationRequest,
        branch_id: str,
        hypothesis: Hypothesis,
        evidence: Sequence[Evidence] = (),
    ) -> InvestigationBranch:
        items = tuple(sorted(evidence, key=lambda item: item.root))
        reused = tuple(EvidenceRef.from_evidence(item) for item in items)
        belief = self.belief(investigation, hypothesis, items)
        status = (
            "supported"
            if belief.status == "supported"
            else "rejected"
            if belief.status == "rejected"
            else "active"
        )
        return InvestigationBranch(
            investigation=investigation,
            branch_id=branch_id,
            hypothesis=hypothesis,
            belief=belief,
            evidence=items,
            reused_evidence_refs=reused,
            gathered_evidence_refs=(),
            status=status,
            lineage=(
                investigation.ref,
                hypothesis.ref,
                belief.ref,
                *(item.ref for item in items),
            ),
        )

    def add_experiment(
        self,
        branch: InvestigationBranch,
        experiment: ExperimentSpec,
    ) -> InvestigationBranch:
        if not isinstance(branch, InvestigationBranch):
            raise TypeError("experiment design requires an InvestigationBranch")
        if branch.status != "active":
            raise ValueError("terminal investigation branches cannot add experiments")
        if not isinstance(experiment, ExperimentSpec):
            raise TypeError("investigation design requires an ExperimentSpec")
        experiments = (*branch.experiments, experiment)
        return InvestigationBranch(
            investigation=branch.investigation,
            branch_id=branch.branch_id,
            hypothesis=branch.hypothesis,
            belief=branch.belief,
            experiments=experiments,
            evidence=branch.evidence,
            reused_evidence_refs=branch.reused_evidence_refs,
            gathered_evidence_refs=branch.gathered_evidence_refs,
            status="active",
            lineage=(
                branch.investigation.ref,
                branch.hypothesis.ref,
                branch.belief.ref,
                *(item.ref for item in experiments),
                *(item.ref for item in branch.evidence),
            ),
        )

    def apply_batch(
        self,
        branch: InvestigationBranch,
        batch: InvestigationEvidenceBatch,
    ) -> InvestigationBranch:
        if not isinstance(branch, InvestigationBranch):
            raise TypeError("investigation evidence requires an InvestigationBranch")
        if not isinstance(batch, InvestigationEvidenceBatch):
            raise TypeError("investigation evidence requires an InvestigationEvidenceBatch")
        if batch.request.branch != branch:
            raise ValueError("investigation evidence does not match the exact branch frontier")
        if batch.disposition == "unavailable":
            return self.retire(branch, "evidence-unavailable")
        known = {item.ref for item in branch.evidence}
        if any(item.ref in known for item in batch.evidence):
            raise ValueError("investigation evidence has already been considered")
        evidence = tuple(sorted((*branch.evidence, *batch.evidence), key=lambda item: item.root))
        gathered = tuple(
            sorted(
                (
                    *branch.gathered_evidence_refs,
                    *(EvidenceRef.from_evidence(item) for item in batch.evidence),
                ),
                key=lambda item: item.root,
            )
        )
        belief = self.belief(branch.investigation, branch.hypothesis, evidence)
        status = (
            "supported"
            if belief.status == "supported"
            else "rejected"
            if belief.status == "rejected"
            else "active"
        )
        return InvestigationBranch(
            investigation=branch.investigation,
            branch_id=branch.branch_id,
            hypothesis=branch.hypothesis,
            belief=belief,
            experiments=branch.experiments,
            evidence=evidence,
            reused_evidence_refs=branch.reused_evidence_refs,
            gathered_evidence_refs=gathered,
            status=status,
            lineage=(
                branch.investigation.ref,
                branch.hypothesis.ref,
                belief.ref,
                *(item.ref for item in branch.experiments),
                *(item.ref for item in evidence),
            ),
        )

    @staticmethod
    def retire(branch: InvestigationBranch, reason: str) -> InvestigationBranch:
        if not isinstance(branch, InvestigationBranch):
            raise TypeError("branch retirement requires an InvestigationBranch")
        if branch.status != "active":
            return branch
        return InvestigationBranch(
            investigation=branch.investigation,
            branch_id=branch.branch_id,
            hypothesis=branch.hypothesis,
            belief=branch.belief,
            experiments=branch.experiments,
            evidence=branch.evidence,
            reused_evidence_refs=branch.reused_evidence_refs,
            gathered_evidence_refs=branch.gathered_evidence_refs,
            status="retired",
            retired_reason=reason,
            lineage=branch.lineage,
        )

    def prioritized_branch(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
    ) -> InvestigationBranch | None:
        items = tuple(branches)
        eligible = tuple(item for item in items if item.status == "active")
        if not eligible:
            return None
        indexed = {item.branch_id: index for index, item in enumerate(items)}
        ordered = (
            eligible
            if investigation.portfolio_mode == "sequential"
            else tuple(
                sorted(
                    eligible,
                    key=lambda item: (
                        len(item.experiments),
                        abs(item.belief.confidence - 0.5),
                        indexed[item.branch_id],
                    ),
                )
            )
        )
        lanes = tuple({"id": item.branch_id} for item in ordered)
        currentness_root = (
            investigation.question.root
            if investigation.target_snapshot is None
            else investigation.target_snapshot.root
        )
        activated = self.portfolios.activate(
            mode=investigation.portfolio_mode,  # type: ignore[arg-type]
            lanes=lanes,
            status="planned",
            baseline_currentness_root=currentness_root,
            currentness_root=currentness_root,
        )
        active_ids = set(activated.active_lane_ids)
        return next(item for item in ordered if item.branch_id in active_ids)

    @staticmethod
    def experiment_has_evidence(branch: InvestigationBranch) -> bool:
        if not branch.experiments:
            return False
        reference = branch.experiments[-1].ref
        return any(item.source_refs == (reference,) for item in branch.evidence)

    def can_design(
        self,
        investigation: InvestigationRequest,
        branch: InvestigationBranch,
        *,
        total_experiments: int,
    ) -> bool:
        if branch.status != "active" or total_experiments >= investigation.max_experiments:
            return False
        if not branch.experiments:
            return True
        if not self.experiment_has_evidence(branch):
            return False
        return branch.redesign_count < investigation.max_redesigns_per_hypothesis

    def settle(
        self,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
        *,
        reason: str | None = None,
    ) -> tuple[InvestigationBranch, ...]:
        total_experiments = sum(len(item.experiments) for item in branches)
        result: list[InvestigationBranch] = []
        for branch in branches:
            if branch.status != "active":
                result.append(branch)
                continue
            retirement = reason
            if retirement is None:
                if total_experiments >= investigation.max_experiments:
                    retirement = "experiment-budget"
                elif branch.experiments and (
                    branch.redesign_count >= investigation.max_redesigns_per_hypothesis
                ):
                    retirement = "redesign-budget"
                else:
                    retirement = "no-action"
            result.append(self.retire(branch, retirement))
        return tuple(result)

    @staticmethod
    def build_experiment(
        *,
        investigation: InvestigationRequest,
        branch: InvestigationBranch,
        result: ReasoningResult,
    ) -> ExperimentSpec:
        if result.kind != "experiment-design":
            raise ValueError("investigation experiment design requires the exact reasoning kind")
        proposals = result.content["experiments"]
        if not isinstance(proposals, tuple) or len(proposals) != 1:
            raise ValueError("investigation design must propose exactly one experiment")
        proposal = proposals[0]
        if not isinstance(proposal, FrozenMap):
            raise TypeError("investigation experiment proposal is not canonical")
        objective = proposal["objective"]
        design = proposal["design"]
        criteria = proposal["criteria"]
        requested_measurements = proposal["requested_measurements"]
        required_objective = result.request.context.get("required_objective")
        if (
            type(objective) is not str
            or type(required_objective) is not str
            or objective != required_objective
        ):
            raise ValueError(
                "investigation objective must match its exact observation-only request"
            )
        if not isinstance(design, FrozenMap):
            raise TypeError("investigation experiment proposal has drifted")
        if not isinstance(criteria, FrozenMap):
            raise TypeError("investigation experiment proposal has drifted")
        if frozenset(design) != _DESIGN_KEYS:
            raise ValueError("investigation design must use the closed observation-only schema")
        if frozenset(criteria) != _CRITERIA_KEYS:
            raise ValueError("investigation criteria must use the closed evidence schema")
        method = design["method"]
        if type(method) is not str or method not in INVESTIGATION_OBSERVATION_METHODS:
            raise ValueError("investigation design method must be observation-only")
        measurements = _measurement_ids(design["measurements"])
        if _measurement_ids(requested_measurements) != measurements:
            raise ValueError("investigation measurements have drifted across proposal fields")
        minimum = criteria["minimum_evidence_items"]
        if type(minimum) is not int or minimum != 1:
            raise ValueError("investigation criteria require one or more canonical evidence items")
        relationships = criteria["accepted_relationships"]
        if (
            not isinstance(relationships, tuple)
            or any(type(item) is not str for item in relationships)
            or relationships != INVESTIGATION_EVIDENCE_RELATIONSHIPS
        ):
            raise ValueError("investigation criteria must retain canonical evidence relationships")
        iteration = len(branch.experiments) + 1
        return ExperimentSpec(
            experiment_id=f"{investigation.investigation_id}:{branch.branch_id}:{iteration}",
            kind="investigation",
            target_snapshot=investigation.target_snapshot,
            design={
                "method": method,
                "measurements": measurements,
                "branch_id": branch.branch_id,
                "iteration": iteration,
            },
            criteria=criteria,
            requested_measurements=measurements,
            repetitions=1,
            validity_requirements={"require_exact_hypothesis": True},
            lineage=(result.ref, *result.request.input_refs),
        )

    @staticmethod
    def build_result(
        *,
        investigation: InvestigationRequest,
        branches: Sequence[InvestigationBranch],
        failure_result: ActionResult | None = None,
    ) -> InvestigationResult:
        items = tuple(branches)
        stop_reason = _investigation_stop_reason(items, failure_result)
        findings = tuple(
            InvestigationFinding.from_branch(branch)
            for branch in items
            if branch.status == "supported"
        )
        evidence = tuple(
            item
            for _, item in sorted(
                {item.root: item for branch in items for item in branch.evidence}.items()
            )
        )
        disposition = (
            "partially-answered"
            if findings and any(branch.status == "retired" for branch in items)
            else "answered"
            if findings
            else "exhausted"
            if stop_reason == "experiment-budget"
            else "inconclusive"
        )
        run = investigation.canonical_run().ref
        failure_lineage: tuple[RecordRef, ...] = ()
        if failure_result is not None:
            failure = failure_result.failure
            if failure is None:
                raise ValueError("investigation failure result lost its RuntimeFailure")
            failure_lineage = (failure_result.ref, failure.ref)
        return InvestigationResult(
            investigation=investigation,
            run=run,
            disposition=disposition,
            stop_reason=stop_reason,
            branches=items,
            findings=findings,
            evidence=evidence,
            unresolved=investigation_unresolved(items),
            failure_result=failure_result,
            lineage=(
                investigation.ref,
                run,
                *(branch.ref for branch in items),
                *(finding.ref for finding in findings),
                *(item.ref for item in evidence),
                *failure_lineage,
            ),
        )

    def hypotheses_from_result(
        self,
        *,
        investigation: InvestigationRequest,
        result: ReasoningResult,
    ) -> tuple[Hypothesis, ...]:
        if result.kind != "hypothesis-generation":
            raise ValueError("investigation hypothesis generation requires the exact kind")
        proposals = result.content["hypotheses"]
        if not isinstance(proposals, tuple):
            raise TypeError("investigation hypothesis proposals are not canonical")
        if not 2 <= len(proposals) <= investigation.max_hypotheses:
            raise ValueError("investigation reasoning must return a bounded competing set")
        hypotheses: list[Hypothesis] = []
        for proposal in proposals:
            if not isinstance(proposal, Mapping):
                raise TypeError("investigation hypothesis proposal must be a mapping")
            hypotheses.append(
                self.hypothesis_from_proposal(
                    investigation=investigation,
                    proposal=proposal,
                    result=result,
                )
            )
        if len({item.statement for item in hypotheses}) != len(hypotheses):
            raise ValueError("investigation hypothesis statements must be unique")
        if len({item.ref for item in hypotheses}) != len(hypotheses):
            raise ValueError("investigation hypothesis proposals must be unique")
        return tuple(hypotheses)

    @staticmethod
    def hypothesis_from_proposal(
        *,
        investigation: InvestigationRequest,
        proposal: Mapping[str, Any],
        result: ReasoningResult,
    ) -> Hypothesis:
        return Hypothesis(
            statement=proposal["statement"],
            target=investigation.question.target,
            causal_model=proposal["causal_model"],
            predictions=proposal["predictions"],
            source_refs=(investigation.question.ref, result.ref),
            confidence=proposal["confidence"],
            status="proposed",
            lineage=(investigation.question.ref, result.request.ref, result.ref),
        )
