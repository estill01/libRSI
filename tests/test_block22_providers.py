from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import librsi.providers.codex as codex_provider
from librsi import Goal, ReasoningRequest, TargetRef, TargetSnapshot
from librsi.providers import (
    CODEX_CLIENT_HANDOFF,
    CodexAppServerBackend,
    CodexAppServerExecutor,
    CodexProcessPolicy,
    OpenAIResponsesBackend,
    OpenAIResponsesConfig,
    validate_codex_client,
)
from librsi.providers.prompt import reasoning_prompt, reasoning_result_from_text


def _request() -> ReasoningRequest:
    target = TargetRef(target_id="queue", kind="process")
    snapshot = TargetSnapshot(target=target, revision="v1", state={"depth": 3})
    goal = Goal(statement="Explain queue growth", target=target)
    return ReasoningRequest(
        request_id="reason-1",
        kind="explanation",
        instruction="Explain the queue growth",
        input_refs=(goal.ref, snapshot.ref),
        target_snapshot=snapshot,
        lineage=(goal.ref, snapshot.ref),
    )


_RESULT = json.dumps(
    {
        "content": {
            "explanations": [{"statement": "Arrival exceeds service.", "basis": ["snapshot"]}]
        },
        "narration": "A proposal, not validated evidence.",
    }
)


class _FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_text=_RESULT, status="completed", error=None, incomplete_details=None
        )


def test_openai_responses_adapter_preserves_typed_proposal_boundary() -> None:
    responses = _FakeResponses()
    backend = OpenAIResponsesBackend(
        OpenAIResponsesConfig("gpt-test"), client=SimpleNamespace(responses=responses)
    )
    request = _request()
    result = backend.respond(request)
    assert result.request == request and result.kind == "explanation"
    assert responses.calls == [{"model": "gpt-test", "input": reasoning_prompt(request)}]
    assert "truth" in reasoning_prompt(request)
    assert "provider" not in result.to_dict()["data"]


def test_provider_output_cannot_promote_authority_or_bypass_schema() -> None:
    request = _request()
    with pytest.raises(ValueError, match="unsupported or missing"):
        reasoning_result_from_text(request, '{"content":{},"accepted":true}')
    with pytest.raises(ValueError, match="missing fields"):
        reasoning_result_from_text(request, '{"content":{}}')
    with pytest.raises(ValueError, match="one JSON object"):
        reasoning_result_from_text(request, "not json")
    with pytest.raises(ValueError, match="bounded"):
        reasoning_result_from_text(request, "x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(TypeError, match="ReasoningRequest"):
        reasoning_prompt(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ReasoningRequest"):
        reasoning_result_from_text(object(), _RESULT)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must be text"):
        reasoning_result_from_text(request, object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bounded"):
        reasoning_result_from_text(request, "")
    with pytest.raises(TypeError, match="string-keyed"):
        reasoning_result_from_text(request, "[]")
    with pytest.raises(TypeError, match="content must be"):
        reasoning_result_from_text(request, '{"content":[] }')
    with pytest.raises(TypeError, match="narration"):
        reasoning_result_from_text(request, '{"content":{},"narration":1}')


class _FakeExecutor:
    def complete(self, request: ReasoningRequest) -> str:
        assert request == _request()
        return _RESULT


def test_codex_backend_is_equivalent_to_other_reasoning_backends() -> None:
    result = CodexAppServerBackend(_FakeExecutor()).respond(_request())
    assert result == reasoning_result_from_text(_request(), _RESULT)


def _fake_codex_module() -> ModuleType:
    module = ModuleType("codex_app_server_client")
    module.__version__ = "0.1.0"
    module.__all__ = [f"name_{index}" for index in range(92)]
    module.PINNED_PROTOCOL = SimpleNamespace(
        codex_version=CODEX_CLIENT_HANDOFF.codex_version,
        source_commit=CODEX_CLIENT_HANDOFF.codex_source_commit,
        schema_tree_root_sha256=CODEX_CLIENT_HANDOFF.schema_root_sha256,
        selected_surface_root_sha256=CODEX_CLIENT_HANDOFF.selected_surface_root_sha256,
    )

    class ThreadStartParams:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class TurnStartParams(ThreadStartParams):
        pass

    class AgentMessageDeltaNotification:
        def __init__(self, thread_id: str, turn_id: str, delta: str) -> None:
            self.threadId, self.turnId, self.delta = thread_id, turn_id, delta

    class TurnCompletedNotification:
        def __init__(self, thread_id: str, turn_id: str, status: str = "completed") -> None:
            self.threadId = thread_id
            self.turn = SimpleNamespace(id=turn_id, status=status, error=None)

    module.ThreadStartParams, module.TurnStartParams = ThreadStartParams, TurnStartParams
    module.AgentMessageDeltaNotification = AgentMessageDeltaNotification
    module.TurnCompletedNotification = TurnCompletedNotification
    return module


class _FakeSession:
    def __init__(self, module: ModuleType) -> None:
        self.module, self.thread_args, self.turn_args = module, None, None

    async def start_thread(self, params: object, *, timeout: float) -> object:
        self.thread_args = (params, timeout)
        return SimpleNamespace(thread=SimpleNamespace(id="thread-1"))

    async def start_turn(self, params: object, *, timeout: float) -> object:
        self.turn_args = (params, timeout)
        return SimpleNamespace(turn=SimpleNamespace(id="turn-1"))

    async def events(self):
        yield self.module.AgentMessageDeltaNotification("thread-1", "turn-1", _RESULT[:20])
        yield self.module.AgentMessageDeltaNotification("thread-1", "turn-1", _RESULT[20:])
        yield self.module.TurnCompletedNotification("thread-1", "turn-1")


def test_injected_codex_session_uses_typed_surface_without_process_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fake_codex_module()
    module.AppServerSession = _FakeSession
    session = _FakeSession(module)
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    monkeypatch.setattr(codex_provider, "validate_codex_client", lambda value: None)

    async def factory() -> object:
        return session

    executor = CodexAppServerExecutor(
        CodexProcessPolicy(owner="software-factory"), session_factory=factory
    )
    assert executor.complete(_request()) == _RESULT
    assert session.thread_args is not None and session.turn_args is not None


def test_process_owner_contract_rejects_two_owners_before_import() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        CodexProcessPolicy(owner="other")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="only standalone"):
        CodexProcessPolicy(owner="software-factory", executable=Path("/usr/bin/codex"))
    with pytest.raises(ValueError, match="absolute"):
        CodexProcessPolicy(owner="standalone", executable=Path("codex"))
    with pytest.raises(ValueError, match="cwd"):
        CodexProcessPolicy(owner="standalone", cwd=Path("relative"))
    with pytest.raises(ValueError, match="timeout"):
        CodexProcessPolicy(owner="standalone", timeout_seconds=0)
    with pytest.raises(TypeError, match="CodexProcessPolicy"):
        CodexAppServerExecutor(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="require an injected"):
        CodexAppServerExecutor(CodexProcessPolicy(owner="software-factory"))

    async def factory() -> object:
        return object()

    with pytest.raises(ValueError, match="owns its session"):
        CodexAppServerExecutor(CodexProcessPolicy(owner="standalone"), session_factory=factory)


def test_exact_handoff_and_compatibility_manifest_are_frozen(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="origin"):
        validate_codex_client(_fake_codex_module())
    path = Path(__file__).parents[1] / "src/librsi/providers/compatibility.json"
    manifest = json.loads(path.read_text())
    assert (
        manifest["codex_app_server_client"]["producer_revision"]
        == CODEX_CLIENT_HANDOFF.producer_revision
    )
    assert manifest["posture"] == "no-license-selected/unpublished"
    provider_root = path.parent
    entries = []
    for source in sorted(provider_root.glob("*.py")):
        data = source.read_bytes()
        entries.append(
            {"path": source.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        )
    payload = (json.dumps(entries, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert manifest["librsi_adapter"]["content_root_sha256"] == hashlib.sha256(payload).hexdigest()

    with pytest.raises(TypeError, match="imported module"):
        validate_codex_client(object())  # type: ignore[arg-type]
    wrong_version = _fake_codex_module()
    wrong_version.__version__ = "9.0"
    with pytest.raises(RuntimeError, match="version"):
        validate_codex_client(wrong_version)
    wrong_artifact = _fake_codex_module()
    package = tmp_path / "codex_app_server_client"
    protocol = package / "_protocol"
    protocol.mkdir(parents=True)
    origin = package / "__init__.py"
    origin.write_text("")
    (protocol / "compatibility.json").write_text("{}")
    (protocol / "public-api.json").write_text("{}")
    wrong_artifact.__file__ = str(origin)
    with pytest.raises(RuntimeError, match="implementation root"):
        validate_codex_client(wrong_artifact)

    client = importlib.import_module("codex_app_server_client")
    validate_codex_client(client)


def test_base_import_does_not_import_provider_sdks() -> None:
    script = "import sys, librsi; assert 'openai' not in sys.modules; assert 'codex_app_server_client' not in sys.modules"
    subprocess.run([sys.executable, "-c", script], check=True)


def test_sync_executor_rejects_nested_event_loop() -> None:
    module = _fake_codex_module()

    async def factory() -> object:
        return _FakeSession(module)

    executor = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=factory
    )

    async def run() -> None:
        with pytest.raises(RuntimeError, match="complete_async"):
            executor.complete(_request())

    asyncio.run(run())


def test_openai_configuration_lazy_import_and_failure_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="model"):
        OpenAIResponsesConfig(" ")
    with pytest.raises(TypeError, match="OpenAIResponsesConfig"):
        OpenAIResponsesBackend(object())  # type: ignore[arg-type]

    def missing(name: str) -> ModuleType:
        raise ImportError(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    with pytest.raises(RuntimeError, match=r"libRSI\[openai\]"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test")).respond(_request())

    module = ModuleType("openai")
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    with pytest.raises(RuntimeError, match="does not expose"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test")).respond(_request())

    class OpenAI:
        def __init__(self) -> None:
            self.responses = _FakeResponses()

    module.OpenAI = OpenAI
    assert (
        OpenAIResponsesBackend(OpenAIResponsesConfig(" gpt-test ")).respond(_request()).request
        == _request()
    )

    with pytest.raises(TypeError, match="responses.create"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=object()).respond(
            _request()
        )
    bad = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: object()))
    with pytest.raises(RuntimeError, match="did not complete"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=bad).respond(_request())

    for status in ("failed", "incomplete", "in_progress", "cancelled", "queued"):
        failed = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda status=status, **kwargs: SimpleNamespace(
                    status=status, output_text=_RESULT, error=None, incomplete_details=None
                )
            )
        )
        with pytest.raises(RuntimeError, match="did not complete"):
            OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=failed).respond(
                _request()
            )
    for details in ({"code": "failed"}, {"reason": "max_output_tokens"}):
        unsettled = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda details=details, **kwargs: SimpleNamespace(
                    status="completed",
                    output_text=_RESULT,
                    error=details if "code" in details else None,
                    incomplete_details=details if "reason" in details else None,
                )
            )
        )
        with pytest.raises(RuntimeError, match="did not complete"):
            OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=unsettled).respond(
                _request()
            )
    no_text = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                status="completed", error=None, incomplete_details=None, output_text=None
            )
        )
    )
    with pytest.raises(TypeError, match="output_text"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=no_text).respond(
            _request()
        )

    class SpoofedStatus:
        def __eq__(self, other: object) -> bool:
            return other == "completed"

    spoofed = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(
                status=SpoofedStatus(), error=None, incomplete_details=None, output_text=_RESULT
            )
        )
    )
    with pytest.raises(RuntimeError, match="did not complete"):
        OpenAIResponsesBackend(OpenAIResponsesConfig("gpt-test"), client=spoofed).respond(
            _request()
        )


def test_standalone_executor_uses_one_owned_client_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fake_codex_module()
    module.AppServerSession = _FakeSession
    session = _FakeSession(module)
    state: dict[str, object] = {}

    module.resolve_codex_binary = lambda executable: (
        state.setdefault("binary", executable) or "binary"
    )
    module.inspect_compatibility = lambda binary: (
        state.setdefault("compatibility", binary) or "compat"
    )
    module.StdioTransport = lambda binary: SimpleNamespace(binary=binary)
    module.ClientIdentity = lambda *args: args

    class Client:
        async def initialize(self, identity: object) -> object:
            state["identity"] = identity
            return session

        async def close(self) -> None:
            state["closed"] = True

    class AppServerClient:
        @staticmethod
        async def connect(transport: object, compatibility: object) -> Client:
            state["connect"] = (transport, compatibility)
            return Client()

    module.AppServerClient = AppServerClient
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    monkeypatch.setattr(codex_provider, "validate_codex_client", lambda value: None)
    executor = CodexAppServerExecutor(CodexProcessPolicy(owner="standalone"))
    assert asyncio.run(executor.complete_async(_request())) == _RESULT
    assert state["closed"] is True

    with pytest.raises(TypeError, match="ReasoningRequest"):
        asyncio.run(executor.complete_async(object()))  # type: ignore[arg-type]


def test_injected_session_shape_and_event_filtering_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _fake_codex_module()
    module.AppServerSession = _FakeSession
    monkeypatch.setattr(importlib, "import_module", lambda name: module)
    monkeypatch.setattr(codex_provider, "validate_codex_client", lambda value: None)

    async def invalid_factory() -> object:
        return object()

    invalid = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=invalid_factory
    )
    with pytest.raises(TypeError, match="accepted typed AppServerSession"):
        asyncio.run(invalid.complete_async(_request()))

    class FilteringSession(_FakeSession):
        async def events(self):
            yield self.module.AgentMessageDeltaNotification("other", "turn-1", "ignored")
            yield self.module.AgentMessageDeltaNotification("thread-1", "other", "ignored")
            yield object()
            yield self.module.AgentMessageDeltaNotification("thread-1", "turn-1", _RESULT)
            yield self.module.TurnCompletedNotification("other", "turn-1")
            yield self.module.TurnCompletedNotification("thread-1", "other")
            yield self.module.TurnCompletedNotification("thread-1", "turn-1")

    async def filtering_factory() -> object:
        return FilteringSession(module)

    filtered = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=filtering_factory
    )
    assert asyncio.run(filtered.complete_async(_request())) == _RESULT

    class NoThreadSession(_FakeSession):
        async def start_thread(self, params: object, *, timeout: float) -> object:
            return SimpleNamespace(thread=SimpleNamespace(id=""))

    async def no_thread_factory() -> object:
        return NoThreadSession(module)

    no_thread = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=no_thread_factory
    )
    with pytest.raises(RuntimeError, match="thread id"):
        asyncio.run(no_thread.complete_async(_request()))

    class FailedSession(_FakeSession):
        async def events(self):
            yield self.module.AgentMessageDeltaNotification("thread-1", "turn-1", _RESULT)
            yield self.module.TurnCompletedNotification("thread-1", "turn-1", "failed")

    async def failed_factory() -> object:
        return FailedSession(module)

    failed = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=failed_factory
    )
    with pytest.raises(RuntimeError, match="did not complete"):
        asyncio.run(failed.complete_async(_request()))

    class ExhaustedSession(_FakeSession):
        async def events(self):
            yield self.module.AgentMessageDeltaNotification("thread-1", "turn-1", _RESULT)

    async def exhausted_factory() -> object:
        return ExhaustedSession(module)

    exhausted = CodexAppServerExecutor(
        CodexProcessPolicy(owner="embedding-host"), session_factory=exhausted_factory
    )
    with pytest.raises(RuntimeError, match="before exact turn"):
        asyncio.run(exhausted.complete_async(_request()))
