from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from librsi.http import HTTPTokenPolicy, create_http_app
from librsi.intake import IntakeRequest
from librsi.mcp import create_mcp_server
from librsi.providers import OpenAIResponsesBackend, OpenAIResponsesConfig
from librsi.service import LibRSIService, ServiceLimits
from librsi.service.factory import load_service_factory
from tests.test_goal_intake import Proposer, service


def test_http_intake_auth_clarification_and_durable_handle(tmp_path):
    backend = Proposer()
    engine = service(tmp_path, backend)
    policy = HTTPTokenPolicy.from_tokens(read_token="read", mutate_token="write")
    app = create_http_app(engine, token_policy=policy)
    read = {"Authorization": "Bearer read"}
    write = {"Authorization": "Bearer write"}
    body = {"request_id": "http-1", "goal": "Improve this prompt"}
    with TestClient(app) as client:
        assert client.post("/v1/intake", json=body, headers=read).status_code == 403
        assert backend.calls == []
        assert client.get("/v1/intake/adapters", headers=read).json()["data"]["enabled"] is True
        response = client.post("/v1/intake", json=body, headers=write)
        assert response.status_code == 200, response.text
        run_id = response.json()["data"]["run_id"]
        assert client.get(f"/v1/runs/{run_id}", headers=read).status_code == 200
        receipt = client.get("/v1/intake/http-1", headers=read).json()
        assert receipt["data"] == response.json()["data"]
        assert client.post("/v1/intake", json=body, headers=write).json() == response.json()
        assert len(backend.calls) == 3
        assert client.get("/v1/intake/unknown", headers=read).status_code == 404
        assert (
            client.post(
                "/v1/intake", json={**body, "allow_application": True}, headers=write
            ).status_code
            == 422
        )
        assert (
            client.post("/v1/intake", json={**body, "goal": "different"}, headers=write).status_code
            == 400
        )
    with TestClient(create_http_app(LibRSIService.local(tmp_path / "disabled"))) as client:
        assert client.post("/v1/intake", json=body).status_code == 409


def test_mcp_intake_tools_are_available_only_when_configured(tmp_path):
    async def exercise():
        with service(tmp_path) as engine:
            async with Client(create_mcp_server(engine)) as client:
                tools = {item.name for item in (await client.list_tools()).tools}
                assert {"librsi_intake", "librsi_intake_status", "librsi_intake_adapters"} <= tools
                result = await client.call_tool(
                    "librsi_intake",
                    {
                        "request_id": "mcp-1",
                        "goal": "Improve the prompt",
                        "adapter_id": "prompts-v1",
                    },
                )
                assert not result.is_error
                assert result.structured_content["data"]["run_id"] == "mcp-1:improvement"
                status = await client.call_tool("librsi_intake_status", {"request_id": "mcp-1"})
                assert status.structured_content["data"] == result.structured_content["data"]
        with LibRSIService.local(tmp_path / "disabled") as engine:
            async with Client(create_mcp_server(engine)) as client:
                tools = {item.name for item in (await client.list_tools()).tools}
                assert "librsi_intake" not in tools

    asyncio.run(exercise())


def test_existing_openai_adapter_carries_real_intake_prompts_without_new_sdk_path(tmp_path):
    fixture = Proposer()
    calls = []

    def create(**kwargs):
        from librsi import record_from_dict

        calls.append(kwargs)
        prompt = json.loads(kwargs["input"])
        request = record_from_dict(prompt["task"])
        result = fixture.respond(request)
        from librsi.identity import thaw

        return SimpleNamespace(
            status="completed",
            error=None,
            incomplete_details=None,
            output_text=json.dumps({"content": thaw(result.content)}),
        )

    backend = OpenAIResponsesBackend(
        OpenAIResponsesConfig(model="explicit-test-model"),
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    with service(tmp_path, backend) as engine:
        assert (
            engine.intake(IntakeRequest("openai", "Improve this prompt"))["data"]["disposition"]
            == "started"
        )
    assert len(calls) == 3
    assert all(call["model"] == "explicit-test-model" for call in calls)
    assert "goal-operationalization" in calls[1]["input"]


def test_trusted_factory_preserves_limits_and_can_configure_intake(tmp_path, monkeypatch):
    import sys

    limits = ServiceLimits(max_request_bytes=4096)

    def factory(*, data_directory, limits):
        from tests.test_goal_intake import adapters

        return LibRSIService.local(
            data_directory, limits=limits, intake_backend=Proposer(), intake_adapters=adapters()
        )

    monkeypatch.setitem(sys.modules, "intake_test_factory", SimpleNamespace(create=factory))
    with load_service_factory(
        "intake_test_factory:create", data_directory=str(tmp_path), limits=limits
    ) as engine:
        assert engine.intake_enabled
        assert engine.limits == limits
    with pytest.raises(ValueError, match="module:callable"):
        load_service_factory("missing", data_directory=str(tmp_path), limits=limits)


@pytest.mark.parametrize("module", ["librsi.http.__main__", "librsi.mcp.__main__"])
def test_executables_accept_explicit_service_factory(module):
    from importlib import import_module

    args = import_module(module)._parser().parse_args(["--factory", "my_host:create_service"])
    assert args.factory == "my_host:create_service"
