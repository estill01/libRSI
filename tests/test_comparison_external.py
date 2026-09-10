from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace

import pytest

from librsi import ComparativeSelectionPolicy
from librsi.comparison.external import REQUEST_SCHEMA, evaluate_request
from librsi.identity import digest
from tests.block14_support import candidate_for, comparison_context, trial_batch


@pytest.fixture
def request_payload():
    context = comparison_context()
    batch = trial_batch(context, candidate_for(context, "candidate"))
    return (
        {
            "schema": REQUEST_SCHEMA,
            "selection_id": "host-selection-1",
            "current_snapshot": context.baseline_snapshot.to_dict(),
            "contract": context.contract.to_dict(),
            "risk_policy": context.risk_policy.to_dict(),
            "batches": [batch.to_dict()],
        },
        context,
        batch,
    )


def test_wire_result_is_the_canonical_policy_decision(request_payload):
    payload, context, batch = request_payload
    before = deepcopy(payload)
    result = evaluate_request(payload)
    expected = ComparativeSelectionPolicy.select(
        selection_id=payload["selection_id"],
        contract=context.contract,
        batches=(batch,),
        risk_policy=context.risk_policy,
    )
    assert result["decision"] == expected.to_dict()
    assert expected.disposition == "selected"
    assert result["activation_authorized"] is False
    assert result["request_root"] == digest(payload)
    assert payload == before


def test_wire_rejection_and_inconclusive_are_successful_evaluations(request_payload):
    payload, context, batch = request_payload
    for candidate_rows, invalid, disposition in (
        (((70.0, 20.0, 2.0),) * 3, (), "rejected"),
        (((76.0, 16.0, 2.0),) * 3, (("candidate", 2),), "inconclusive"),
    ):
        payload["batches"] = [
            trial_batch(
                context,
                batch.candidate,
                candidate_rows=candidate_rows,
                invalid=invalid,
            ).to_dict()
        ]
        response = evaluate_request(payload)
        assert response["status"] == "succeeded"
        assert response["decision"]["data"]["disposition"] == "none-accepted"
        assert response["decision"]["data"]["assessments"][0]["data"]["disposition"] == disposition


@pytest.mark.parametrize(
    "change", ["stale", "tampered", "duplicate", "empty", "too-many", "wrong-type", "unknown-field"]
)
def test_invalid_requests_fail_closed(request_payload, change):
    payload, context, batch = request_payload
    if change == "stale":
        payload["current_snapshot"] = replace(context.baseline_snapshot, revision="later").to_dict()
    elif change == "tampered":
        payload["batches"][0]["data"]["candidate"]["data"]["candidate_id"] = "forged"
    elif change == "duplicate":
        payload["batches"] *= 2
    elif change == "empty":
        payload["batches"] = []
    elif change == "too-many":
        payload["batches"] *= 33
    elif change == "wrong-type":
        payload["risk_policy"] = batch.to_dict()
    else:
        payload["activate"] = True
    with pytest.raises((ValueError, TypeError)):
        evaluate_request(payload)


def test_isolated_processes_replay_without_creating_local_state(request_payload, tmp_path):
    payload, _, _ = request_payload
    results = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-m", "librsi.comparison"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            timeout=20,
            check=True,
        )
        assert completed.stderr == ""
        results.append(completed.stdout)
    assert results[0] == results[1]
    assert json.loads(results[0]) == evaluate_request(payload)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema":1,"schema":2}',
        '{"value":NaN}',
        "[]",
        "{}",
        '"secret"',
        "\xff",
        " " * (8 * 1024 * 1024 + 1),
    ],
    ids=["duplicate-key", "nonfinite", "array", "empty", "scalar", "invalid-json", "oversize"],
)
def test_process_rejects_malformed_or_oversize_input(payload):
    completed = subprocess.run(
        [sys.executable, "-m", "librsi.comparison"],
        input=payload,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode == 2
    assert completed.stderr == ""
    response = json.loads(completed.stdout)
    assert response["status"] == "failed"
    assert response["activation_authorized"] is False
    assert response["error"]["code"] == "invalid_comparison_request"
