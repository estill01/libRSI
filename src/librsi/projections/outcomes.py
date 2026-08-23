"""Canonical workflow-result to public Outcome derivation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..improvement import ImprovementResult
from ..investigation import InvestigationResult
from ..records import EvidenceRef, Outcome
from ..rsi import RSIResult
from ..validation import ValidationResult
from .records import OutcomeProjection, ResultRecord

_WORKFLOW_TYPES = {
    ValidationResult: "validation",
    InvestigationResult: "investigation",
    ImprovementResult: "improvement",
    RSIResult: "rsi",
}


def workflow_for_result(result: ResultRecord) -> str:
    """Return the closed workflow kind for one exact public result class."""

    workflow = _WORKFLOW_TYPES.get(type(result))
    if workflow is None:
        raise TypeError("outcome projections require a supported exact workflow result")
    return workflow


def _validation_outcome(result: ValidationResult) -> Outcome:
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


def _investigation_outcome(result: InvestigationResult) -> Outcome:
    evidence_refs = tuple(EvidenceRef.from_evidence(item) for item in result.evidence)
    return Outcome(
        intent=result.investigation.question.ref,
        status=result.disposition,
        target_snapshot=result.investigation.target_snapshot,
        conclusions=tuple(item.statement for item in result.findings),
        evidence_refs=evidence_refs,
        unresolved=result.unresolved,
        lineage=(result.ref, *(item.ref for item in result.findings), *evidence_refs),
    )


def _improvement_outcome(result: ImprovementResult) -> Outcome:
    evidence = {
        item.root: EvidenceRef.from_evidence(item)
        for iteration in result.iterations
        for item in iteration.proposal.investigation.evidence
    }
    return Outcome(
        intent=result.request.ref,
        status=result.disposition,
        target_snapshot=result.request.baseline,
        conclusions=(result.stop_reason,),
        evidence_refs=tuple(evidence[key] for key in sorted(evidence)),
        unresolved=() if result.disposition == "improved" else ("no candidate accepted",),
        next_actions=(
            ("submit the explicit application handoff to an authorized Applier",)
            if result.handoff is not None
            else ("revise the goal, evidence, or search budget before another run",)
        ),
        lineage=(result.ref, *result.lineage),
    )


def _rsi_outcome(result: RSIResult) -> Outcome:
    conclusions = {
        "verified": ("self-change was applied and verified",),
        "rolled-back": ("self-change was rolled back",),
        "activation-disabled": ("self-change governance passed with activation disabled",),
    }.get(result.disposition, ())
    unresolved = {
        "governance-failed": ("self-change governance failed operationally",),
        "governance-rejected": ("self-change activation was not authorized",),
        "application-failed": ("self-change application failed operationally",),
        "rollback-failed": ("self-change rollback failed operationally",),
        "rolled-back": ("the activated self-change did not verify",),
    }.get(result.disposition, ())
    next_actions = {
        "activation-disabled": ("obtain explicit activation authority before application",),
        "governance-failed": ("resolve operational failures before rerunning governance",),
        "governance-rejected": ("revise the candidate or satisfy the failed gates",),
        "application-failed": ("resolve application failures before another attempt",),
        "rollback-failed": ("restore an authoritative target state before continuing",),
        "rolled-back": ("revise or replace the rejected self-change candidate",),
    }.get(result.disposition, ())
    return Outcome(
        intent=result.request.ref,
        status=result.disposition,
        target_snapshot=result.authoritative_snapshot,
        conclusions=conclusions,
        unresolved=unresolved,
        next_actions=next_actions,
        lineage=(result.ref, *result.lineage),
    )


def outcome_for_result(result: ResultRecord) -> Outcome:
    """Derive the one complete public Outcome for a canonical workflow result."""

    if type(result) is ValidationResult:
        return _validation_outcome(result)
    if type(result) is InvestigationResult:
        return _investigation_outcome(result)
    if type(result) is ImprovementResult:
        return _improvement_outcome(result)
    if type(result) is RSIResult:
        return _rsi_outcome(result)
    raise TypeError("outcome projections require a supported exact workflow result")


def project_result(
    result: ResultRecord,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> OutcomeProjection:
    """Project one canonical result without adding semantic authority."""

    return OutcomeProjection(
        workflow=workflow_for_result(result),
        result=result,
        outcome=outcome_for_result(result),
        metadata={} if metadata is None else metadata,
    )
