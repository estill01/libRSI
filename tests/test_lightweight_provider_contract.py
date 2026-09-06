from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from librsi import REASONING_KINDS
from librsi.providers import OpenAIResponsesBackend, OpenAIResponsesConfig
from librsi.providers.prompt import reasoning_prompt, reasoning_result_from_text
from librsi.reasoning.schemas import REASONING_CONTENT_GUIDANCE
from tests.test_block9_reasoning_records import VALID_CONTENT, _context


@pytest.mark.parametrize("kind", sorted(REASONING_KINDS))
def test_kind_contract_is_supplied_and_valid_output_still_passes(kind) -> None:
    _, _, request = _context(kind)
    content = VALID_CONTENT[kind]
    guidance = json.loads(reasoning_prompt(request))["response_contract"]
    assert set(REASONING_CONTENT_GUIDANCE) == REASONING_KINDS
    for key, value in content.items():
        assert f'"{key}"' in guidance["content"]
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    assert all(f'"{field}"' in guidance["content"] for field in item)
    assert "required" in guidance["content_rules"]

    def respond(**kwargs):
        assert kwargs == {"model": "offline", "input": reasoning_prompt(request)}
        return SimpleNamespace(
            status="completed",
            error=None,
            incomplete_details=None,
            output_text=json.dumps({"content": content}),
        )

    backend = OpenAIResponsesBackend(
        OpenAIResponsesConfig("offline"),
        client=SimpleNamespace(responses=SimpleNamespace(create=respond)),
    )
    assert backend.respond(request).request == request
    for key in content:
        missing = {name: value for name, value in content.items() if name != key}
        with pytest.raises(ValueError, match="missing fields"):
            reasoning_result_from_text(request, json.dumps({"content": missing}))
    with pytest.raises(ValueError, match="unsupported fields"):
        reasoning_result_from_text(request, json.dumps({"content": {**content, "accepted": True}}))
