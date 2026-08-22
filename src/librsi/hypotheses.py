from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .identity import digest, normalize_ids
from .models import (
    EvidenceType,
    HypothesisProposal,
    HypothesisStatus,
    HypothesisUpdate,
    ReflectionIdentity,
)
from .records import Evidence, Hypothesis, RecordRef, TargetRef

_SUPPORTED_EVIDENCE_TYPES = frozenset(
    {"support", "counterexample", "boundary", "confounder", "null"}
)
_SUPPORTED_HYPOTHESIS_STATUSES = frozenset(
    {"proposed", "testing", "supported", "weakened", "rejected"}
)


@dataclass(frozen=True)
class HypothesisPolicy:
    """Evidence update policy for falsifiable causal hypotheses.

    The canonical Block 2 API is :meth:`create` plus :meth:`apply`. Those methods
    operate on complete immutable ``Hypothesis`` and ``Evidence`` records and require
    evidence to name the exact hypothesis version it updates.

    ``propose`` and ``apply_evidence`` remain as deprecated ``0.2.0`` compatibility
    wrappers. They intentionally preserve the legacy hash/update behavior and should
    not be used by new orchestration code because their scalar arguments cannot carry
    the same referential guarantees as canonical records.
    """

    support_scale: float = 0.2
    counterexample_scale: float = 0.2
    qualification_scale: float = 0.05
    supported_threshold: float = 0.75
    rejected_threshold: float = 0.2

    def create(
        self,
        *,
        target: TargetRef,
        statement: str,
        causal_model: Mapping[str, Any] | None = None,
        predictions: Sequence[Mapping[str, Any]],
        source_refs: Sequence[RecordRef] = (),
        confidence: float = 0.5,
        status: HypothesisStatus = "proposed",
        lineage: Sequence[RecordRef] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> Hypothesis:
        """Create a complete canonical hypothesis.

        ``target`` is the exact scope/target identity. ``source_refs`` binds the
        originating question, reflection, or other semantic records. At least one
        prediction is required so the canonical path cannot create a proposition that
        has no stated observable consequence.
        """

        if not isinstance(target, TargetRef):
            raise TypeError("canonical hypotheses require an exact TargetRef")
        prediction_items = tuple(predictions)
        if not prediction_items:
            raise ValueError("canonical hypotheses require at least one prediction")
        if status not in _SUPPORTED_HYPOTHESIS_STATUSES:
            raise ValueError(f"unsupported hypothesis status: {status}")
        return Hypothesis(
            target=target,
            statement=statement,
            causal_model=causal_model or {},
            predictions=prediction_items,
            source_refs=tuple(source_refs),
            confidence=confidence,
            status=status,
            lineage=tuple(lineage),
            metadata=metadata or {},
        )

    def apply(self, *, hypothesis: Hypothesis, evidence: Evidence) -> Hypothesis:
        """Apply evidence to the exact hypothesis version it names.

        The evidence must contain ``hypothesis.ref`` in ``subject_refs``. This makes
        applying evidence intended for a different or stale hypothesis version fail
        closed. The returned hypothesis is a new immutable version whose lineage names
        both the prior hypothesis version and the evidence record.
        """

        if not isinstance(hypothesis, Hypothesis):
            raise TypeError("hypothesis updates require a canonical Hypothesis")
        if not isinstance(hypothesis.target, TargetRef):
            raise ValueError("canonical hypothesis updates require an exact target")
        if not isinstance(evidence, Evidence):
            raise TypeError("hypothesis updates require canonical Evidence")
        if hypothesis.ref not in evidence.subject_refs:
            raise ValueError("evidence does not identify the exact hypothesis being updated")
        if (
            evidence.target_snapshot is not None
            and evidence.target_snapshot.target != hypothesis.target
        ):
            raise ValueError("evidence target does not match the hypothesis target")
        if evidence.weight is None:
            raise ValueError("canonical hypothesis evidence requires an explicit weight")

        update = self._transition(
            current_confidence=hypothesis.confidence,
            evidence_type=evidence.evidence_type,
            evidence_id=evidence.root,
            weight=evidence.weight,
        )
        return Hypothesis(
            target=hypothesis.target,
            statement=hypothesis.statement,
            causal_model=hypothesis.causal_model,
            predictions=hypothesis.predictions,
            source_refs=hypothesis.source_refs,
            confidence=update.confidence,
            status=update.status,
            lineage=(*hypothesis.lineage, hypothesis.ref, evidence.ref),
            metadata=hypothesis.metadata,
        )

    def propose(
        self,
        *,
        scope_id: str,
        statement: str,
        causal_model: Mapping[str, Any],
        prediction: Mapping[str, Any],
        reflection_id: str | None = None,
        confidence: float = 0.5,
    ) -> HypothesisProposal:
        """Deprecated ``0.2.0`` proposal wrapper preserving legacy identity."""

        warnings.warn(
            "HypothesisPolicy.propose() is a legacy compatibility wrapper; "
            "use create() with TargetRef and canonical source references instead",
            DeprecationWarning,
            stacklevel=2,
        )
        normalized_statement = statement.strip()
        if not normalized_statement:
            raise ValueError("hypothesis statement is required")
        self._validate_probability(confidence, "hypothesis confidence")
        hypothesis_root = digest(
            {
                "scope_id": scope_id,
                "statement": normalized_statement,
                "causal_model": dict(causal_model),
                "prediction": dict(prediction),
                "reflection_id": reflection_id,
            }
        )
        return HypothesisProposal(normalized_statement, confidence, hypothesis_root)

    def apply_evidence(
        self,
        *,
        current_confidence: float,
        evidence_type: EvidenceType,
        evidence_id: str,
        weight: float,
    ) -> HypothesisUpdate:
        """Deprecated scalar update wrapper preserving ``0.2.0`` behavior."""

        warnings.warn(
            "HypothesisPolicy.apply_evidence() is a legacy compatibility wrapper; "
            "use apply(hypothesis=..., evidence=...) for exact referential integrity",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._transition(
            current_confidence=current_confidence,
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            weight=weight,
        )

    def _transition(
        self,
        *,
        current_confidence: float,
        evidence_type: str,
        evidence_id: str,
        weight: float,
    ) -> HypothesisUpdate:
        self._validate_probability(current_confidence, "hypothesis confidence")
        self._validate_probability(weight, "evidence weight")
        if not evidence_id:
            raise ValueError("hypothesis evidence requires an exact evidence id")
        if evidence_type not in _SUPPORTED_EVIDENCE_TYPES:
            raise ValueError(f"unsupported hypothesis evidence type: {evidence_type}")

        if evidence_type == "support":
            delta = weight * self.support_scale
        elif evidence_type == "counterexample":
            delta = -weight * self.counterexample_scale
        else:
            delta = -weight * self.qualification_scale

        confidence = min(1.0, max(0.0, current_confidence + delta))
        status: HypothesisStatus
        if confidence >= self.supported_threshold:
            status = "supported"
        elif confidence <= self.rejected_threshold:
            status = "rejected"
        elif evidence_type == "counterexample":
            status = "weakened"
        else:
            status = "testing"
        return HypothesisUpdate(
            status,
            confidence,
            evidence_type,
            evidence_id,
            weight,
        )

    @staticmethod
    def _validate_probability(value: float, label: str) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{label} must be between zero and one")


class ReflectionPolicy:
    """Evidence-bound identity and confidence rules for reflective observations."""

    @staticmethod
    def identify(
        *,
        reflection_type: str,
        source_type: str,
        source_id: str,
        evidence_ids: Sequence[str],
        observations: Mapping[str, Any],
        confidence: float,
    ) -> ReflectionIdentity:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("reflection confidence must be between zero and one")
        evidence = normalize_ids(evidence_ids)
        if not evidence:
            raise ValueError("reflection requires exact evidence references")
        prompt_root = digest(
            {
                "reflection_type": reflection_type,
                "source_type": source_type,
                "source_id": source_id,
                "evidence_ids": list(evidence),
                "observations": dict(observations),
            }
        )
        return ReflectionIdentity(prompt_root, evidence)
