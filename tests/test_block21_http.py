from __future__ import annotations

import json

from fastapi.testclient import TestClient

from librsi import ServiceLimits, record_from_dict
from librsi.http import HTTPTokenPolicy, create_http_app
from librsi.runtime import Action
from librsi.service import LibRSIService
from tests.block20_support import target_admission, validation_request, validation_result


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_http_drives_restartable_run_with_structured_auth_and_duplicate_safety(tmp_path) -> None:
    policy = HTTPTokenPolicy.from_tokens(
        read_token="read-secret",
        mutate_token="mutate-secret",
        apply_token="apply-secret",
    )
    admission = target_admission()
    request = validation_request()
    first = LibRSIService.local(tmp_path)
    app = create_http_app(first, token_policy=policy)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 403
        assert client.get("/ready", headers=_headers("read-secret")).status_code == 200
        admitted = client.post(
            "/v1/targets",
            json={"record": admission.to_dict()},
            headers=_headers("mutate-secret"),
        )
        started = client.post(
            "/v1/runs/validation",
            json={"request": request.to_dict(), "admission_id": admission.admission_id},
            headers=_headers("mutate-secret"),
        )
        pending = client.get(
            f"/v1/runs/{request.validation_id}/actions",
            headers=_headers("read-secret"),
        )
        assert admitted.status_code == started.status_code == pending.status_code == 200
        state_root = started.json()["state_root"]
        action = record_from_dict(pending.json()["data"]["action"])
        assert type(action) is Action

    restarted = LibRSIService.local(tmp_path)
    app = create_http_app(restarted, token_policy=policy)
    with TestClient(app) as client:
        status = client.get(
            f"/v1/runs/{request.validation_id}",
            headers=_headers("read-secret"),
        )
        assert status.json()["state_root"] == state_root
        body = {
            "result": validation_result(action).to_dict(),
            "authority": "external",
        }
        submitted = client.post(
            f"/v1/runs/{request.validation_id}/results",
            json=body,
            headers=_headers("mutate-secret"),
        )
        duplicate = client.post(
            f"/v1/runs/{request.validation_id}/results",
            json=body,
            headers=_headers("mutate-secret"),
        )
        outcome = client.get(
            f"/v1/runs/{request.validation_id}/outcome",
            headers=_headers("read-secret"),
        )
        assert submitted.status_code == outcome.status_code == 200
        assert duplicate.status_code == 400
        assert duplicate.json()["$schema"] == "librsi.external-error/v1"
        assert outcome.json()["data"]["projection"]["workflow"] == "validation"


def test_http_projection_is_transport_neutral_and_managed_execution_is_bounded(tmp_path) -> None:
    from tests.block21_support import (
        AutomaticValidationExperimenter,
        automatic_validation_admission,
        automatic_validation_registry,
    )

    provider = AutomaticValidationExperimenter()
    service = LibRSIService.local(
        tmp_path,
        registry=automatic_validation_registry(provider),
    )
    admission = automatic_validation_admission()
    request = validation_request()
    app = create_http_app(service)
    with TestClient(app) as client:
        client.post("/v1/targets", json={"record": admission.to_dict()}).raise_for_status()
        started = client.post(
            "/v1/runs/validation",
            json={"request": request.to_dict(), "admission_id": admission.admission_id},
        )
        managed = client.post(
            f"/v1/runs/{request.validation_id}/managed",
            json={"max_actions": 4, "allow_application": False},
        )
        outcome = client.get(f"/v1/runs/{request.validation_id}/outcome")
        assert started.status_code == managed.status_code == outcome.status_code == 200
        assert managed.json()["data"]["execution"]["stop_reason"] == "outcome"
        assert outcome.json() == service.get_outcome(request.validation_id)


def test_http_rejects_oversized_malformed_unauthorized_and_secret_inputs(tmp_path) -> None:
    service = LibRSIService.local(
        tmp_path,
        limits=ServiceLimits(max_request_bytes=256),
    )
    policy = HTTPTokenPolicy.from_tokens(mutate_token="super-secret")
    app = create_http_app(service, token_policy=policy)
    with TestClient(app) as client:
        unauthorized = client.post("/v1/targets", json={"record": {}})
        invalid = client.post(
            "/v1/targets",
            json={"record": {}, "secret": "must-not-echo"},
            headers=_headers("super-secret"),
        )
        oversized = client.post(
            "/v1/knowledge/query",
            content=json.dumps({"query": {"padding": "x" * 1000}}),
            headers={**_headers("super-secret"), "content-type": "application/json"},
        )
        assert unauthorized.status_code == 403
        assert invalid.status_code == 422
        assert oversized.status_code == 413
        assert "must-not-echo" not in invalid.text
        assert "super-secret" not in unauthorized.text + invalid.text + oversized.text


def test_http_token_permissions_are_distinct() -> None:
    policy = HTTPTokenPolicy.from_tokens(
        read_token="reader",
        mutate_token="writer",
        apply_token="applier",
    )
    policy.authorize("Bearer reader", "read")
    policy.authorize("Bearer writer", "mutate")
    policy.authorize("Bearer applier", "apply")
    import pytest

    with pytest.raises(PermissionError, match="required permission"):
        policy.authorize("Bearer reader", "mutate")
    with pytest.raises(PermissionError, match="required permission"):
        policy.authorize("Bearer writer", "apply")


def test_http_application_results_require_the_distinct_apply_scope(tmp_path) -> None:
    from librsi import (
        Action,
        ActionResult,
        Run,
        RunBudget,
        RuntimeFailure,
        TargetRef,
        TargetSnapshot,
    )

    target = TargetRef(target_id="http-application-security")
    snapshot = TargetSnapshot(target=target, revision="one", state={})
    run = Run(
        run_id="http-application-security-run",
        intent=target.ref,
        target_snapshot=snapshot,
        budget=RunBudget(max_actions=1),
    )
    action = Action(
        action_id="apply",
        run=run.ref,
        kind="apply-selected-candidate",
        input_refs=(snapshot.ref,),
        lineage=(run.ref, snapshot.ref),
    )
    result = ActionResult(
        action=action,
        disposition="failed",
        failure=RuntimeFailure(classification="execution", message="not authorized"),
    )
    policy = HTTPTokenPolicy.from_tokens(mutate_token="writer", apply_token="applier")
    service = LibRSIService.local(tmp_path)
    with TestClient(create_http_app(service, token_policy=policy)) as client:
        body = {"result": result.to_dict(), "authority": "external"}
        denied = client.post(
            "/v1/runs/missing/results",
            json=body,
            headers=_headers("writer"),
        )
        authorized = client.post(
            "/v1/runs/missing/results",
            json=body,
            headers=_headers("applier"),
        )
        assert denied.status_code == 403
        assert authorized.status_code == 400
        assert "required permission" in denied.text
        assert "unknown external run id" in authorized.text


def test_http_exposes_every_workflow_lifecycle_and_closed_query_surface(tmp_path) -> None:
    service = LibRSIService.local(tmp_path)
    app = create_http_app(service)
    with TestClient(app) as client:
        assert client.get("/v1/capabilities").status_code == 200
        for case in __import__(
            "tests.block20_support", fromlist=["workflow_cases"]
        ).workflow_cases():
            client.post("/v1/targets", json={"record": case.admission.to_dict()}).raise_for_status()
            workflow = (
                case.command.replace("validate", "validation")
                .replace("investigate", "investigation")
                .replace("improve", "improvement")
            )
            started = client.post(
                f"/v1/runs/{workflow}",
                json={
                    "request": case.request.to_dict(),
                    "admission_id": case.admission.admission_id,
                },
            )
            run_id = case.request.canonical_run().run_id
            assert started.status_code == 200
            assert client.get(f"/v1/runs/{run_id}").status_code == 200
            assert client.get(f"/v1/runs/{run_id}/status").status_code == 200
            assert client.get(f"/v1/runs/{run_id}/actions").status_code == 200
            assert client.post(f"/v1/runs/{run_id}/resume").status_code == 200
        query = client.post("/v1/knowledge/query", json={})
        assert query.status_code == 200
        assert query.json()["data"]["count"] == 0

        wrong_target = client.post(
            "/v1/targets",
            json={"record": validation_request().to_dict()},
        )
        wrong_start = client.post(
            "/v1/runs/validation",
            json={"request": target_admission().to_dict(), "admission_id": "missing"},
        )
        invalid_length = client.get("/health", headers={"content-length": "invalid"})
        assert wrong_target.status_code == wrong_start.status_code == 400
        assert invalid_length.status_code == 400
