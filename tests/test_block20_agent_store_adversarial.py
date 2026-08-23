from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest

from librsi import AgentRunBinding, CapabilityBinding, SQLiteAgentStore, TargetRef, TargetSnapshot
from tests.block20_support import target_admission, validation_request


def _binding():
    admission = target_admission()
    request = validation_request()
    return (
        admission,
        request,
        AgentRunBinding("validation", request, admission, admission.target_snapshot),
    )


def test_agent_binding_rejects_wrong_workflow_records_and_targets() -> None:
    admission, request, _ = _binding()
    with pytest.raises(ValueError, match="workflow does not match"):
        AgentRunBinding("rsi", request, admission, admission.target_snapshot)
    with pytest.raises(TypeError, match="TargetAdmission"):
        AgentRunBinding("validation", request, object(), admission.target_snapshot)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact current snapshot"):
        AgentRunBinding("validation", request, admission, object())  # type: ignore[arg-type]
    other = TargetSnapshot(
        target=TargetRef(target_id="other", kind="physical-process"),
        revision="one",
        state={},
    )
    with pytest.raises(ValueError, match="different target"):
        AgentRunBinding("validation", request, admission, other)


def test_agent_store_idempotence_divergence_and_closed_state(tmp_path) -> None:
    admission, request, binding = _binding()
    store = SQLiteAgentStore(tmp_path / "agent.sqlite3")
    assert store.get_admission("missing") is None
    with pytest.raises(TypeError, match="exact TargetAdmission"):
        store.put_admission(object())  # type: ignore[arg-type]
    store.put_admission(admission)
    assert store.put_admission(admission) == admission

    automatic = CapabilityBinding(
        action_kind="validation-evidence",
        family="experimenter",
        posture="automatic",
    )
    divergent_admission = type(admission).create(
        admission_id=admission.admission_id,
        target_snapshot=admission.target_snapshot,
        objective=admission.objective,
        evaluation_contract=admission.evaluation_contract,
        capabilities=(automatic,),
        application_requirement=admission.application_requirement,
        resource_limits=admission.resource_limits,
    )
    with pytest.raises(ValueError, match="divergent canonical data"):
        store.put_admission(divergent_admission)

    with pytest.raises(TypeError, match="AgentRunBinding"):
        store.bind_run(object())  # type: ignore[arg-type]
    assert store.load_run("missing") is None
    store.bind_run(binding)
    assert store.bind_run(binding) == binding
    divergent_request = replace(
        request,
        claim=replace(request.claim, statement="A divergent claim"),
        lineage=(
            replace(request.claim, statement="A divergent claim").ref,
            admission.target_snapshot.ref,
        ),
    )
    divergent_binding = AgentRunBinding(
        "validation", divergent_request, admission, admission.target_snapshot
    )
    with pytest.raises(ValueError, match="divergent external binding"):
        store.bind_run(divergent_binding)

    with pytest.raises(ValueError, match="unknown external run id"):
        store.update_snapshot(
            "missing",
            prior=admission.target_snapshot,
            current=admission.target_snapshot,
        )
    with pytest.raises(TypeError, match="exact TargetSnapshot"):
        store.update_snapshot(
            binding.run_id,
            prior=object(),  # type: ignore[arg-type]
            current=admission.target_snapshot,
        )
    store.close()
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.get_admission(admission.admission_id)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("workflow", "future", "workflow is unsupported"),
        ("request_root", "0" * 64, "roots diverge"),
        ("run_id", "forged-run", "lacks its immutable authority binding"),
    ],
)
def test_agent_store_detects_tampered_binding_columns(tmp_path, column, value, message) -> None:
    path = tmp_path / f"{column}.sqlite3"
    admission, _, binding = _binding()
    store = SQLiteAgentStore(path)
    store.put_admission(admission)
    store.bind_run(binding)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute(f"UPDATE agent_runs SET {column} = ?", (value,))
    connection.commit()
    connection.close()

    store = SQLiteAgentStore(path)
    run_id = value if column == "run_id" else binding.run_id
    with pytest.raises(ValueError, match=message):
        store.load_run(run_id)
    store.close()


def test_agent_store_rejects_noncanonical_serialized_admission(tmp_path) -> None:
    path = tmp_path / "serialized.sqlite3"
    admission = target_admission()
    store = SQLiteAgentStore(path)
    store.put_admission(admission)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute("UPDATE agent_admissions SET serialized = serialized || char(10)")
    connection.commit()
    connection.close()

    store = SQLiteAgentStore(path)
    with pytest.raises(ValueError, match="not exact canonical data"):
        store.get_admission(admission.admission_id)
    store.close()


def test_agent_store_rejects_mutated_run_to_admission_authority(tmp_path) -> None:
    path = tmp_path / "authority.sqlite3"
    external, request, binding = _binding()
    automatic = type(external).create(
        admission_id="automatic-admission",
        target_snapshot=external.target_snapshot,
        objective=external.objective,
        evaluation_contract=external.evaluation_contract,
        capabilities=(
            CapabilityBinding(
                action_kind="validation-evidence",
                family="experimenter",
                posture="automatic",
            ),
        ),
        application_requirement=external.application_requirement,
        resource_limits=external.resource_limits,
    )
    store = SQLiteAgentStore(path)
    store.put_admission(external)
    store.put_admission(automatic)
    store.bind_run(binding)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE agent_runs SET admission_root = ? WHERE run_id = ?",
        (automatic.root, request.validation_id),
    )
    connection.commit()
    connection.close()

    store = SQLiteAgentStore(path)
    with pytest.raises(ValueError, match="authority association has diverged"):
        store.load_run(request.validation_id)
    store.close()


def test_agent_store_requires_the_immutable_authority_record(tmp_path) -> None:
    path = tmp_path / "missing-authority.sqlite3"
    admission, _, binding = _binding()
    store = SQLiteAgentStore(path)
    store.put_admission(admission)
    store.bind_run(binding)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM agent_run_authorities WHERE run_id = ?", (binding.run_id,))
    connection.commit()
    connection.close()

    store = SQLiteAgentStore(path)
    with pytest.raises(ValueError, match="lacks its immutable authority binding"):
        store.load_run(binding.run_id)
    store.close()


def test_agent_store_rejects_admission_lookup_alias_tampering(tmp_path) -> None:
    path = tmp_path / "admission-alias.sqlite3"
    admission = target_admission()
    store = SQLiteAgentStore(path)
    store.put_admission(admission)
    store.close()

    connection = sqlite3.connect(path)
    connection.execute(
        "UPDATE agent_admissions SET admission_id = ? WHERE admission_id = ?",
        ("alias", admission.admission_id),
    )
    connection.commit()
    connection.close()

    store = SQLiteAgentStore(path)
    with pytest.raises(ValueError, match="identity diverges from canonical data"):
        store.get_admission("alias")
    store.close()
