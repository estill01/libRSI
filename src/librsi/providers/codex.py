"""Required utils-backed Codex app-server reasoning and execution adapter."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from ..reasoning import ReasoningRequest, ReasoningResult
from .handoff import validate_codex_client
from .prompt import reasoning_prompt, reasoning_result_from_text

ProcessOwner = Literal["standalone", "embedding-host", "software-factory"]
SessionFactory = Callable[[], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class CodexProcessPolicy:
    owner: ProcessOwner
    executable: Path | None = None
    cwd: Path | None = None
    model: str | None = None
    timeout_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.owner not in ("standalone", "embedding-host", "software-factory"):
            raise ValueError("unsupported Codex process owner")
        if self.owner != "standalone" and self.executable is not None:
            raise ValueError("only standalone libRSI may configure an owned Codex executable")
        if self.executable is not None and not self.executable.is_absolute():
            raise ValueError("Codex executable must be absolute")
        if self.cwd is not None and not self.cwd.is_absolute():
            raise ValueError("Codex cwd must be absolute")
        if type(self.timeout_seconds) not in (int, float) or self.timeout_seconds <= 0:
            raise ValueError("Codex timeout must be positive")


@runtime_checkable
class CodexExecutor(Protocol):
    def complete(self, request: ReasoningRequest) -> str: ...


class CodexAppServerExecutor:
    """Own or borrow exactly one typed app-server session for one bounded task."""

    def __init__(
        self,
        policy: CodexProcessPolicy,
        *,
        session_factory: SessionFactory | None = None,
    ) -> None:
        if not isinstance(policy, CodexProcessPolicy):
            raise TypeError("Codex executor requires CodexProcessPolicy")
        if policy.owner == "standalone" and session_factory is not None:
            raise ValueError("standalone mode owns its session and cannot inject another owner")
        if policy.owner != "standalone" and session_factory is None:
            raise ValueError("embedded and Software Factory modes require an injected session")
        self._policy = policy
        self._session_factory = session_factory

    def complete(self, request: ReasoningRequest) -> str:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.complete_async(request))
        raise RuntimeError("use complete_async when an event loop is already running")

    async def complete_async(self, request: ReasoningRequest) -> str:
        if not isinstance(request, ReasoningRequest):
            raise TypeError("Codex execution requires a ReasoningRequest")
        module = importlib.import_module("codex_app_server_client")
        validate_codex_client(module)
        if self._session_factory is not None:
            session = await self._session_factory()
            return await self._run_session(module, session, request)

        binary = module.resolve_codex_binary(self._policy.executable)
        compatibility = module.inspect_compatibility(binary)
        client = await module.AppServerClient.connect(module.StdioTransport(binary), compatibility)
        try:
            session = await client.initialize(module.ClientIdentity("libRSI", "0.2.0"))
            return await self._run_session(module, session, request)
        finally:
            await client.close()

    async def _run_session(self, module: Any, session: object, request: ReasoningRequest) -> str:
        start_thread = getattr(session, "start_thread", None)
        start_turn = getattr(session, "start_turn", None)
        events = getattr(session, "events", None)
        if not isinstance(session, module.AppServerSession):
            raise TypeError("injected Codex session must be the accepted typed AppServerSession")
        if not callable(start_thread) or not callable(start_turn) or not callable(events):
            raise TypeError("injected Codex session must expose the typed session surface")
        thread_response = await start_thread(
            module.ThreadStartParams(
                approvalPolicy="never",
                cwd=str(self._policy.cwd) if self._policy.cwd is not None else None,
                ephemeral=True,
                model=self._policy.model,
                sandbox="read-only",
            ),
            timeout=self._policy.timeout_seconds,
        )
        thread_id = getattr(getattr(thread_response, "thread", None), "id", None)
        if not isinstance(thread_id, str) or not thread_id:
            raise RuntimeError("Codex thread response has no thread id")
        turn_response = await start_turn(
            module.TurnStartParams(
                input=({"type": "text", "text": reasoning_prompt(request)},),
                model=self._policy.model,
                threadId=thread_id,
            ),
            timeout=self._policy.timeout_seconds,
        )
        started_turn = getattr(turn_response, "turn", None)
        turn_id = getattr(started_turn, "id", None)
        if not isinstance(turn_id, str) or not turn_id:
            raise RuntimeError("Codex turn response has no turn id")
        chunks: list[str] = []
        settled = False
        async with asyncio.timeout(self._policy.timeout_seconds):
            async for event in events():
                if isinstance(event, module.AgentMessageDeltaNotification):
                    if event.threadId == thread_id and event.turnId == turn_id:
                        chunks.append(event.delta)
                elif (
                    isinstance(event, module.TurnCompletedNotification)
                    and event.threadId == thread_id
                    and getattr(event.turn, "id", None) == turn_id
                ):
                    if (
                        getattr(event.turn, "status", None) != "completed"
                        or getattr(event.turn, "error", None) is not None
                    ):
                        raise RuntimeError("Codex turn did not complete successfully")
                    settled = True
                    break
        if not settled:
            raise RuntimeError("Codex event stream ended before exact turn completion")
        return "".join(chunks)


class CodexAppServerBackend:
    """Project typed app-server completion into a proposal-only ReasoningResult."""

    def __init__(self, executor: CodexExecutor) -> None:
        if not isinstance(executor, CodexExecutor):
            raise TypeError("Codex backend requires a CodexExecutor")
        self._executor = executor

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        return reasoning_result_from_text(request, self._executor.complete(request))
