"""Deterministic provider prompt and response projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..reasoning import ReasoningRequest, ReasoningResult

_MAX_PROVIDER_RESPONSE_BYTES = 2 * 1024 * 1024


def reasoning_prompt(request: ReasoningRequest) -> str:
    if not isinstance(request, ReasoningRequest):
        raise TypeError("provider prompt requires a ReasoningRequest")
    envelope = {
        "task": request.to_dict(),
        "response_contract": {
            "content": "exact libRSI structured content for task.kind",
            "narration": "optional proposal-only explanation",
        },
        "authority": (
            "Return a proposal only. Do not claim truth, evidence, selection, application, "
            "verification, or acceptance authority. Return one JSON object and no markdown."
        ),
    }
    return json.dumps(envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def reasoning_result_from_text(request: ReasoningRequest, text: str) -> ReasoningResult:
    if not isinstance(request, ReasoningRequest):
        raise TypeError("provider response requires a ReasoningRequest")
    if not isinstance(text, str):
        raise TypeError("provider response must be text")
    encoded = text.encode("utf-8")
    if not encoded or len(encoded) > _MAX_PROVIDER_RESPONSE_BYTES:
        raise ValueError("provider response is empty or exceeds the bounded response size")
    try:
        document: Any = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ValueError("provider response must be one JSON object") from exc
    if not isinstance(document, Mapping) or any(not isinstance(key, str) for key in document):
        raise TypeError("provider response must be a string-keyed JSON object")
    unexpected = frozenset(document) - {"content", "narration"}
    if unexpected or "content" not in document:
        raise ValueError("provider response has unsupported or missing fields")
    content = document["content"]
    narration = document.get("narration")
    if not isinstance(content, Mapping):
        raise TypeError("provider response content must be an object")
    if narration is not None and not isinstance(narration, str):
        raise TypeError("provider response narration must be text or null")
    return ReasoningResult.propose(request=request, content=content, narration=narration)
