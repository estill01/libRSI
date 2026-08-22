"""Deterministic evidence sufficiency and result projection for validation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..epistemics import EpistemicPolicy, LinearEvidenceAggregator
from ..records import BeliefState, Evidence, EvidenceRef
from .records import ValidationRequest, classify_validation


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """Compose canonical epistemics without inventing another belief authority."""

    epistemics: EpistemicPolicy = field(default_factory=EpistemicPolicy)

    def __post_init__(self) -> None:
        self._require_canonical()

    def _require_canonical(self) -> None:
        if type(self) is not ValidationPolicy or type(self.epistemics) is not EpistemicPolicy:
            raise ValueError(
                "validation policy changes require a versioned semantic policy contract"
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
                "validation policy changes require a versioned semantic policy contract"
            )

    @classmethod
    def owned_canonical(cls, value: ValidationPolicy) -> ValidationPolicy:
        """Validate an external policy and return a fresh built-in policy instance."""

        if type(value) is not cls:
            raise TypeError("validation workflows require a ValidationPolicy")
        value._require_canonical()
        return cls()

    def belief(
        self,
        validation: ValidationRequest,
        evidence: Sequence[Evidence],
    ) -> BeliefState:
        if not isinstance(validation, ValidationRequest):
            raise TypeError("validation belief requires a ValidationRequest")
        if isinstance(evidence, (str, bytes, bytearray)) or not isinstance(evidence, Sequence):
            raise TypeError("validation evidence must be a sequence")
        raw = tuple(evidence)
        if any(not isinstance(item, Evidence) for item in raw):
            raise TypeError("validation evidence must contain Evidence values")
        items = tuple(sorted(raw, key=lambda item: item.root))
        if not items:
            return self.epistemics.initial(
                validation.claim, target_snapshot=validation.target_snapshot
            )
        return self.epistemics.aggregate(
            subject=validation.claim,
            evidence=items,
            current_snapshot=validation.target_snapshot,
        )

    def disposition(self, belief: BeliefState, evidence: Sequence[Evidence]) -> str:
        return classify_validation(belief, evidence)

    def gaps(self, belief: BeliefState, evidence: Sequence[Evidence]) -> tuple[str, ...]:
        disposition = self.disposition(belief, evidence)
        if disposition == "bounded":
            return ("resolve the observed boundary, confounder, or conflicting evidence",)
        if disposition != "inconclusive":
            return ()
        relationships = {item.evidence_type for item in evidence if item.evidence_type != "null"}
        if not relationships:
            return ("obtain current substantive evidence for the exact claim",)
        return ("obtain enough current evidence to meet a decisive threshold",)

    @staticmethod
    def evidence_refs(evidence: Sequence[Evidence]) -> tuple[EvidenceRef, ...]:
        return tuple(
            EvidenceRef.from_evidence(item) for item in sorted(evidence, key=lambda item: item.root)
        )
