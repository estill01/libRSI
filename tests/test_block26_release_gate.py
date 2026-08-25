from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

import librsi
from tests.block26_release_audit import (
    ReleaseAuditError,
    validate_project_document,
    validate_public_exports,
    validate_public_texts,
    validate_requirements,
    validate_source_tree,
)

PROJECT = Path(__file__).parents[1]


def _project_document() -> dict[str, object]:
    with (PROJECT / "pyproject.toml").open("rb") as source:
        return tomllib.load(source)


def test_source_tree_metadata_exports_and_license_gate_are_exact() -> None:
    validate_source_tree(PROJECT, "pending")
    validate_public_exports(librsi)

    document = _project_document()
    project = document["project"]
    assert isinstance(project, dict)
    assert project["version"] == librsi.__version__ == "0.3.0"
    assert project["dependencies"] == []
    assert set(project["optional-dependencies"]) == {
        "dev",
        "mcp",
        "openai",
        "providers",
        "server",
        "service",
    }


@pytest.mark.parametrize(
    "requirement",
    (
        "codex-app-server-client @ git+https://github.com/estill01/utils.git@deadbeef",
        "embedded-service-contract==0.1.0",
        "runtime-manifest @ file:///tmp/internal.whl",
        "provider @ https://example.invalid/provider.whl",
    ),
)
def test_public_requirement_audit_rejects_internal_and_direct_dependencies(
    requirement: str,
) -> None:
    with pytest.raises(ReleaseAuditError, match="public metadata"):
        validate_requirements([requirement])


def test_project_audit_rejects_base_dependency_extra_and_version_drift() -> None:
    document = _project_document()

    with_base = copy.deepcopy(document)
    with_base["project"]["dependencies"] = ["requests>=2"]  # type: ignore[index]
    with pytest.raises(ReleaseAuditError, match="zero dependencies"):
        validate_project_document(with_base, "pending")

    with_codex = copy.deepcopy(document)
    with_codex["project"]["optional-dependencies"]["codex"] = []  # type: ignore[index]
    with pytest.raises(ReleaseAuditError, match="extras"):
        validate_project_document(with_codex, "pending")

    stale = copy.deepcopy(document)
    stale["project"]["version"] = "0.2.0"  # type: ignore[index]
    with pytest.raises(ReleaseAuditError, match="name/version"):
        validate_project_document(stale, "pending")


def test_license_gate_rejects_unselected_grant_and_wrong_selected_classifier() -> None:
    document = _project_document()
    unselected = copy.deepcopy(document)
    unselected["project"]["license"] = "MIT"  # type: ignore[index]
    with pytest.raises(ReleaseAuditError, match="license grant"):
        validate_project_document(unselected, "pending")

    selected = copy.deepcopy(document)
    selected["project"]["license"] = "MIT"  # type: ignore[index]
    with pytest.raises(ReleaseAuditError, match="classifier"):
        validate_project_document(selected, "MIT")


@pytest.mark.parametrize(
    "text, message",
    (
        ('pip install "librsi @ git+https://github.com/estill01/libRSI.git@v0.2.0"', "stale"),
        ("pip install 'libRSI[codex]'", "public extra"),
        (
            "dependency = 'git+https://github.com/estill01/utils.git@deadbeef'",
            "internal utility",
        ),
    ),
)
def test_public_text_audit_rejects_stale_or_internal_install_claims(
    text: str, message: str
) -> None:
    with pytest.raises(ReleaseAuditError, match=message):
        validate_public_texts({"example": text})


def test_export_audit_rejects_duplicate_missing_and_nonfacade_surfaces() -> None:
    duplicate = ModuleType("duplicate")
    duplicate.__all__ = ["LibRSI", "LibRSI"]
    duplicate.LibRSI = object()
    with pytest.raises(ReleaseAuditError, match="duplicate"):
        validate_public_exports(duplicate)

    missing = ModuleType("missing")
    missing.__all__ = sorted(
        {"LibRSI", "LibRSIRun", "WorkflowRequest", "HypothesisTestResult", "Gone"}
    )
    missing.LibRSI = missing.LibRSIRun = missing.WorkflowRequest = missing.HypothesisTestResult = (
        object()
    )
    with pytest.raises(ReleaseAuditError, match="missing attributes"):
        validate_public_exports(missing)


def test_optional_entrypoint_help_imports_without_optional_stacks() -> None:
    script = r"""
import importlib.abc
import json
import sys

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastapi', 'mcp', 'uvicorn'}:
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, BlockOptional())
from librsi.http.__main__ import _parser as http_parser
from librsi.mcp.__main__ import _parser as mcp_parser
assert not ({'fastapi', 'mcp', 'uvicorn'} & set(sys.modules))
for parser in (http_parser(), mcp_parser()):
    try:
        parser.parse_args(['--help'])
    except SystemExit as exc:
        assert exc.code == 0
print(json.dumps(sorted({'fastapi', 'mcp', 'uvicorn'} & set(sys.modules))))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT / "src")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == []


def test_examples_are_syntax_valid_and_use_only_public_core_imports() -> None:
    for relative in ("examples/local_validation.py", "examples/local_hypothesis.py"):
        source = (PROJECT / relative).read_text(encoding="utf-8")
        compile(source, relative, "exec")
        assert "from librsi import" in source
        assert all(name not in source for name in ("codex_app_server_client", "runtime_manifest"))
