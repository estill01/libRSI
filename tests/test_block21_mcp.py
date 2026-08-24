from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

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
