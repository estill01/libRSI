"""Optional OpenAI Responses API adapter for typed libRSI reasoning tasks."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from ..reasoning import ReasoningRequest, ReasoningResult
from .prompt import reasoning_prompt, reasoning_result_from_text


@dataclass(frozen=True, slots=True)
class OpenAIResponsesConfig:
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("OpenAI model is required")
        object.__setattr__(self, "model", self.model.strip())


class OpenAIResponsesBackend:
    """Use the maintained Responses API without placing provider state in records."""

    def __init__(self, config: OpenAIResponsesConfig, *, client: object | None = None) -> None:
        if not isinstance(config, OpenAIResponsesConfig):
            raise TypeError("OpenAI backend requires OpenAIResponsesConfig")
        self._config = config
        self._client = client

    def _resolve_client(self) -> object:
        if self._client is not None:
            return self._client
        try:
            module = importlib.import_module("openai")
        except ImportError as exc:
            raise RuntimeError("install libRSI[openai] to use the OpenAI adapter") from exc
        constructor = getattr(module, "OpenAI", None)
        if not callable(constructor):
            raise RuntimeError("installed OpenAI SDK does not expose OpenAI")
        return constructor()

    def respond(self, request: ReasoningRequest) -> ReasoningResult:
        client: Any = self._resolve_client()
        responses = getattr(client, "responses", None)
        create = getattr(responses, "create", None)
        if not callable(create):
            raise TypeError("OpenAI client must expose responses.create")
        response = create(model=self._config.model, input=reasoning_prompt(request))
        status = getattr(response, "status", None)
        if (
            type(status) is not str
            or status != "completed"
            or getattr(response, "error", None) is not None
            or getattr(response, "incomplete_details", None) is not None
        ):
            raise RuntimeError("OpenAI response did not complete successfully")
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str):
            raise TypeError("OpenAI response must expose output_text")
        return reasoning_result_from_text(request, output_text)
