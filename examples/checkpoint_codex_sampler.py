"""Persist bounded, resumable Astra requests, including explicit timeout attempts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from threading import Lock
from typing import Any

from llm_search import CodexSampler

from librsi.identity import digest


class CheckpointSampler(CodexSampler):
    def __init__(self, directory, *, logical_limit=518, retry_limit=8):
        self.logical_limit = logical_limit
        self.retry_limit = retry_limit
        self.history_lock = Lock()
        self.history: dict[str, list[dict[str, Any]]] = {}
        directory = Path(directory)
        if not directory.exists():
            super().__init__(
                directory,
                "gpt-6-astra",
                max_calls=logical_limit + retry_limit,
                reasoning_effort="high",
                timeout_seconds=600,
            )
        else:
            self.directory = directory
            self.model = "gpt-6-astra"
            self.reasoning_effort = "high"
            self.timeout_seconds = 600
            self.max_calls = logical_limit + retry_limit
            self._lock = Lock()
            self.version = subprocess.check_output(["codex", "--version"], text=True).strip()
            self.instructions = directory / "instructions.txt"
            assert self.instructions.is_file()
            self.receipts = []
            for number, path in enumerate(sorted(directory.glob("[0-9][0-9][0-9]")), 1):
                receipt = json.loads((path / "receipt.json").read_text())
                assert receipt["number"] == number and path.name == f"{number:03d}"
                if "returncode" not in receipt and receipt.get("status") != "timeout":
                    raise RuntimeError(f"Incomplete provider request requires diagnosis: {path}")
                self.receipts.append(receipt)
                self.history.setdefault(receipt["role"], []).append(receipt)
        self.roles = set(self.history)
        self.extra_attempts = sum(len(rows) - 1 for rows in self.history.values())
        assert len(self.roles) <= self.logical_limit and self.extra_attempts <= self.retry_limit

    def _record_attempts(self, role):
        with self.history_lock:
            self.history[role] = [r for r in self.receipts if r.get("role") == role]

    def _attempt(self, prompt, *, field, role, count):
        try:
            return super().call(prompt, field=field, role=role, count=count)
        except ValueError as error:
            receipt = [r for r in self.receipts if r.get("role") == role][-1]
            path = self.directory / f"{receipt['number']:03d}" / "invalid-output.json"
            path.write_text(json.dumps({"error": str(error)}) + "\n")
            raise

    def call(self, prompt, *, field, role, count=2):
        with self.history_lock:
            previous = list(self.history.get(role, []))
            if role not in self.roles:
                if len(self.roles) >= self.logical_limit:
                    raise RuntimeError("logical model-call limit exhausted")
                self.roles.add(role)
        if previous:
            for receipt in previous:
                path = self.directory / f"{receipt['number']:03d}"
                assert receipt["prompt_sha256"] == digest(prompt)
                assert (path / "prompt.txt").read_text() == prompt
                assert receipt["model"] == self.model and receipt["reasoning_effort"] == "high"
                assert receipt["candidate_count"] == count
            latest = previous[-1]
            path = self.directory / f"{latest['number']:03d}"
            if latest.get("returncode") == 0:
                assert latest["tool_items"] == 0 and len(latest["usage"]) == 1
                if not (path / "response.json").exists():
                    invalid = json.loads((path / "invalid-output.json").read_text())
                    raise ValueError(invalid["error"])
                choices = json.loads((path / "response.json").read_text())["candidates"]
                assert len(choices) == count
                assert all(set(c["configuration"]) == {field} for c in choices)
                return choices
            if latest.get("status") != "timeout" or len(previous) != 1:
                raise RuntimeError(f"Failed provider request requires diagnosis: {path}")
        else:
            try:
                return self._attempt(prompt, field=field, role=role, count=count)
            except subprocess.TimeoutExpired:
                pass
            finally:
                self._record_attempts(role)
        # Only a timeout without a response can receive the registered one retry.
        failed = self.history[role][-1]
        assert failed.get("status") == "timeout" and not failed.get("usage")
        assert not (self.directory / f"{failed['number']:03d}" / "response.json").exists()
        with self.history_lock:
            if self.extra_attempts >= self.retry_limit:
                raise RuntimeError("registered transport retry allowance exhausted")
            self.extra_attempts += 1
        try:
            return self._attempt(prompt, field=field, role=role, count=count)
        finally:
            self._record_attempts(role)
