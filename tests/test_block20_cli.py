from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from librsi import record_from_dict, serialize_record
from librsi.cli.main import main
from librsi.runtime import Action
from tests.block20_support import (
    target_admission,
    validation_request,
    validation_result,
    workflow_cases,
)


def _run(data: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source = str(Path(__file__).parents[1] / "src")
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "librsi", "--data-dir", str(data), *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )


def _write(path: Path, record) -> Path:
    path.write_text(serialize_record(record), encoding="utf-8")
    return path


def _document(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout if result.returncode == 0 else result.stderr)


def _action(document: dict) -> Action:
    record = record_from_dict(document)
    assert type(record) is Action
    return record


def _main_call(capsys, data: Path, *arguments: str) -> tuple[int, dict]:
    code = main(["--data-dir", str(data), *arguments])
    captured = capsys.readouterr()
    return code, json.loads(captured.out if code == 0 else captured.err)


def test_cli_drives_a_complete_external_run_through_json_and_restarts(tmp_path) -> None:
    data = tmp_path / "state"
    admission = target_admission()
    request = validation_request()
    admission_path = _write(tmp_path / "admission.json", admission)
    request_path = _write(tmp_path / "request.json", request)

    admitted = _run(data, "target", "submit", "--input", str(admission_path))
    started = _run(
        data,
        "validate",
        "--request",
        str(request_path),
        "--admission",
        admission.admission_id,
    )
    pending = _run(data, "next", request.validation_id)

    assert admitted.returncode == started.returncode == pending.returncode == 0
    pending_document = _document(pending)
    action = _action(pending_document["data"]["action"])
    result_path = _write(tmp_path / "result.json", validation_result(action))
    submitted = _run(
        data,
        "submit",
        request.validation_id,
        "--input",
        str(result_path),
        "--authority",
        "external",
    )
    status = _run(data, "status", request.validation_id)
    resumed = _run(data, "resume", request.validation_id)
    outcome = _run(data, "outcome", request.validation_id)

    assert (
        submitted.returncode == status.returncode == resumed.returncode == outcome.returncode == 0
    )
    assert _document(submitted)["data"]["terminal"] is True
    assert _document(status)["state_root"] == _document(resumed)["state_root"]
    assert _document(outcome)["data"]["projection"]["workflow"] == "validation"


def test_cli_rejects_malformed_unknown_noncanonical_and_duplicate_inputs(tmp_path) -> None:
    data = tmp_path / "state"
    malformed = _run(data, "target", "submit", "--input", "-", stdin="{broken")
    unknown = _run(data, "unknown")

    assert malformed.returncode == unknown.returncode == 2
    assert _document(malformed)["$schema"] == "librsi.external-error/v1"
    assert "valid JSON" in _document(malformed)["message"]
    assert _document(unknown)["error_type"] == "ValueError"

    admission = target_admission()
    payload = admission.to_dict()
    payload["extra"] = "not canonical"
    noncanonical_path = tmp_path / "noncanonical.json"
    noncanonical_path.write_text(json.dumps(payload), encoding="utf-8")
    noncanonical = _run(data, "target", "submit", "--input", str(noncanonical_path))
    assert noncanonical.returncode == 2
    assert "canonical record" in _document(noncanonical)["message"]

    admission_path = _write(tmp_path / "admission.json", admission)
    request = validation_request()
    request_path = _write(tmp_path / "request.json", request)
    assert _run(data, "target", "submit", "--input", str(admission_path)).returncode == 0
    assert (
        _run(
            data,
            "validate",
            "--request",
            str(request_path),
            "--admission",
            admission.admission_id,
        ).returncode
        == 0
    )
    pending = _document(_run(data, "next", request.validation_id))
    result_path = _write(
        tmp_path / "result.json",
        validation_result(_action(pending["data"]["action"])),
    )
    first = _run(
        data,
        "submit",
        request.validation_id,
        "--input",
        str(result_path),
        "--authority",
        "external",
    )
    duplicate = _run(
        data,
        "submit",
        request.validation_id,
        "--input",
        str(result_path),
        "--authority",
        "external",
    )
    assert first.returncode == 0
    assert duplicate.returncode == 2
    assert "does not accept another result" in _document(duplicate)["message"]


def test_cli_starts_every_exposed_workflow_from_canonical_records(tmp_path) -> None:
    for case in workflow_cases():
        command = case.command
        request = case.request
        admission = case.admission
        admission_path = _write(tmp_path / f"{command}-admission.json", admission)
        request_path = _write(tmp_path / f"{command}-request.json", request)
        state = tmp_path / f"{command}-state"

        assert _run(state, "target", "submit", "--input", str(admission_path)).returncode == 0
        started = _run(
            state,
            command,
            "--request",
            str(request_path),
            "--admission",
            admission.admission_id,
        )
        assert started.returncode == 0, started.stderr
        pending = _run(state, "next", request.canonical_run().run_id)
        assert pending.returncode == 0, pending.stderr
        assert _document(pending)["data"]["action"]["data"]["kind"] == case.expected_action


def test_cli_rejects_unknown_schema_and_missing_admission_authority(tmp_path) -> None:
    admission = target_admission()
    for field in ("evaluation_contract", "application_requirement"):
        payload = admission.to_dict()
        del payload["data"][field]
        path = tmp_path / f"missing-{field}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = _run(tmp_path / "state", "target", "submit", "--input", str(path))
        assert result.returncode == 2

    unknown = admission.to_dict()
    unknown["$schema"] = "librsi.record/v999"
    path = tmp_path / "unknown-schema.json"
    path.write_text(json.dumps(unknown), encoding="utf-8")
    result = _run(tmp_path / "state", "target", "submit", "--input", str(path))
    assert result.returncode == 2
    assert "schema" in _document(result)["message"].lower()


def test_in_process_cli_projection_covers_every_lifecycle_operation(tmp_path, capsys) -> None:
    data = tmp_path / "state"
    admission = target_admission()
    request = validation_request()
    admission_path = _write(tmp_path / "admission.json", admission)
    request_path = _write(tmp_path / "request.json", request)
    snapshot_path = _write(tmp_path / "snapshot.json", admission.target_snapshot)

    assert _main_call(capsys, data, "target", "submit", "--input", str(admission_path))[0] == 0
    assert (
        _main_call(
            capsys,
            data,
            "validate",
            "--request",
            str(request_path),
            "--admission",
            admission.admission_id,
        )[0]
        == 0
    )
    code, pending = _main_call(capsys, data, "next", request.validation_id)
    assert code == 0
    result_path = _write(
        tmp_path / "result.json",
        validation_result(_action(pending["data"]["action"])),
    )
    code, submitted = _main_call(
        capsys,
        data,
        "submit",
        request.validation_id,
        "--input",
        str(result_path),
        "--authority",
        "external",
        "--current-snapshot",
        str(snapshot_path),
    )
    assert code == 0
    assert submitted["data"]["terminal"] is True
    for command in ("status", "resume", "outcome"):
        assert _main_call(capsys, data, command, request.validation_id)[0] == 0

    wrong_type = _main_call(
        capsys, tmp_path / "wrong", "target", "submit", "--input", str(request_path)
    )
    unknown = _main_call(capsys, tmp_path / "unknown", "unknown")
    assert wrong_type[0] == unknown[0] == 2
