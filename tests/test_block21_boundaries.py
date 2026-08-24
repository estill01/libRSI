from __future__ import annotations

import asyncio

import pytest

from librsi import CapabilityRegistry, KnowledgeQuery, ManagedBounds, ServiceLimits
from librsi.http import HTTPTokenCredential, HTTPTokenPolicy, create_http_app
from librsi.mcp import StaticTokenVerifier, create_mcp_server
from librsi.protocol import ExternalAgentController
from librsi.service import (
    LibRSIService,
    ManagedExecution,
    canonical_record_from_dict,
    knowledge_query_from_dict,
)
from librsi.service.managed import ManagedServiceRunner, _data
from tests.block13_support import intent_context
from tests.block20_support import target_admission


def test_service_codecs_cover_complete_queries_and_reject_transport_drift() -> None:
    context = intent_context()
    reference = context.target.ref.to_dict()
    query = knowledge_query_from_dict(
        {
            "record_types": ["evidence"],
            "target": context.target.to_dict(),
            "current_snapshot": context.snapshot.to_dict(),
            "subject_refs": [reference],
            "evidence_types": ["support"],
            "lineage_refs": [reference],
            "source_run_id": "run-1",
            "valid": True,
            "currentness": "current",
            "limit": 2,
        }
    )
    assert query == KnowledgeQuery(
        record_types=("evidence",),
        target=context.target,
        current_snapshot=context.snapshot,
        subject_refs=(context.target.ref,),
        evidence_types=("support",),
        lineage_refs=(context.target.ref,),
        source_run_id="run-1",
        valid=True,
        currentness="current",
        limit=2,
    )
    admission = target_admission()
    assert canonical_record_from_dict(admission.to_dict(), label="admission") == admission

    invalid_queries = (
        {1: "non-text-key"},
        {"unknown": True},
        {"record_types": "evidence"},
        {"record_types": [1]},
        {"subject_refs": "ref"},
        {"subject_refs": [{"record_type": "target", "root": "0" * 64}]},
        {"target": context.snapshot.to_dict()},
        {"current_snapshot": context.target.to_dict()},
    )
    for payload in invalid_queries:
        with pytest.raises(ValueError):
            knowledge_query_from_dict(payload)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        canonical_record_from_dict([], label="record")  # type: ignore[arg-type]


def test_service_operational_records_and_constructor_boundaries(tmp_path) -> None:
    class BoundBypass(int):
        def __gt__(self, other):
            return False

    for value, error in ((True, TypeError), (0, ValueError)):
        with pytest.raises(error):
            ServiceLimits(max_managed_actions=value)  # type: ignore[arg-type]
        with pytest.raises(error):
            ManagedBounds(max_actions=value)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="integer"):
        ManagedBounds(max_actions=BoundBypass(2))
    with pytest.raises(TypeError, match="boolean"):
        ManagedBounds(max_actions=1, allow_application=1)  # type: ignore[arg-type]
    for changes, error in (
        ({"run_id": ""}, ValueError),
        ({"executed_action_roots": ("z" * 64,)}, ValueError),
        ({"terminal": 1}, TypeError),
    ):
        values = {
            "run_id": "run",
            "stop_reason": "bound",
            "executed_action_roots": ("0" * 64,),
            "terminal": False,
            "status": "waiting",
            "state_root": "1" * 64,
            **changes,
        }
        with pytest.raises(error):
            ManagedExecution(**values)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="ExternalAgentController"):
        LibRSIService(object())  # type: ignore[arg-type]
    controller = ExternalAgentController.local(tmp_path / "controller")
    with pytest.raises(TypeError, match="registry"):
        LibRSIService(controller, registry=object())  # type: ignore[arg-type]
    controller.close()
    controller = ExternalAgentController.local(tmp_path / "controller-2")
    with pytest.raises(TypeError, match="limits"):
        LibRSIService(controller, limits=object())  # type: ignore[arg-type]
    controller.close()
    controller = ExternalAgentController.local(tmp_path / "controller-3")
    with pytest.raises(TypeError, match="snapshot resolver"):
        LibRSIService(
            controller,
            current_snapshot_resolver=object(),  # type: ignore[arg-type]
        )
    controller.close()


def test_service_method_and_managed_runner_boundaries(tmp_path, monkeypatch) -> None:
    service = LibRSIService.local(tmp_path / "service")
    for method in (
        service.start,
        service.validate,
        service.investigate,
        service.improve,
        service.recurse,
    ):
        with pytest.raises(TypeError):
            method(object(), admission_id="admission")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="KnowledgeQuery"):
        service.query_knowledge(object())  # type: ignore[arg-type]
    assert service.query_knowledge()["data"]["count"] == 0
    assert service.resume if callable(service.resume) else False

    runner = ManagedServiceRunner(service.controller, CapabilityRegistry(), ServiceLimits())
    with pytest.raises(ValueError, match="run id"):
        runner.run("", ManagedBounds(1))
    with pytest.raises(TypeError, match="ManagedBounds"):
        runner.run("run", object())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="structured data"):
        _data({"data": "invalid"})
    monkeypatch.setattr(service.controller, "status", lambda _run_id: {"data": {}})
    with pytest.raises(RuntimeError, match="state root"):
        runner._report("run", reason="bound", executed=[])
    service.close()
    service.close()
    with pytest.raises(RuntimeError, match="closed"):
        service.readiness()

    for controller, registry, limits in (
        (object(), CapabilityRegistry(), ServiceLimits()),
        (ExternalAgentController.local(tmp_path / "runner-registry"), object(), ServiceLimits()),
        (ExternalAgentController.local(tmp_path / "runner-limits"), CapabilityRegistry(), object()),
    ):
        try:
            with pytest.raises(TypeError):
                ManagedServiceRunner(controller, registry, limits)  # type: ignore[arg-type]
        finally:
            if type(controller) is ExternalAgentController:
                controller.close()
    controller = ExternalAgentController.local(tmp_path / "runner-resolver")
    try:
        with pytest.raises(TypeError, match="snapshot resolver"):
            ManagedServiceRunner(
                controller,
                CapabilityRegistry(),
                ServiceLimits(),
                object(),  # type: ignore[arg-type]
            )
    finally:
        controller.close()


def test_service_rejects_oversized_direct_requests_before_mutation(tmp_path) -> None:
    service = LibRSIService.local(tmp_path, limits=ServiceLimits(max_request_bytes=1))
    with pytest.raises(ValueError, match="request byte limit"):
        service.submit_target(target_admission())
    assert service.controller.agent_store.get_admission("fermenter-admission") is None
    service.close()


def test_http_auth_and_app_construction_boundaries(tmp_path) -> None:
    with pytest.raises(ValueError, match="required"):
        HTTPTokenCredential("", frozenset({"read"}))
    with pytest.raises(ValueError, match="permissions"):
        HTTPTokenCredential("token", frozenset())
    with pytest.raises(TypeError, match="credentials"):
        HTTPTokenPolicy(())
    with pytest.raises(ValueError, match="unique"):
        HTTPTokenPolicy(
            (
                HTTPTokenCredential("same", frozenset({"read"})),
                HTTPTokenCredential("same", frozenset({"mutate"})),
            )
        )
    with pytest.raises(ValueError, match="cannot be empty"):
        HTTPTokenPolicy.from_tokens(read_token="")
    policy = HTTPTokenPolicy.from_tokens(read_token="read")
    with pytest.raises(ValueError, match="unsupported"):
        policy.authorize("Bearer read", "unknown")
    with pytest.raises(PermissionError, match="invalid"):
        policy.authorize("Bearer wrong", "read")

    service = LibRSIService.local(tmp_path)
    with pytest.raises(TypeError, match="LibRSIService"):
        create_http_app(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="token policy"):
        create_http_app(service, token_policy=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="close-service"):
        create_http_app(service, close_service=1)  # type: ignore[arg-type]
    service.close()


def test_mcp_auth_and_server_construction_boundaries(tmp_path) -> None:
    for token, scopes in (("", ("librsi",)), ("token", ()), ("token", ("",))):
        with pytest.raises(ValueError):
            StaticTokenVerifier(token, scopes=scopes)
    verifier = StaticTokenVerifier("token", scopes=(" librsi ",))
    assert asyncio.run(verifier.verify_token("wrong")) is None
    accepted = asyncio.run(verifier.verify_token("token"))
    assert accepted is not None and accepted.scopes == ["librsi"]

    service = LibRSIService.local(tmp_path)
    with pytest.raises(TypeError, match="LibRSIService"):
        create_mcp_server(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="configured together"):
        create_mcp_server(service, token_verifier=verifier)
    service.close()


def test_executable_entrypoints_compose_and_close_without_real_servers(
    tmp_path,
    monkeypatch,
) -> None:
    import librsi.http.__main__ as http_main
    import librsi.mcp.__main__ as mcp_main

    http_calls: list[object] = []
    monkeypatch.setenv("LIBRSI_HTTP_READ_TOKEN", "reader")
    monkeypatch.setattr(
        http_main.uvicorn, "run", lambda app, **kwargs: http_calls.append((app, kwargs))
    )
    assert http_main.main(["--data-dir", str(tmp_path / "http"), "--port", "8123"]) == 0
    assert http_calls[0][1]["port"] == 8123  # type: ignore[index]

    runs: list[tuple[str, dict[str, object]]] = []
    closed: list[bool] = []

    class FakeService:
        def close(self) -> None:
            closed.append(True)

    class FakeServer:
        def run(self, transport: str, **kwargs: object) -> None:
            runs.append((transport, kwargs))

    monkeypatch.setattr(mcp_main.LibRSIService, "local", lambda *args, **kwargs: FakeService())
    monkeypatch.setattr(mcp_main, "create_mcp_server", lambda *args, **kwargs: FakeServer())
    monkeypatch.setenv("LIBRSI_MCP_TOKEN", "token")
    auth = [
        "--auth-issuer-url",
        "https://issuer.example",
        "--auth-resource-url",
        "https://rsi.example",
    ]
    assert mcp_main.main(["--data-dir", str(tmp_path / "mcp-stdio"), *auth]) == 0
    assert (
        mcp_main.main(
            [
                "--data-dir",
                str(tmp_path / "mcp-http"),
                "--transport",
                "streamable-http",
                "--port",
                "8124",
                *auth,
            ]
        )
        == 0
    )
    assert runs[0] == ("stdio", {})
    assert runs[1][0] == "streamable-http"
    assert runs[1][1]["stateless_http"] is True
    assert closed == [True, True]

    monkeypatch.delenv("LIBRSI_MCP_TOKEN")
    with pytest.raises(ValueError, match="configured together"):
        mcp_main.main(["--auth-issuer-url", "https://issuer.example"])


def test_http_entrypoint_closes_service_when_server_startup_fails(tmp_path, monkeypatch) -> None:
    import librsi.http.__main__ as http_main

    closed: list[bool] = []

    class FakeService:
        def close(self) -> None:
            closed.append(True)

    fake = FakeService()
    monkeypatch.setattr(http_main.LibRSIService, "local", lambda *args, **kwargs: fake)
    monkeypatch.setattr(http_main, "create_http_app", lambda service, **kwargs: object())

    def fail(*args, **kwargs):
        raise RuntimeError("startup failed")

    monkeypatch.setattr(http_main.uvicorn, "run", fail)
    with pytest.raises(RuntimeError, match="startup failed"):
        http_main.main(["--data-dir", str(tmp_path)])
    assert closed == [True]
