from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from librsi import (
    Action,
    ActionResult,
    ImprovementResult,
    ImprovementWorkflow,
    InvestigationRequest,
    InvestigationResult,
    InvestigationWorkflow,
    OutcomeProjection,
    ValidationRequest,
    ValidationResult,
    ValidationWorkflow,
    improvement_outcome,
    investigation_outcome,
    project_result,
    serialize_projection,
    validation_outcome,
)
from tests.block25_domain_audit import audit_generic_tree, audit_source
from tests.block25_fermenter_adapter import (
    FermenterAdapter,
    fermenter_hypotheses,
    fermenter_improvement_request,
    fermenter_question,
    fermenter_validation_claim,
)


@dataclass(frozen=True)
class CrossDomainProof:
    validation: ValidationResult
    investigation: InvestigationResult
    improvement: ImprovementResult
    projections: tuple[OutcomeProjection, ...]
    actions: tuple[Action, ...]


EXPECTED_PROOF_ROOTS = {
    "validation": (
        "321c6d8f8a6a4830ec2a596fa5590bf9f3e4e28b77a41a8d49e26b44124d094b",
        "87c0c16b1c7abc5a3f428c42ffde577c9af777d42bdf9eff0b5fc3ff8d01ea2e",
        "c9ad9bc76522ed30bf38c1fe465c0cc7044a3378287c0e1368077eba10bf5e67",
    ),
    "investigation": (
        "c27aced0b9da03ea80576360e70b9fc13f29096a7d80121b5e65cdec7e8c6d67",
        "158babfe98b35dadc2f21d4b015d0ae2d820efa2affe413add23976f3ea8b674",
        "49abc7b406e7c6dde81c068a4559a086f1b39715137b05c4b221953812d04767",
    ),
    "improvement": (
        "be4cb50aa60e6bc20298a43f528a7630d5f5814cb9152aae9a5e922f1dab20f9",
        "fef522467c64b3ca51fbeaada63d4d73f15fcab12c2649ea777ecbee2a827e3d",
        "6d7d73c84e6a244125a612c5fbde6a6fca6b1a087fa24701a9924788fb5c72de",
    ),
}
EXPECTED_ACTION_ROOTS = (
    "e4b05558cacb04aafcd957b0718e20cf75c97b0208c00f87837ab7afe1d8751a",
    "d3595bc1d94a83e02523ecabe2c8cda16ea7c9b18693646493f6b4c46600ccec",
    "17b6241588412c1edfd5658e69487d1466d5fc73eb08bca21f6bb8d75113823b",
    "97bbfe888ff0aef6e628237403b1c2efae9018fa7a39be7093cfd78daaa52596",
    "29a4c4e8e2377d540fccaac301796e939b547b97173119ab01c3f33ed9ba2b97",
    "99f38fe79c15c2499c241cdca92bc5956387ec8d4e33097257e419645e6c4c37",
    "f022f828145db37c84982b1bfc1d39a4a43fe8779228655b683ed581e2e47946",
    "2d1d649bb546e591b0c4c18c81755cb145352c125fd007fb94368b1c644ac05e",
    "67e0951510ed281e291f88a77991bb6059c0f976526cc7d1e7c560e8ed8b5fd3",
    "30114d0c0aebbe4c9c059150f75aa34d2a0eb430a5701f93a7f80ef2834ecd93",
)
EXPECTED_GENERIC_SOURCE_ROOT = "80a595c8984c67afd510ecf44d70a7f3e537a3264c65c5be109829e717a417d9"


def _run_fermenter_proof() -> CrossDomainProof:
    adapter = FermenterAdapter()
    context = adapter.context

    validation_request = ValidationRequest.for_claim(
        validation_id="fermenter-cross-domain-validation",
        claim=fermenter_validation_claim(context),
        target_snapshot=context.baseline_snapshot,
    )
    validation_workflow = ValidationWorkflow()
    validation_update = validation_workflow.run_managed(
        validation_workflow.start(validation_request).progress,
        adapter,
    )
    validation = validation_update.progress.result
    assert validation is not None
    assert validation_update.progress.state.outcome == validation_outcome(validation)

    question = fermenter_question(context, purpose="standalone investigation")
    investigation_request = InvestigationRequest.for_question(
        investigation_id="fermenter-cross-domain-investigation",
        question=question,
        target_snapshot=context.baseline_snapshot,
        initial_hypotheses=fermenter_hypotheses(question),
        max_hypotheses=2,
        max_experiments=2,
        max_redesigns_per_hypothesis=0,
    )
    investigation_workflow = InvestigationWorkflow()
    investigation_update = investigation_workflow.run_managed(
        investigation_workflow.start(investigation_request).progress,
        reasoner=adapter,
        experimenter=adapter,
    )
    investigation = investigation_update.progress.result
    assert investigation is not None
    assert investigation_update.progress.state.outcome == investigation_outcome(investigation)

    improvement_request = fermenter_improvement_request(context)
    improvement_workflow = ImprovementWorkflow()
    improvement_update = improvement_workflow.run_managed(
        improvement_workflow.start(
            improvement_request,
            current_snapshot=context.baseline_snapshot,
        ).progress,
        provider=adapter,
        current_snapshot=context.baseline_snapshot,
    )
    improvement = improvement_update.progress.result
    assert improvement is not None
    assert improvement_update.progress.state.outcome == improvement_outcome(improvement)

    results = (validation, investigation, improvement)
    return CrossDomainProof(
        validation=validation,
        investigation=investigation,
        improvement=improvement,
        projections=tuple(project_result(result) for result in results),
        actions=tuple(adapter.actions),
    )


def test_one_physical_adapter_runs_every_canonical_workflow_and_outcome_family() -> None:
    proof = _run_fermenter_proof()

    assert proof.validation.disposition == "supported"
    assert tuple(branch.status for branch in proof.investigation.branches) == (
        "rejected",
        "supported",
    )
    assert proof.improvement.disposition == "improved"
    assert tuple(projection.workflow for projection in proof.projections) == (
        "validation",
        "investigation",
        "improvement",
    )
    assert all(
        projection.outcome.target_snapshot is not None
        and projection.outcome.target_snapshot.target.kind == "physical-process"
        for projection in proof.projections
    )
    assert {action.kind for action in proof.actions} == {
        "improvement-cycle",
        "investigation-experiment",
        "investigation-reason",
        "validation-evidence",
    }

    iteration = proof.improvement.iterations[0]
    batch = iteration.proposal.batches[0]
    assert batch.contract == proof.improvement.request.contract
    assert len(batch.results) == 6
    assert batch.evaluation.subject_refs == (batch.experiment.ref,)
    assert iteration.selection.disposition == "selected"
    assert iteration.selection.selected == (batch.candidate.ref,)
    assert proof.improvement.handoff is not None
    assert proof.improvement.handoff.apply is False


def test_fermenter_runs_are_exactly_deterministic_and_project_without_semantic_drift() -> None:
    first = _run_fermenter_proof()
    second = _run_fermenter_proof()

    assert first == second
    assert tuple(serialize_projection(item) for item in first.projections) == tuple(
        serialize_projection(item) for item in second.projections
    )
    assert tuple(item.outcome for item in first.projections) == (
        validation_outcome(first.validation),
        investigation_outcome(first.investigation),
        improvement_outcome(first.improvement),
    )
    assert {
        item.workflow: (item.result.root, item.outcome.root, item.projection_root)
        for item in first.projections
    } == EXPECTED_PROOF_ROOTS
    assert tuple(item.root for item in first.actions) == EXPECTED_ACTION_ROOTS
    assert len({item.projection_root for item in first.projections}) == 3


def test_fermenter_actions_do_not_gain_software_or_repository_ontology() -> None:
    proof = _run_fermenter_proof()
    forbidden = re.compile(
        r"(^|[^a-z0-9])(git|github|repository|software|worktree|commit[_-]?sha)([^a-z0-9]|$)"
    )
    for action in proof.actions:
        payload = json.dumps(action.to_dict(), sort_keys=True).lower()
        assert forbidden.search(payload) is None


def test_generic_semantic_tree_has_no_software_types_or_adapter_dependencies() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    audit = audit_generic_tree(repository_root / "src")

    assert len(audit.paths) == 82
    assert audit.source_root == EXPECTED_GENERIC_SOURCE_ROOT
    assert audit.leaks == ()


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "class GenericResult:\n    repository_path: str\n",
            "software-specific generic identifier: repository_path",
        ),
        (
            "def route(target):\n    if target.kind == 'software-repository':\n        return 1\n",
            "software-only target branch: software-repository",
        ),
        (
            "from librsi.providers import CodexAppServerReasoner\n",
            "forbidden adapter import: librsi.providers",
        ),
    ],
)
def test_domain_audit_rejects_repository_fields_software_branches_and_adapter_leaks(
    source: str,
    message: str,
) -> None:
    leaks = audit_source(source, module_name="librsi.validation.injected")
    assert any(item.detail == message for item in leaks)


def test_adapter_cannot_replace_canonical_outcome_authority() -> None:
    adapter = FermenterAdapter()
    context = adapter.context
    request = ValidationRequest.for_claim(
        validation_id="fermenter-authority-negative",
        claim=fermenter_validation_claim(context),
        target_snapshot=context.baseline_snapshot,
    )
    workflow = ValidationWorkflow()
    started = workflow.start(request)
    action = started.progress.state.pending_actions[0]
    leaked = ActionResult(
        action=action,
        disposition="succeeded",
        payload={"outcome": {"status": "supported", "authority": "adapter"}},
    )

    with pytest.raises(ValueError, match="only its evidence batch"):
        workflow.submit(started.progress, leaked)
    assert started.progress.state.results == ()
    assert started.progress.state.outcome is None
