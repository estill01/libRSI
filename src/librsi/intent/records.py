"""Typed improvement intent and measurable evaluation-contract records."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, TypeVar

from ..identity import FrozenMap
from ..records import (
    Constraint,
    Goal,
    Metric,
    RecordRef,
    SemanticRecord,
    TargetSnapshot,
    register_record_type,
)
from ..runtime import Action, Run, RunBudget

OBJECTIVE_SEMANTICS = frozenset({"minimize", "maximize", "target"})
GUARDRAIL_SEMANTICS = frozenset({"no-regression", "must-satisfy"})
COMPARISON_OPERATORS = frozenset({"<", "<=", "==", ">=", ">"})
STOPPING_RULE_KINDS = frozenset(
    {"criteria-sufficient", "missing-fact", "budget", "diminishing-return"}
)
OPERATIONALIZATION_DISPOSITIONS = frozenset(
    {"operationalized", "pending-information", "unmeasurable"}
)
OPERATIONALIZE_GOAL_ACTION_KIND = "operationalize-goal"
OPERATIONALIZATION_CAPABILITY_FAMILY = "reasoner"


def _require_text(value: str, label: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _finite(value: float | int, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _texts(value: Sequence[str], label: str, *, required: bool = False) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of text values")
    items = tuple(_require_text(item, label) for item in value)
    if required and not items:
        raise ValueError(f"{label} cannot be empty")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


RecordT = TypeVar("RecordT", bound=SemanticRecord)


def _records(
    value: Sequence[RecordT], expected: type[RecordT], label: str
) -> tuple[RecordT, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)
    if any(type(item) is not expected for item in items):
        raise TypeError(f"{label} must contain {expected.__name__} values")
    if len({item.ref for item in items}) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


def _refs(value: Sequence[RecordRef], label: str) -> tuple[RecordRef, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence")
    items = tuple(value)
    if any(not isinstance(item, RecordRef) for item in items):
        raise TypeError(f"{label} must contain RecordRef values")
    if len(set(items)) != len(items):
        raise ValueError(f"{label} must be unique")
    return items


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Baseline(SemanticRecord):
    """Exact target revision and finite metric values used by a contract."""

    RECORD_TYPE: ClassVar[str] = "evaluation_baseline"

    snapshot: TargetSnapshot
    measurements: Mapping[str, float]

    def __post_init__(self) -> None:
        if type(self.snapshot) is not TargetSnapshot:
            raise TypeError("evaluation baselines require a TargetSnapshot")
        if not isinstance(self.measurements, Mapping):
            raise TypeError("baseline measurements must be a mapping")
        normalized: dict[str, float] = {}
        for name, value in self.measurements.items():
            metric_id = _require_text(name, "baseline metric id")
            if metric_id in normalized:
                raise ValueError("baseline metric ids must be unique")
            normalized[metric_id] = _finite(value, f"baseline measurement {metric_id}")
        object.__setattr__(self, "measurements", FrozenMap(normalized))
        if _refs(self.lineage, "baseline lineage") != (self.snapshot.ref,):
            raise ValueError("baseline lineage must cite its exact target snapshot")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        snapshot: TargetSnapshot,
        measurements: Mapping[str, float],
        metadata: Mapping[str, object] | None = None,
    ) -> Baseline:
        return cls(
            snapshot=snapshot,
            measurements=measurements,
            lineage=(snapshot.ref,),
            metadata=FrozenMap(metadata),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Objective(SemanticRecord):
    """One optimization or target criterion derived from an exact Goal."""

    RECORD_TYPE: ClassVar[str] = "objective"

    objective_id: str
    metric: Metric
    semantics: str
    source_goal: RecordRef
    target_value: float | None = None
    tolerance: float = 0.0
    minimum_effect: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _require_text(self.objective_id, "objective id"))
        if type(self.metric) is not Metric:
            raise TypeError("objectives require a Metric")
        if self.metric.role != "objective":
            raise ValueError("objective Metrics must have the objective role")
        semantics = _require_text(self.semantics, "objective semantics")
        if semantics not in OBJECTIVE_SEMANTICS:
            raise ValueError(f"unsupported objective semantics: {semantics}")
        object.__setattr__(self, "semantics", semantics)
        if not isinstance(self.source_goal, RecordRef) or self.source_goal.record_type != "goal":
            raise TypeError("objective source_goal must reference a Goal")
        tolerance = _finite(self.tolerance, "objective tolerance")
        effect = _finite(self.minimum_effect, "objective minimum effect")
        if tolerance < 0.0 or effect < 0.0:
            raise ValueError("objective tolerance and minimum effect must be nonnegative")
        object.__setattr__(self, "tolerance", tolerance)
        object.__setattr__(self, "minimum_effect", effect)
        direction = {"minimize": "decrease", "maximize": "increase", "target": "target"}[
            semantics
        ]
        if self.metric.direction != direction:
            raise ValueError("objective semantics conflict with its Metric direction")
        if semantics == "target":
            if self.target_value is None:
                raise ValueError("target objectives require a finite target value")
            object.__setattr__(
                self, "target_value", _finite(self.target_value, "objective target value")
            )
            if effect != 0.0:
                raise ValueError("target objectives do not accept a minimum effect")
        else:
            if self.target_value is not None or tolerance != 0.0:
                raise ValueError("minimize/maximize objectives do not accept target fields")
        if _refs(self.lineage, "objective lineage") != (self.source_goal, self.metric.ref):
            raise ValueError("objective lineage must cite its exact Goal and Metric")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        objective_id: str,
        metric: Metric,
        semantics: str,
        goal: Goal,
        target_value: float | None = None,
        tolerance: float = 0.0,
        minimum_effect: float = 0.0,
    ) -> Objective:
        if type(goal) is not Goal:
            raise TypeError("objective creation requires a Goal")
        return cls(
            objective_id=objective_id,
            metric=metric,
            semantics=semantics,
            source_goal=goal.ref,
            target_value=target_value,
            tolerance=tolerance,
            minimum_effect=minimum_effect,
            lineage=(goal.ref, metric.ref),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class Guardrail(SemanticRecord):
    """A gating no-regression or threshold rule derived from a Constraint."""

    RECORD_TYPE: ClassVar[str] = "guardrail"

    guardrail_id: str
    metric: Metric
    semantics: str
    source_constraint: RecordRef
    operator: str | None = None
    threshold: float | None = None
    allowed_regression: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "guardrail_id", _require_text(self.guardrail_id, "guardrail id"))
        if type(self.metric) is not Metric:
            raise TypeError("guardrails require a Metric")
        if self.metric.role != "guardrail":
            raise ValueError("guardrail Metrics must have the guardrail role")
        semantics = _require_text(self.semantics, "guardrail semantics")
        if semantics not in GUARDRAIL_SEMANTICS:
            raise ValueError(f"unsupported guardrail semantics: {semantics}")
        object.__setattr__(self, "semantics", semantics)
        if (
            not isinstance(self.source_constraint, RecordRef)
            or self.source_constraint.record_type != "constraint"
        ):
            raise TypeError("guardrail source_constraint must reference a Constraint")
        regression = _finite(self.allowed_regression, "allowed regression")
        if regression < 0.0:
            raise ValueError("allowed regression must be nonnegative")
        object.__setattr__(self, "allowed_regression", regression)
        if semantics == "must-satisfy":
            if self.operator not in COMPARISON_OPERATORS or self.threshold is None:
                raise ValueError("must-satisfy guardrails require an operator and threshold")
            object.__setattr__(self, "threshold", _finite(self.threshold, "guardrail threshold"))
            if regression != 0.0:
                raise ValueError("must-satisfy guardrails do not accept allowed regression")
        else:
            if self.metric.direction == "target":
                raise ValueError("no-regression guardrails require increase/decrease direction")
            if self.operator is not None or self.threshold is not None:
                raise ValueError("no-regression guardrails derive their bound from the baseline")
        if _refs(self.lineage, "guardrail lineage") != (
            self.source_constraint,
            self.metric.ref,
        ):
            raise ValueError("guardrail lineage must cite its exact Constraint and Metric")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        guardrail_id: str,
        metric: Metric,
        semantics: str,
        constraint: Constraint,
        operator: str | None = None,
        threshold: float | None = None,
        allowed_regression: float = 0.0,
    ) -> Guardrail:
        if type(constraint) is not Constraint:
            raise TypeError("guardrail creation requires a Constraint")
        return cls(
            guardrail_id=guardrail_id,
            metric=metric,
            semantics=semantics,
            source_constraint=constraint.ref,
            operator=operator,
            threshold=threshold,
            allowed_regression=allowed_regression,
            lineage=(constraint.ref, metric.ref),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class StoppingRule(SemanticRecord):
    """Explicit condition that ends operationalization or later improvement work."""

    RECORD_TYPE: ClassVar[str] = "stopping_rule"

    rule_id: str
    kind: str
    condition: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_text(self.rule_id, "stopping rule id"))
        kind = _require_text(self.kind, "stopping rule kind")
        if kind not in STOPPING_RULE_KINDS:
            raise ValueError(f"unsupported stopping rule kind: {kind}")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "condition", _require_text(self.condition, "stopping condition"))
        super().__post_init__()


def _guardrail_bound(
    guardrail: Guardrail,
    baseline: Baseline,
) -> tuple[float | None, bool, float | None, bool]:
    if guardrail.semantics == "no-regression":
        value = baseline.measurements[guardrail.metric.metric_id]
        if guardrail.metric.direction == "increase":
            return value - guardrail.allowed_regression, True, None, True
        return None, True, value + guardrail.allowed_regression, True
    threshold = guardrail.threshold
    if threshold is None:  # pragma: no cover - record invariant
        raise RuntimeError("must-satisfy guardrail lost its threshold")
    if guardrail.operator == ">":
        return threshold, False, None, True
    if guardrail.operator == ">=":
        return threshold, True, None, True
    if guardrail.operator == "<":
        return None, True, threshold, False
    if guardrail.operator == "<=":
        return None, True, threshold, True
    return threshold, True, threshold, True


def _require_contract_consistency(
    *,
    baseline: Baseline,
    objectives: tuple[Objective, ...],
    guardrails: tuple[Guardrail, ...],
) -> None:
    metric_defs: dict[str, tuple[str, str | None]] = {}
    for objective in objectives:
        signature = (objective.metric.direction, objective.metric.unit)
        previous = metric_defs.setdefault(objective.metric.metric_id, signature)
        if previous != signature:
            raise ValueError("one metric id cannot have conflicting definitions")
    for guardrail in guardrails:
        signature = (guardrail.metric.direction, guardrail.metric.unit)
        previous = metric_defs.setdefault(guardrail.metric.metric_id, signature)
        if previous != signature:
            raise ValueError("one metric id cannot have conflicting definitions")

    objective_by_metric: dict[str, Objective] = {}
    for objective in objectives:
        previous_objective = objective_by_metric.setdefault(
            objective.metric.metric_id, objective
        )
        if previous_objective != objective:
            raise ValueError("a contract cannot contain contradictory objectives")

    required_baselines = {
        item.metric.metric_id
        for item in objectives
        if item.semantics in {"minimize", "maximize"}
    } | {
        item.metric.metric_id
        for item in guardrails
        if item.semantics == "no-regression"
    }
    missing = required_baselines - set(baseline.measurements)
    if missing:
        raise ValueError(f"evaluation contract is missing required baselines: {sorted(missing)}")

    guardrails_by_metric: dict[str, list[Guardrail]] = {}
    for guardrail in guardrails:
        guardrails_by_metric.setdefault(guardrail.metric.metric_id, []).append(guardrail)
    for metric_id, metric_guardrails in guardrails_by_metric.items():
        lower: float | None = None
        lower_inclusive = True
        upper: float | None = None
        upper_inclusive = True
        for guardrail in metric_guardrails:
            candidate_lower, candidate_lower_inclusive, candidate_upper, candidate_upper_inclusive = (
                _guardrail_bound(guardrail, baseline)
            )
            if candidate_lower is not None and (lower is None or candidate_lower > lower):
                lower, lower_inclusive = candidate_lower, candidate_lower_inclusive
            elif candidate_lower is not None and candidate_lower == lower:
                lower_inclusive = lower_inclusive and candidate_lower_inclusive
            if candidate_upper is not None and (upper is None or candidate_upper < upper):
                upper, upper_inclusive = candidate_upper, candidate_upper_inclusive
            elif candidate_upper is not None and candidate_upper == upper:
                upper_inclusive = upper_inclusive and candidate_upper_inclusive
        if lower is not None and upper is not None and (
            lower > upper or (lower == upper and not (lower_inclusive and upper_inclusive))
        ):
            raise ValueError(f"contradictory guardrails for metric {metric_id!r}")

        target_objective = objective_by_metric.get(metric_id)
        if target_objective is not None and target_objective.semantics == "target":
            target = target_objective.target_value
            if target is None:  # pragma: no cover - record invariant
                raise RuntimeError("target objective lost its value")
            target_low = target - target_objective.tolerance
            target_high = target + target_objective.tolerance
            if lower is not None and (
                target_high < lower or (target_high == lower and not lower_inclusive)
            ):
                raise ValueError("target objective contradicts its guardrail")
            if upper is not None and (
                target_low > upper or (target_low == upper and not upper_inclusive)
            ):
                raise ValueError("target objective contradicts its guardrail")

@register_record_type
@dataclass(frozen=True, kw_only=True)
class EvaluationContract(SemanticRecord):
    """Exact measurable criteria; it is intent, not a Claim or Evidence."""

    RECORD_TYPE: ClassVar[str] = "evaluation_contract"

    contract_id: str
    goal: Goal
    baseline: Baseline
    objectives: tuple[Objective, ...]
    constraints: tuple[Constraint, ...]
    guardrails: tuple[Guardrail, ...]
    stopping_rules: tuple[StoppingRule, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "contract_id", _require_text(self.contract_id, "contract id"))
        if type(self.goal) is not Goal:
            raise TypeError("evaluation contracts require a Goal")
        if type(self.baseline) is not Baseline:
            raise TypeError("evaluation contracts require a Baseline")
        if self.goal.target is not None and self.goal.target != self.baseline.snapshot.target:
            raise ValueError("evaluation baseline belongs to another goal target")
        objectives = tuple(_records(self.objectives, Objective, "contract objectives"))
        constraints = tuple(_records(self.constraints, Constraint, "contract constraints"))
        guardrails = tuple(_records(self.guardrails, Guardrail, "contract guardrails"))
        stops = tuple(_records(self.stopping_rules, StoppingRule, "contract stopping rules"))
        if not objectives:
            raise ValueError("evaluation contracts require at least one objective")
        if not stops:
            raise ValueError("evaluation contracts require an explicit stopping rule")
        if len({item.objective_id for item in objectives}) != len(objectives):
            raise ValueError("objective ids must be unique")
        if len({item.guardrail_id for item in guardrails}) != len(guardrails):
            raise ValueError("guardrail ids must be unique")
        if len({item.rule_id for item in stops}) != len(stops):
            raise ValueError("stopping rule ids must be unique")
        if any(item.source_goal != self.goal.ref for item in objectives):
            raise ValueError("every objective must derive from the exact contract Goal")
        constraint_refs = {item.ref for item in constraints}
        if {item.source_constraint for item in guardrails} != constraint_refs:
            raise ValueError("every contract Constraint must have an exact typed Guardrail")
        if any(
            item.target is not None and item.target != self.baseline.snapshot.target
            for item in constraints
        ):
            raise ValueError("contract constraints belong to another target")
        _require_contract_consistency(
            baseline=self.baseline,
            objectives=objectives,
            guardrails=guardrails,
        )
        object.__setattr__(self, "objectives", objectives)
        object.__setattr__(self, "constraints", constraints)
        object.__setattr__(self, "guardrails", guardrails)
        object.__setattr__(self, "stopping_rules", stops)
        expected_lineage = (
            self.goal.ref,
            self.baseline.ref,
            *(item.ref for item in objectives),
            *(item.ref for item in constraints),
            *(item.ref for item in guardrails),
            *(item.ref for item in stops),
        )
        if _refs(self.lineage, "evaluation contract lineage") != expected_lineage:
            raise ValueError("evaluation contract lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        contract_id: str,
        goal: Goal,
        baseline: Baseline,
        objectives: Sequence[Objective],
        constraints: Sequence[Constraint] = (),
        guardrails: Sequence[Guardrail] = (),
        stopping_rules: Sequence[StoppingRule],
        metadata: Mapping[str, object] | None = None,
    ) -> EvaluationContract:
        objective_items = tuple(objectives)
        constraint_items = tuple(constraints)
        guardrail_items = tuple(guardrails)
        stop_items = tuple(stopping_rules)
        return cls(
            contract_id=contract_id,
            goal=goal,
            baseline=baseline,
            objectives=objective_items,
            constraints=constraint_items,
            guardrails=guardrail_items,
            stopping_rules=stop_items,
            lineage=(
                goal.ref,
                baseline.ref,
                *(item.ref for item in objective_items),
                *(item.ref for item in constraint_items),
                *(item.ref for item in guardrail_items),
                *(item.ref for item in stop_items),
            ),
            metadata=FrozenMap(metadata),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class OperationalizationRequest(SemanticRecord):
    """Request to translate one Goal at one exact current target revision."""

    RECORD_TYPE: ClassVar[str] = "operationalization_request"

    request_id: str
    goal: Goal
    current_snapshot: TargetSnapshot
    known_facts: Mapping[str, str] = field(default_factory=FrozenMap)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _require_text(self.request_id, "request id"))
        if type(self.goal) is not Goal:
            raise TypeError("operationalization requests require a Goal")
        if type(self.current_snapshot) is not TargetSnapshot:
            raise TypeError("operationalization requests require a current TargetSnapshot")
        if self.goal.target is not None and self.goal.target != self.current_snapshot.target:
            raise ValueError("operationalization target does not match the Goal")
        if not isinstance(self.known_facts, Mapping):
            raise TypeError("operationalization known facts must be a mapping")
        facts = {
            _require_text(key, "known fact name"): _require_text(value, "known fact value")
            for key, value in self.known_facts.items()
        }
        object.__setattr__(self, "known_facts", FrozenMap(facts))
        if _refs(self.lineage, "operationalization request lineage") != (
            self.goal.ref,
            self.current_snapshot.ref,
        ):
            raise ValueError("operationalization request lineage is incomplete")
        super().__post_init__()

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        goal: Goal,
        current_snapshot: TargetSnapshot,
        known_facts: Mapping[str, str] | None = None,
    ) -> OperationalizationRequest:
        return cls(
            request_id=request_id,
            goal=goal,
            current_snapshot=current_snapshot,
            known_facts={} if known_facts is None else known_facts,
            lineage=(goal.ref, current_snapshot.ref),
        )

    def canonical_run(self) -> Run:
        return Run(
            run_id=f"{self.request_id}:operationalization",
            intent=self.goal.ref,
            target_snapshot=self.current_snapshot,
            budget=RunBudget(max_actions=1, max_failures=1, max_retries=0),
            lineage=(self.ref,),
        )

    def canonical_action(self) -> Action:
        return Action(
            run=self.canonical_run().ref,
            action_id=f"{self.request_id}:propose-contract",
            kind=OPERATIONALIZE_GOAL_ACTION_KIND,
            input_refs=(self.ref, self.goal.ref, self.current_snapshot.ref),
            payload={"request": self.to_dict()},
            lineage=(self.ref,),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class OperationalizationProposal(SemanticRecord):
    """Untrusted structured proposal; policy must validate it before use."""

    RECORD_TYPE: ClassVar[str] = "operationalization_proposal"

    request: OperationalizationRequest
    disposition: str
    contract: EvaluationContract | None = None
    missing_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.request) is not OperationalizationRequest:
            raise TypeError("operationalization proposals require their exact request")
        disposition = _require_text(self.disposition, "operationalization disposition")
        if disposition not in OPERATIONALIZATION_DISPOSITIONS:
            raise ValueError(f"unsupported operationalization disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        missing = _texts(self.missing_facts, "missing fact", required=False)
        object.__setattr__(self, "missing_facts", missing)
        if disposition == "operationalized":
            if type(self.contract) is not EvaluationContract or missing:
                raise ValueError("operationalized proposals require only a contract")
        elif self.contract is not None or not missing:
            raise ValueError("non-operationalized proposals require named missing facts only")
        expected_lineage = (
            self.request.ref,
            self.request.goal.ref,
            self.request.current_snapshot.ref,
            *((self.contract.ref,) if self.contract is not None else ()),
        )
        if _refs(self.lineage, "operationalization proposal lineage") != expected_lineage:
            raise ValueError("operationalization proposal lineage is incomplete")
        super().__post_init__()

    @classmethod
    def propose_contract(
        cls,
        *,
        request: OperationalizationRequest,
        contract: EvaluationContract,
    ) -> OperationalizationProposal:
        return cls(
            request=request,
            disposition="operationalized",
            contract=contract,
            lineage=(
                request.ref,
                request.goal.ref,
                request.current_snapshot.ref,
                contract.ref,
            ),
        )

    @classmethod
    def pending(
        cls,
        *,
        request: OperationalizationRequest,
        missing_facts: Sequence[str],
        unmeasurable: bool = False,
    ) -> OperationalizationProposal:
        return cls(
            request=request,
            disposition="unmeasurable" if unmeasurable else "pending-information",
            missing_facts=tuple(missing_facts),
            lineage=(request.ref, request.goal.ref, request.current_snapshot.ref),
        )


@register_record_type
@dataclass(frozen=True, kw_only=True)
class OperationalizationResult(SemanticRecord):
    """Policy-owned outcome of typed or proposal-backed operationalization."""

    RECORD_TYPE: ClassVar[str] = "operationalization_result"

    request: OperationalizationRequest
    disposition: str
    contract: EvaluationContract | None = None
    missing_facts: tuple[str, ...] = ()
    proposal: OperationalizationProposal | None = None

    def __post_init__(self) -> None:
        if type(self.request) is not OperationalizationRequest:
            raise TypeError("operationalization results require their exact request")
        disposition = _require_text(self.disposition, "operationalization disposition")
        if disposition not in OPERATIONALIZATION_DISPOSITIONS:
            raise ValueError(f"unsupported operationalization disposition: {disposition}")
        object.__setattr__(self, "disposition", disposition)
        missing = _texts(self.missing_facts, "missing fact", required=False)
        object.__setattr__(self, "missing_facts", missing)
        if disposition == "operationalized":
            if type(self.contract) is not EvaluationContract or missing:
                raise ValueError("operationalized results require only a contract")
        elif self.contract is not None or not missing:
            raise ValueError("pending/unmeasurable results require named missing facts")
        if self.proposal is not None:
            if type(self.proposal) is not OperationalizationProposal:
                raise TypeError("result proposal must be OperationalizationProposal")
            if self.proposal.request != self.request:
                raise ValueError("operationalization result proposal answers another request")
            if (
                self.proposal.disposition != disposition
                or self.proposal.contract != self.contract
                or self.proposal.missing_facts != missing
            ):
                raise ValueError("operationalization result cannot rewrite its proposal")
        if self.contract is not None:
            if self.contract.goal != self.request.goal:
                raise ValueError("operationalization result contract belongs to another Goal")
            if self.contract.baseline.snapshot != self.request.current_snapshot:
                raise ValueError("operationalization result contract baseline is stale")
        expected_lineage = (
            self.request.ref,
            *((self.proposal.ref,) if self.proposal is not None else ()),
            *((self.contract.ref,) if self.contract is not None else ()),
        )
        if _refs(self.lineage, "operationalization result lineage") != expected_lineage:
            raise ValueError("operationalization result lineage is incomplete")
        super().__post_init__()


@register_record_type
@dataclass(frozen=True, kw_only=True)
class OperationalizationHandoff(SemanticRecord):
    """Complete proposal-only frontier for an external or managed Reasoner."""

    RECORD_TYPE: ClassVar[str] = "operationalization_handoff"

    request: OperationalizationRequest
    action: Action
    capability_family: str = OPERATIONALIZATION_CAPABILITY_FAMILY
    expected_output_record_type: str = "operationalization_proposal"

    def __post_init__(self) -> None:
        if type(self.request) is not OperationalizationRequest:
            raise TypeError("operationalization handoffs require an exact request")
        if not isinstance(self.action, Action) or self.action != self.request.canonical_action():
            raise ValueError("operationalization handoff action is not canonical")
        if self.capability_family != OPERATIONALIZATION_CAPABILITY_FAMILY:
            raise ValueError("operationalization handoffs require Reasoner capability")
        if self.expected_output_record_type != "operationalization_proposal":
            raise ValueError("operationalization handoff output schema cannot be replaced")
        if _refs(self.lineage, "operationalization handoff lineage") != (
            self.request.ref,
            self.action.ref,
        ):
            raise ValueError("operationalization handoff lineage is incomplete")
        super().__post_init__()
