from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ResourceError, ToolError

import librsi.mcp.server as mcp_server
from librsi import ServiceLimits
from librsi.mcp import create_mcp_server
from librsi.service import LibRSIService
from tests.block20_support import target_admission, validation_request

EXPECTED_TOOLS = {
    "librsi_target_submit",
    "librsi_validate",
    "librsi_investigate",
    "librsi_improve",
    "librsi_recurse",
    "librsi_run_status",
    "librsi_run_next",
    "librsi_run_submit",
    "librsi_run_resume",
    "librsi_run_managed",
    "librsi_run_outcome",
    "librsi_knowledge_query",
    "librsi_capabilities",
}


def _structured(result) -> dict:
    assert result.is_error is False
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def test_in_memory_mcp_projects_tools_resources_and_durable_handles(tmp_path) -> None:
    async def exercise() -> None:
        service = LibRSIService.local(tmp_path)
        server = create_mcp_server(service)
        admission = target_admission()
        request = validation_request()
        async with Client(server) as client:
            tools = await client.list_tools()
            assert {item.name for item in tools.tools} == EXPECTED_TOOLS
            admitted = _structured(
                await client.call_tool(
                    "librsi_target_submit",
                    {"admission": admission.to_dict()},
                )
            )
            started = _structured(
                await client.call_tool(
                    "librsi_validate",
                    {
                        "request": request.to_dict(),
                        "admission_id": admission.admission_id,
                    },
                )
            )
            status = _structured(
                await client.call_tool(
                    "librsi_run_status",
                    {"run_id": request.validation_id},
                )
            )
            resource = await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert admitted["data"]["admission_root"] == admission.root
            assert started["run_id"] == status["run_id"] == request.validation_id
            assert json.loads(resource.contents[0].text)["state_root"] == status["state_root"]
        service.close()

    asyncio.run(exercise())


def _source_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source = str(Path(__file__).parents[1] / "src")
    environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
    return environment


def test_stdio_mcp_smoke_uses_the_executable_server(tmp_path) -> None:
    async def exercise() -> None:
        transport = stdio_client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "librsi.mcp", "--data-dir", str(tmp_path)],
                env=_source_environment(),
            )
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            assert {item.name for item in tools.tools} == EXPECTED_TOOLS
            capabilities = _structured(await client.call_tool("librsi_capabilities", {}))
            assert capabilities["data"]["workflows"] == [
                "validation",
                "investigation",
                "improvement",
                "rsi",
            ]

    asyncio.run(exercise())


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_streamable_http_mcp_smoke_is_stateless_and_remote_capable(tmp_path) -> None:
    async def exercise(url: str) -> None:
        last_error: Exception | None = None
        for _ in range(60):
            try:
                async with Client(url) as client:
                    tools = await client.list_tools()
                    assert {item.name for item in tools.tools} == EXPECTED_TOOLS
                    capabilities = _structured(await client.call_tool("librsi_capabilities", {}))
                    assert capabilities["operation"] == "capabilities"
                    return
            except Exception as error:
                last_error = error
                await asyncio.sleep(0.1)
        raise AssertionError("Streamable HTTP MCP server did not become ready") from last_error

    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "librsi.mcp",
            "--data-dir",
            str(tmp_path),
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=_source_environment(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        asyncio.run(exercise(f"http://127.0.0.1:{port}/mcp"))
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    assert process.returncode is not None


def test_mcp_generic_submission_cannot_claim_automatic_or_application_authority(tmp_path) -> None:
    from librsi import (
        Action,
        ActionResult,
        Run,
        RunBudget,
        RuntimeFailure,
        TargetRef,
        TargetSnapshot,
    )

    async def exercise() -> None:
        service = LibRSIService.local(tmp_path)
        server = create_mcp_server(service)
        target = TargetRef(target_id="mcp-security")
        snapshot = TargetSnapshot(target=target, revision="one", state={})
        run = Run(
            run_id="mcp-security-run",
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
        async with Client(server) as client:
            automatic = await client.call_tool(
                "librsi_run_submit",
                {
                    "run_id": "missing",
                    "result": result.to_dict(),
                    "authority": "automatic",
                },
            )
            application = await client.call_tool(
                "librsi_run_submit",
                {
                    "run_id": "missing",
                    "result": result.to_dict(),
                    "authority": "external",
                },
            )
            assert automatic.is_error is True
            assert application.is_error is True
            assert "automatic capability authority" in automatic.content[0].text
            assert "application authority" in application.content[0].text
        service.close()

    asyncio.run(exercise())


def test_mcp_projects_every_workflow_and_lifecycle_operation(tmp_path) -> None:
    from librsi import record_from_dict
    from librsi.runtime import Action
    from tests.block20_support import validation_result, workflow_cases

    async def exercise() -> None:
        service = LibRSIService.local(tmp_path)
        server = create_mcp_server(service)
        async with Client(server) as client:
            for case in workflow_cases():
                _structured(
                    await client.call_tool(
                        "librsi_target_submit",
                        {"admission": case.admission.to_dict()},
                    )
                )
                tool = {
                    "validate": "librsi_validate",
                    "investigate": "librsi_investigate",
                    "improve": "librsi_improve",
                    "rsi": "librsi_recurse",
                }[case.command]
                _structured(
                    await client.call_tool(
                        tool,
                        {
                            "request": case.request.to_dict(),
                            "admission_id": case.admission.admission_id,
                        },
                    )
                )
                run_id = case.request.canonical_run().run_id
                _structured(await client.call_tool("librsi_run_status", {"run_id": run_id}))
                pending = _structured(await client.call_tool("librsi_run_next", {"run_id": run_id}))
                _structured(await client.call_tool("librsi_run_resume", {"run_id": run_id}))
                managed = _structured(
                    await client.call_tool(
                        "librsi_run_managed",
                        {"run_id": run_id, "max_actions": 1},
                    )
                )
                assert managed["data"]["execution"]["stop_reason"] == "authority-gate"
                if case.command == "validate":
                    action = record_from_dict(pending["data"]["action"])
                    assert type(action) is Action
                    _structured(
                        await client.call_tool(
                            "librsi_run_submit",
                            {
                                "run_id": run_id,
                                "result": validation_result(action).to_dict(),
                                "authority": "external",
                                "current_snapshot": case.admission.target_snapshot.to_dict(),
                            },
                        )
                    )
                    outcome = _structured(
                        await client.call_tool("librsi_run_outcome", {"run_id": run_id})
                    )
                    resource = await client.read_resource(f"librsi://runs/{run_id}/outcome")
                    assert json.loads(resource.contents[0].text) == outcome
            knowledge = _structured(await client.call_tool("librsi_knowledge_query", {}))
            assert knowledge["data"]["count"] == 0
        service.close()

    asyncio.run(exercise())


def test_mcp_common_request_bound_rejects_before_canonical_decode_or_mutation(tmp_path) -> None:
    async def exercise() -> None:
        service = LibRSIService.local(
            tmp_path,
            limits=ServiceLimits(max_request_bytes=1),
        )
        server = create_mcp_server(service)
        async with Client(server) as client:
            rejected = await client.call_tool(
                "librsi_target_submit",
                {"admission": target_admission().to_dict()},
            )
            assert rejected.is_error is True
            assert "request byte limit" in rejected.content[0].text
            assert service.controller.agent_store.get_admission("fermenter-admission") is None
        service.close()

    asyncio.run(exercise())


def test_mcp_expected_failures_remain_actionable_and_server_faults_remain_masked(
    tmp_path, monkeypatch
) -> None:
    async def exercise() -> None:
        service = LibRSIService.local(tmp_path / "service")
        admission = target_admission()
        request = validation_request()
        service.submit_target(admission)
        service.start(request, admission_id=admission.admission_id)
        server = create_mcp_server(service)
        async with Client(server) as client:
            malformed = await client.call_tool(
                "librsi_target_submit",
                {"admission": {}},
            )
            missing = await client.call_tool(
                "librsi_run_status",
                {"run_id": "missing"},
            )
            invalid_bound = await client.call_tool(
                "librsi_run_managed",
                {"run_id": "missing", "max_actions": 0},
            )
            malformed_query = await client.call_tool(
                "librsi_knowledge_query",
                {"query": {"unknown": True}},
            )
            assert "unsupported semantic record schema" in malformed.content[0].text
            assert "unknown external run id" in missing.content[0].text
            assert "positive" in invalid_bound.content[0].text
            assert "unknown fields" in malformed_query.content[0].text
            assert all(
                result.is_error is True
                for result in (malformed, missing, invalid_bound, malformed_query)
            )

            def crash() -> dict:
                raise RuntimeError("private server detail")

            monkeypatch.setattr(service, "capabilities", crash)
            unexpected = await client.call_tool("librsi_capabilities", {})
            assert unexpected.is_error is True
            assert "internal tool error" in unexpected.content[0].text
            assert "private server detail" not in unexpected.content[0].text

            def tool_error_crash() -> dict:
                raise ToolError("private transport-tool detail")

            monkeypatch.setattr(service, "capabilities", tool_error_crash)
            transport_tool = await client.call_tool("librsi_capabilities", {})
            assert "internal tool error" in transport_tool.content[0].text
            assert "private transport-tool detail" not in transport_tool.content[0].text

            def value_error_crash() -> dict:
                raise ValueError("private value-tool detail")

            monkeypatch.setattr(service, "capabilities", value_error_crash)
            value_tool = await client.call_tool("librsi_capabilities", {})
            assert "internal tool error" in value_tool.content[0].text
            assert "private value-tool detail" not in value_tool.content[0].text

            def exact_origin_spoof() -> dict:
                raise mcp_server._ClientFault(object(), "private exact-origin detail")

            monkeypatch.setattr(service, "capabilities", exact_origin_spoof)
            exact_origin = await client.call_tool("librsi_capabilities", {})
            assert "internal tool error" in exact_origin.content[0].text
            assert "private exact-origin detail" not in exact_origin.content[0].text

            class ForgedClientFault(mcp_server._ClientFault):
                pass

            def subclass_origin_spoof() -> dict:
                raise ForgedClientFault(object(), "private subclass-origin detail")

            monkeypatch.setattr(service, "capabilities", subclass_origin_spoof)
            subclass_origin = await client.call_tool("librsi_capabilities", {})
            assert "internal tool error" in subclass_origin.content[0].text
            assert "private subclass-origin detail" not in subclass_origin.content[0].text

            def resource_crash(_run_id: str) -> dict:
                raise RuntimeError("private resource detail")

            monkeypatch.setattr(service, "get_run", resource_crash)
            with pytest.raises(Exception) as unexpected_resource:
                await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert "internal resource error" in str(unexpected_resource.value)
            assert "private resource detail" not in str(unexpected_resource.value)

            def resource_error_crash(_run_id: str) -> dict:
                raise ResourceError("private transport-resource detail")

            monkeypatch.setattr(service, "get_run", resource_error_crash)
            with pytest.raises(Exception) as transport_resource:
                await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert "internal resource error" in str(transport_resource.value)
            assert "private transport-resource detail" not in str(transport_resource.value)

            def value_resource_crash(_run_id: str) -> dict:
                raise ValueError("private value-resource detail")

            monkeypatch.setattr(service, "get_run", value_resource_crash)
            with pytest.raises(Exception) as value_resource:
                await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert "internal resource error" in str(value_resource.value)
            assert "private value-resource detail" not in str(value_resource.value)

            def exact_resource_origin_spoof(_run_id: str) -> dict:
                raise mcp_server._ClientFault(
                    object(),
                    "private exact-resource-origin detail",
                    not_found=True,
                )

            monkeypatch.setattr(service, "get_run", exact_resource_origin_spoof)
            with pytest.raises(Exception) as exact_resource_origin:
                await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert "internal resource error" in str(exact_resource_origin.value)
            assert "private exact-resource-origin detail" not in str(exact_resource_origin.value)

            def subclass_resource_origin_spoof(_run_id: str) -> dict:
                raise ForgedClientFault(
                    object(),
                    "private subclass-resource-origin detail",
                    not_found=True,
                )

            monkeypatch.setattr(service, "get_run", subclass_resource_origin_spoof)
            with pytest.raises(Exception) as subclass_resource_origin:
                await client.read_resource(f"librsi://runs/{request.validation_id}")
            assert "internal resource error" in str(subclass_resource_origin.value)
            assert "private subclass-resource-origin detail" not in str(
                subclass_resource_origin.value
            )
        service.close()

        bounded = LibRSIService.local(
            tmp_path / "bounded",
            limits=ServiceLimits(max_request_bytes=1),
        )
        bounded_server = create_mcp_server(bounded)
        async with Client(bounded_server) as client:
            with pytest.raises(Exception, match="request byte limit"):
                await client.read_resource("librsi://runs/oversized")
        bounded.close()

    asyncio.run(exercise())
