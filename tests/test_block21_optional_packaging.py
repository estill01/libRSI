from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from librsi.http.__main__ import main as http_main
from librsi.mcp.__main__ import main as mcp_main


def test_base_import_does_not_require_http_or_mcp_dependencies() -> None:
    project = Path(__file__).parents[1]
    script = """
import importlib.abc
import sys

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastapi', 'mcp', 'uvicorn'}:
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, BlockOptional())
import librsi
from librsi.service import LibRSIService
assert 'fastapi' not in sys.modules
assert 'mcp' not in sys.modules
assert 'uvicorn' not in sys.modules
print(LibRSIService.__name__)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(project / "src")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "LibRSIService"


def test_non_loopback_entrypoints_require_explicit_auth(monkeypatch, tmp_path) -> None:
    for name in (
        "LIBRSI_HTTP_READ_TOKEN",
        "LIBRSI_HTTP_MUTATE_TOKEN",
        "LIBRSI_HTTP_APPLY_TOKEN",
        "LIBRSI_MCP_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError, match="non-loopback HTTP"):
        http_main(["--data-dir", str(tmp_path), "--host", "0.0.0.0"])
    with pytest.raises(ValueError, match="non-loopback MCP"):
        mcp_main(
            [
                "--data-dir",
                str(tmp_path),
                "--transport",
                "streamable-http",
                "--host",
                "0.0.0.0",
            ]
        )
