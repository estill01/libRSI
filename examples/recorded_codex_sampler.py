"""Reuse exact, completed model responses without substituting measured outcomes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from llm_search import CodexSampler

from librsi.identity import canonical_json, digest


class RecordedCodexSampler(CodexSampler):
    def __init__(self, directory, model, *, reuse=None, **kwargs):
        super().__init__(directory, model, **kwargs)
        self.reuse = reuse
        self.replays: dict[str, tuple[Path, dict[str, Any]]] = {}
        if reuse is not None:
            for path in sorted((reuse / "model-calls").glob("*/receipt.json")):
                receipt = json.loads(path.read_text())
                if receipt.get("returncode") != 0 or not (path.parent / "response.json").exists():
                    continue
                if receipt["role"] in self.replays:
                    raise ValueError("duplicate recorded model role")
                self.replays[receipt["role"]] = (path.parent, receipt)

    def call(self, prompt, *, field, role, count=2):
        if role not in self.replays:
            return super().call(prompt, field=field, role=role, count=count)
        source, original = self.replays[role]
        if (
            original["model"] != self.model
            or original["reasoning_effort"] != self.reasoning_effort
            or original["prompt_sha256"] != digest(prompt)
            or original["candidate_count"] != count
            or original["tool_items"] != 0
            or len(original["usage"]) != 1
            or (source / "prompt.txt").read_text() != prompt
        ):
            raise ValueError("recorded model response does not match the exact request")
        response = json.loads((source / "response.json").read_text())
        choices = response["candidates"]
        if len(choices) != count or any(set(c["configuration"]) != {field} for c in choices):
            raise ValueError("recorded response schema differs from current request")
        with self._lock:
            if len(self.receipts) >= self.max_calls:
                raise RuntimeError("model-call budget exhausted")
            if any(r["role"] == role for r in self.receipts):
                raise ValueError("model role was already consumed")
            number = len(self.receipts) + 1
            receipt = {
                **original,
                "number": number,
                "reused_from": {
                    "run": self.reuse.name,
                    "number": original["number"],
                    "original_receipt_sha256": digest(original),
                },
            }
            self.receipts.append(receipt)
        destination = self.directory / f"{number:03d}"
        shutil.copytree(source, destination)
        (destination / "receipt.json").write_text(canonical_json(receipt) + "\n")
        print(
            f"Recorded model call {number}: {role}; exact response reused, zero new provider calls",
            flush=True,
        )
        return choices

    def prior_generation_seconds(self):
        if self.reuse is None:
            return 0.0
        from datetime import datetime

        protocol = json.loads((self.reuse / "protocol.json").read_text())
        start = datetime.fromisoformat(protocol["created_at"]).timestamp()
        used = [
            source / "receipt.json"
            for role, (source, _) in self.replays.items()
            if any(r["role"] == role and "reused_from" in r for r in self.receipts)
        ]
        return max((p.stat().st_mtime - start for p in used), default=0.0)
