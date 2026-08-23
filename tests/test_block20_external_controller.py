from __future__ import annotations

from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator, ValidationError

from librsi import (
    APPLY_CANDIDATE_ACTION_KIND,
    FORWARD_SHADOW_ACTION_KIND,
    HISTORICAL_EVALUATION_ACTION_KIND,
    INDEPENDENT_REVIEW_ACTION_KIND,
    INVESTIGATION_EXPERIMENT_ACTION_KIND,
    INVESTIGATION_REASONING_ACTION_KIND,
    ROLLBACK_APPLICATION_ACTION_KIND,
    VERIFY_APPLICATION_ACTION_KIND,
    AgentRunBinding,
    ApplicationGovernanceRequirement,
    Evidence,
    RSIProgress,
    RSIWorkflow,
    SQLiteAgentStore,
    TargetRef,
    TargetSnapshot,
    make_cycle_result,
    record_from_dict,
)
from librsi.runtime import Action, ActionResult
from tests.block14_support import comparison_context
from tests.block15_support import (
    CycleExperimenter,
    CycleReasoner,
    cycle_proposal,
    improvement_request,
)
from tests.block16_support import DeterministicApplicationTarget
from tests.block17_support import DeterministicGovernanceProvider, self_change_request
from tests.block20_support import (
    controller,
    target_admission,
    validation_request,
    validation_result,
    workflow_cases,
)


def _action(document: dict) -> Action:
    record = record_from_dict(document)
    assert type(record) is Action
    return record


def _validate_expected_result(pending: dict, result: ActionResult) -> None:
    validator = Draft202012Validator(pending["data"]["expected_result_schema"])
    validator.validate(result.to_dict())
    generic = ActionResult(action=result.action, disposition="succeeded")
    with pytest.raises(ValidationError):
        validator.validate(generic.to_dict())


def test_external_controller_drives_exact_json_run_across_restart(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    first = controller(tmp_path)
    submitted = first.submit_target(admission)
    started = first.start(request, admission_id=admission.admission_id)
    pending = first.next(request.validation_id)
    authoritative = first.runtime_store.resume(request.validation_id)
    first.close()

    assert submitted["data"]["admission_root"] == admission.root
    assert started["data"]["status"] == "waiting"
    assert authoritative is not None
    assert started["state_root"] == pending["state_root"] == authoritative.root
    action = _action(pending["data"]["action"])
    assert pending["data"]["action_root"] == action.root
    assert pending["data"]["target_snapshot"] == admission.target_snapshot.to_dict()
    assert pending["data"]["capability"] == admission.capabilities[0].to_dict()
    assert pending["data"]["expected_result_schema"]["$id"].endswith(action.root)

    restarted = controller(tmp_path)
    assert restarted.next(request.validation_id) == pending
    completed = restarted.submit(
        request.validation_id,
        validation_result(action),
        authority="external",
    )
    outcome = restarted.outcome(request.validation_id)
    restarted.close()

    assert completed["data"]["terminal"] is True
    assert completed["data"]["status"] == "completed"
    assert outcome["data"]["projection"]["workflow"] == "validation"

    final = controller(tmp_path)
    assert final.status(request.validation_id)["data"]["result_root"] is not None
    assert final.outcome(request.validation_id) == outcome
    final.close()


def test_controller_rejects_wrong_duplicate_and_stale_submissions(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    managed = controller(tmp_path)
    managed.submit_target(admission)
    managed.start(request, admission_id=admission.admission_id)
    next_document = managed.next(request.validation_id)
    action = _action(next_document["data"]["action"])
    result = validation_result(action)
    _validate_expected_result(next_document, result)
    with pytest.raises(ValueError, match="no terminal outcome"):
        managed.outcome(request.validation_id)

    wrong_action = replace(action, action_id="wrong")
    wrong_result = ActionResult(
        action=wrong_action,
        disposition="succeeded",
        payload=result.payload,
        output_refs=result.output_refs,
        resource_usage=result.resource_usage,
        lineage=(wrong_action.ref, *result.output_refs),
    )
    with pytest.raises(ValueError, match="exact pending action"):
        managed.submit(request.validation_id, wrong_result, authority="external")
    with pytest.raises(ValueError, match="submission authority"):
        managed.submit(request.validation_id, result, authority="automatic")
    with pytest.raises(TypeError, match="requires a TargetSnapshot"):
        managed.submit(
            request.validation_id,
            result,
            authority="external",
            current_snapshot=object(),  # type: ignore[arg-type]
        )
    stale = TargetSnapshot(
        target=admission.target_snapshot.target,
        revision="stale",
        state=admission.target_snapshot.state,
    )
    with pytest.raises(ValueError, match="cannot change target currentness"):
        managed.submit(
            request.validation_id,
            result,
            authority="external",
            current_snapshot=stale,
        )

    managed.submit(request.validation_id, result, authority="external")
    with pytest.raises(ValueError, match="does not accept another result"):
        managed.submit(request.validation_id, result, authority="external")
    with pytest.raises(ValueError, match="terminal"):
        managed.next(request.validation_id)
    managed.close()


def test_controller_rejects_unadmitted_or_divergent_requests(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    managed = controller(tmp_path)
    with pytest.raises(ValueError, match="unknown target admission"):
        managed.start(request, admission_id="missing")
    managed.submit_target(admission)

    changed_snapshot = TargetSnapshot(
        target=admission.target_snapshot.target,
        revision="changed",
        state=admission.target_snapshot.state,
    )
    changed = replace(
        request,
        target_snapshot=changed_snapshot,
        lineage=(request.claim.ref, changed_snapshot.ref),
    )
    with pytest.raises(ValueError, match="admitted target snapshot"):
        managed.start(changed, admission_id=admission.admission_id)

    too_small = replace(
        admission,
        admission_id="small",
        resource_limits={"max_actions": 0, "max_failures": 0, "max_retries": 0},
        lineage=admission.lineage,
    )
    managed.submit_target(too_small)
    with pytest.raises(ValueError, match="budget exceeds"):
        managed.start(request, admission_id="small")
    with pytest.raises(ValueError, match="unknown external run id"):
        managed.status("missing")
    managed.close()


def test_agent_store_preserves_exact_bindings_and_rejects_non_rsi_revision(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    store = SQLiteAgentStore(tmp_path / "agent.sqlite3")
    store.put_admission(admission)
    binding = AgentRunBinding("validation", request, admission, admission.target_snapshot)
    store.bind_run(binding)

    current = TargetSnapshot(
        target=admission.target_snapshot.target,
        revision="batch-19",
        state={"temperature_c": 30.5},
    )
    with pytest.raises(ValueError, match="non-RSI agent runs cannot mutate"):
        store.update_snapshot(
            binding.run_id,
            prior=admission.target_snapshot,
            current=current,
        )
    assert store.load_run(binding.run_id) == binding

    other = TargetSnapshot(
        target=TargetRef(target_id="other", kind="physical-process"),
        revision="one",
        state={},
    )
    with pytest.raises(ValueError, match="different target"):
        store.update_snapshot(
            binding.run_id,
            prior=admission.target_snapshot,
            current=other,
        )
    with pytest.raises(ValueError, match="changed before update"):
        store.update_snapshot(binding.run_id, prior=current, current=current)
    store.close()


def test_start_recovers_an_exact_binding_without_runtime_history(tmp_path) -> None:
    admission = target_admission()
    request = validation_request()
    seed = controller(tmp_path)
    seed.submit_target(admission)
    seed.agent_store.bind_run(
        AgentRunBinding("validation", request, admission, admission.target_snapshot)
    )
    with pytest.raises(ValueError, match="no authoritative runtime history"):
        seed.status(request.validation_id)
    seed.close()

    recovered = controller(tmp_path)
    started = recovered.start(request, admission_id=admission.admission_id)
    assert started["data"]["status"] == "waiting"
    with pytest.raises(ValueError, match="use resume"):
        recovered.start(request, admission_id=admission.admission_id)
    recovered.close()


def test_controller_projects_every_exposed_workflow_from_the_same_runtime(tmp_path) -> None:
    for case in workflow_cases():
        managed = controller(tmp_path / case.command)
        managed.submit_target(case.admission)
        started = managed.start(
            case.request,
            admission_id=case.admission.admission_id,
        )
        run_id = case.request.canonical_run().run_id
        resumed = managed.resume(run_id)
        pending = managed.next(run_id)
        authoritative = managed.runtime_store.resume(run_id)

        assert authoritative is not None
        assert started["data"]["workflow"] == case.command.replace(
            "validate", "validation"
        ).replace("investigate", "investigation").replace("improve", "improvement")
        assert started["state_root"] == resumed["state_root"] == pending["state_root"]
        assert pending["state_root"] == authoritative.root
        assert pending["data"]["action"]["data"]["kind"] == case.expected_action
        managed.close()


def test_controller_submits_each_nonvalidation_workflow_frontier(tmp_path) -> None:
    context = comparison_context()
    for case in workflow_cases()[1:]:
        managed = controller(tmp_path / case.command)
        managed.submit_target(case.admission)
        managed.start(case.request, admission_id=case.admission.admission_id)
        run_id = case.request.canonical_run().run_id
        pending = managed.next(run_id)
        action = _action(pending["data"]["action"])
        if case.command == "investigate":
            result = CycleReasoner().reason(action)
        elif case.command == "improve":
            result = make_cycle_result(
                action=action,
                proposal=cycle_proposal(action, context=context, accepted=True),
            )
        else:
            result = DeterministicGovernanceProvider(context).experiment(action)

        _validate_expected_result(pending, result)
        submitted = managed.submit(run_id, result, authority="external")
        assert submitted["state_root"] != pending["state_root"]
        managed.close()


def test_investigation_schema_conforms_across_reasoning_and_experiment_phases(
    tmp_path,
) -> None:
    case = next(case for case in workflow_cases() if case.command == "investigate")
    managed = controller(tmp_path)
    managed.submit_target(case.admission)
    managed.start(case.request, admission_id=case.admission.admission_id)
    run_id = case.request.canonical_run().run_id
    seen: set[str] = set()

    for _ in range(12):
        pending = managed.next(run_id)
        action = _action(pending["data"]["action"])
        seen.add(action.kind)
        result = (
            CycleReasoner().reason(action)
            if action.kind == INVESTIGATION_REASONING_ACTION_KIND
            else CycleExperimenter().experiment(action)
        )
        _validate_expected_result(pending, result)
        submitted = managed.submit(run_id, result, authority="external")
        if submitted["data"]["terminal"]:
            break

    assert seen == {
        INVESTIGATION_REASONING_ACTION_KIND,
        INVESTIGATION_EXPERIMENT_ACTION_KIND,
    }
    assert submitted["data"]["terminal"] is True
    managed.close()


def test_rsi_schema_conforms_through_apply_verify_and_rollback(tmp_path) -> None:
    context = comparison_context()
    case = next(case for case in workflow_cases() if case.command == "rsi")
    request = self_change_request(context, activate=True)
    managed = controller(tmp_path)
    managed.submit_target(case.admission)
    managed.start(request, admission_id=case.admission.admission_id)
    run_id = request.canonical_run().run_id
    governance = DeterministicGovernanceProvider(context)
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        context=context,
        verification="rejected",
    )
    seen: set[str] = set()

    for _ in range(8):
        pending = managed.next(run_id)
        action = _action(pending["data"]["action"])
        seen.add(action.kind)
        if action.kind == INDEPENDENT_REVIEW_ACTION_KIND:
            result = governance.review(action)
        elif action.kind in {
            HISTORICAL_EVALUATION_ACTION_KIND,
            FORWARD_SHADOW_ACTION_KIND,
        }:
            result = governance.experiment(action)
        elif action.kind == VERIFY_APPLICATION_ACTION_KIND:
            result = target.verify(action)
        else:
            result = target.apply(action)
        _validate_expected_result(pending, result)
        submitted = managed.submit(
            run_id,
            result,
            authority="external",
            current_snapshot=target.snapshot,
        )
        if submitted["data"]["terminal"]:
            break

    assert seen == {
        HISTORICAL_EVALUATION_ACTION_KIND,
        FORWARD_SHADOW_ACTION_KIND,
        INDEPENDENT_REVIEW_ACTION_KIND,
        APPLY_CANDIDATE_ACTION_KIND,
        VERIFY_APPLICATION_ACTION_KIND,
        ROLLBACK_APPLICATION_ACTION_KIND,
    }
    assert submitted["data"]["terminal"] is True
    managed.close()


def test_controller_rejects_improvement_and_rsi_admission_drift(tmp_path) -> None:
    cases = {case.command: case for case in workflow_cases()}
    context = comparison_context()
    improvement_case = cases["improve"]
    ungoverned = improvement_request(context)
    managed = controller(tmp_path / "improvement")
    managed.submit_target(improvement_case.admission)
    with pytest.raises(ValueError, match="improvement request is not bound"):
        managed.start(ungoverned, admission_id=improvement_case.admission.admission_id)
    managed.close()

    rsi_case = cases["rsi"]
    divergent_requirement = ApplicationGovernanceRequirement(
        requirement_id="divergent-authority",
        authority_record_type="external_application_authority",
        target_snapshot=rsi_case.admission.target_snapshot,
        governing_refs=(rsi_case.admission.evaluation_contract.ref,),
        lineage=(
            rsi_case.admission.target_snapshot.ref,
            rsi_case.admission.evaluation_contract.ref,
        ),
    )
    divergent = type(rsi_case.admission).create(
        admission_id="rsi-divergent",
        target_snapshot=rsi_case.admission.target_snapshot,
        objective=rsi_case.admission.objective,
        evaluation_contract=rsi_case.admission.evaluation_contract,
        capabilities=rsi_case.admission.capabilities,
        application_requirement=divergent_requirement,
        resource_limits=rsi_case.admission.resource_limits,
    )
    managed = controller(tmp_path / "rsi")
    managed.submit_target(divergent)
    with pytest.raises(ValueError, match="RSI request is not bound"):
        managed.start(rsi_case.request, admission_id=divergent.admission_id)
    managed.close()


def test_target_submission_indexes_current_sourced_baseline_evidence(tmp_path) -> None:
    admission = target_admission()
    evidence = Evidence(
        evidence_type="support",
        data={"sample": 1},
        subject_refs=(admission.objective.ref,),
        source_refs=(admission.evaluation_contract.ref,),
        target_snapshot=admission.target_snapshot,
        weight=1.0,
    )
    with_evidence = type(admission).create(
        admission_id="with-evidence",
        target_snapshot=admission.target_snapshot,
        objective=admission.objective,
        evaluation_contract=admission.evaluation_contract,
        capabilities=admission.capabilities,
        evidence_baseline=(evidence,),
        application_requirement=admission.application_requirement,
        resource_limits=admission.resource_limits,
    )
    managed = controller(tmp_path)
    managed.submit_target(with_evidence)
    assert managed.knowledge_store.get(evidence.root) == evidence
    managed.close()


def test_rsi_restart_repairs_snapshot_after_runtime_first_apply_crash(tmp_path) -> None:
    context = comparison_context()
    base_case = next(case for case in workflow_cases() if case.command == "rsi")
    request = self_change_request(context, activate=True)
    managed = controller(tmp_path)
    managed.submit_target(base_case.admission)
    managed.start(request, admission_id=base_case.admission.admission_id)
    run_id = request.canonical_run().run_id
    governance = DeterministicGovernanceProvider(context)
    for _ in range(3):
        pending = managed.next(run_id)
        action = _action(pending["data"]["action"])
        result = (
            governance.review(action)
            if action.kind == INDEPENDENT_REVIEW_ACTION_KIND
            else governance.experiment(action)
        )
        _validate_expected_result(pending, result)
        managed.submit(run_id, result, authority="external")

    apply_pending = managed.next(run_id)
    apply_action = _action(apply_pending["data"]["action"])
    target = DeterministicApplicationTarget(
        context.baseline_snapshot,
        context=context,
    )
    apply_result = target.apply(apply_action)
    _validate_expected_result(apply_pending, apply_result)
    binding = managed.agent_store.load_run(run_id)
    assert binding is not None
    binding, progress = managed._resume(binding)
    workflow = managed._workflow(binding)
    assert type(progress) is RSIProgress
    assert type(workflow) is RSIWorkflow
    update = workflow.submit(
        progress,
        apply_result,
        prior_snapshot=binding.current_snapshot,
        current_snapshot=target.snapshot,
        authority="external",
    )
    managed._record(update.transitions)
    stale = managed.agent_store.load_run(run_id)
    assert stale is not None
    assert stale.current_snapshot == context.baseline_snapshot
    managed.close()

    restarted = controller(tmp_path)
    status = restarted.status(run_id)
    repaired = restarted.agent_store.load_run(run_id)
    assert repaired is not None
    assert repaired.current_snapshot == target.snapshot
    assert status["data"]["target_snapshot_root"] == target.snapshot.root
    assert restarted.next(run_id)["data"]["target_snapshot"] == target.snapshot.to_dict()
    restarted.close()
