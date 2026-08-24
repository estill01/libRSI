"""Exact internal handoffs for utils-backed conformance packages."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass(frozen=True, slots=True)
class SharedPackageHandoff:
    """Frozen producer and artifact identity for one internal package lane."""

    distribution: str
    import_root: str
    version: str
    producer_repository: str
    producer_revision: str
    accepted_source_commit: str
    package_tree_object: str
    wheel_sha256: str
    wheel_content_root_sha256: str
    runtime_content_root_sha256: str
    public_contracts: tuple[tuple[str, str], ...]
    runtime_files: tuple[str, ...]
    posture: str


@dataclass(frozen=True, slots=True)
class QualifiedPackageSet:
    """Frozen technical qualification shared by every mapped utility lane."""

    producer_revision: str
    qualification_matrix_sha256: str
    technical_qualification_root_sha256: str
    posture: str


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise RuntimeError(f"shared utility metadata has an invalid {label}")
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise RuntimeError(f"shared utility metadata has an invalid {label}")
    return text


def _git_oid(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise RuntimeError(f"shared utility metadata has an invalid {label}")
    return text


def _metadata() -> dict[str, Any]:
    try:
        document = json.loads(
            resources.files("librsi.conformance")
            .joinpath("shared-utilities.json")
            .read_text(encoding="utf-8")
        )
    except (OSError, TypeError, ValueError) as exc:
        raise RuntimeError("shared utility handoff metadata is unavailable") from exc
    if type(document) is not dict or set(document) != {
        "schema_version",
        "qualified_set",
        "packages",
        "librsi_adapter",
    }:
        raise RuntimeError("shared utility handoff metadata has an unexpected shape")
    if document["schema_version"] != 1:
        raise RuntimeError("shared utility handoff metadata has an unsupported schema")
    return document


def _package(document: dict[str, Any], distribution: str) -> SharedPackageHandoff:
    packages = document["packages"]
    if type(packages) is not dict or set(packages) != {
        "embedded-service-contract",
        "runtime-manifest",
    }:
        raise RuntimeError("shared utility package set is not exact")
    row = packages.get(distribution)
    if type(row) is not dict or set(row) != {
        "import_root",
        "version",
        "producer_repository",
        "producer_revision",
        "accepted_source_commit",
        "package_tree_object",
        "wheel_sha256",
        "wheel_content_root_sha256",
        "runtime_content_root_sha256",
        "public_contracts",
        "runtime_files",
        "posture",
    }:
        raise RuntimeError(f"shared utility package metadata is not exact: {distribution}")
    contracts = row["public_contracts"]
    files = row["runtime_files"]
    if (
        type(contracts) is not dict
        or not contracts
        or any(type(name) is not str for name in contracts)
        or type(files) is not list
        or not files
        or any(type(name) is not str for name in files)
    ):
        raise RuntimeError(f"shared utility package files are invalid: {distribution}")
    return SharedPackageHandoff(
        distribution=distribution,
        import_root=_text(row["import_root"], "import root"),
        version=_text(row["version"], "version"),
        producer_repository=_text(row["producer_repository"], "producer repository"),
        producer_revision=_git_oid(row["producer_revision"], "producer revision"),
        accepted_source_commit=_git_oid(row["accepted_source_commit"], "source commit"),
        package_tree_object=_text(row["package_tree_object"], "package tree object"),
        wheel_sha256=_sha256(row["wheel_sha256"], "wheel SHA-256"),
        wheel_content_root_sha256=_sha256(row["wheel_content_root_sha256"], "wheel content root"),
        runtime_content_root_sha256=_sha256(
            row["runtime_content_root_sha256"], "runtime content root"
        ),
        public_contracts=tuple(
            sorted(
                (name, _sha256(digest, f"{name} contract root"))
                for name, digest in contracts.items()
            )
        ),
        runtime_files=tuple(sorted(files)),
        posture=_text(row["posture"], "release posture"),
    )


_DOCUMENT = _metadata()
_QUALIFIED = _DOCUMENT["qualified_set"]
if type(_QUALIFIED) is not dict or set(_QUALIFIED) != {
    "producer_revision",
    "qualification_matrix_sha256",
    "technical_qualification_root_sha256",
    "posture",
}:
    raise RuntimeError("shared utility qualification metadata is not exact")

QUALIFIED_PACKAGE_SET = QualifiedPackageSet(
    producer_revision=_git_oid(_QUALIFIED["producer_revision"], "qualified producer revision"),
    qualification_matrix_sha256=_sha256(
        _QUALIFIED["qualification_matrix_sha256"], "qualification matrix root"
    ),
    technical_qualification_root_sha256=_sha256(
        _QUALIFIED["technical_qualification_root_sha256"], "technical qualification root"
    ),
    posture=_text(_QUALIFIED["posture"], "qualification posture"),
)
EMBEDDED_SERVICE_HANDOFF = _package(_DOCUMENT, "embedded-service-contract")
RUNTIME_MANIFEST_HANDOFF = _package(_DOCUMENT, "runtime-manifest")
SHARED_UTILITY_HANDOFFS = (EMBEDDED_SERVICE_HANDOFF, RUNTIME_MANIFEST_HANDOFF)


def _runtime_content_root(module: ModuleType, handoff: SharedPackageHandoff) -> str:
    origin = getattr(module, "__file__", None)
    if type(origin) is not str:
        raise RuntimeError(f"{handoff.distribution} has no stable filesystem origin")
    package = Path(origin).resolve().parent
    rows: list[dict[str, str | int]] = []
    for relative in handoff.runtime_files:
        path = package / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"{handoff.distribution} accepted runtime file is unavailable"
            ) from exc
        rows.append(
            {
                "path": f"{handoff.import_root}/{relative}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    payload = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_contracts(package: Path, handoff: SharedPackageHandoff) -> None:
    for relative, expected in handoff.public_contracts:
        path = package / "_contract" / relative
        try:
            observed = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise RuntimeError(f"{handoff.distribution} public contract is unavailable") from exc
        if observed != expected:
            raise RuntimeError(f"{handoff.distribution} public contract root has drifted")


def validate_shared_package(module: ModuleType, handoff: SharedPackageHandoff) -> None:
    """Fail closed unless one imported package is the exact accepted handoff."""

    if type(module) is not ModuleType:
        raise TypeError("shared utility validation requires an imported module")
    if module.__name__ != handoff.import_root:
        raise RuntimeError(f"{handoff.distribution} import root does not match its handoff")
    if sys.modules.get(handoff.import_root) is not module:
        raise RuntimeError(f"{handoff.distribution} is not the active imported module")
    if getattr(module, "__version__", None) != handoff.version:
        raise RuntimeError(f"{handoff.distribution} version does not match its handoff")
    origin = getattr(module, "__file__", None)
    if type(origin) is not str:
        raise RuntimeError(f"{handoff.distribution} has no stable filesystem origin")
    package = Path(origin).resolve().parent
    _validate_contracts(package, handoff)
    if _runtime_content_root(module, handoff) != handoff.runtime_content_root_sha256:
        raise RuntimeError(f"{handoff.distribution} runtime content root has drifted")
    contract_name = (
        "structural-contract.json" if handoff is EMBEDDED_SERVICE_HANDOFF else "public-api.json"
    )
    try:
        public_contract = json.loads(
            (package / "_contract" / contract_name).read_text(encoding="utf-8")
        )
        exports = public_contract["root_exports"]
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise RuntimeError(f"{handoff.distribution} public contract is malformed") from exc
    if (
        type(exports) is not list
        or any(type(name) is not str for name in exports)
        or tuple(sorted(getattr(module, "__all__", ()))) != tuple(sorted(exports))
        or any(not hasattr(module, name) for name in exports)
    ):
        raise RuntimeError(f"{handoff.distribution} public surface has drifted")


def load_shared_utilities() -> tuple[ModuleType, ModuleType]:
    """Import and validate both exact internal shared packages as one set."""

    lifecycle = importlib.import_module(EMBEDDED_SERVICE_HANDOFF.import_root)
    manifest = importlib.import_module(RUNTIME_MANIFEST_HANDOFF.import_root)
    validate_shared_package(lifecycle, EMBEDDED_SERVICE_HANDOFF)
    validate_shared_package(manifest, RUNTIME_MANIFEST_HANDOFF)
    return lifecycle, manifest


def librsi_adapter_contract() -> dict[str, Any]:
    """Return the frozen libRSI-owned adapter roots from the handoff document."""

    row = _DOCUMENT["librsi_adapter"]
    if type(row) is not dict or set(row) != {
        "content_root_sha256",
        "protocol_schema_root_sha256",
        "files",
    }:
        raise RuntimeError("libRSI shared-utility adapter metadata is not exact")
    files = row["files"]
    if type(files) is not list or not files or any(type(name) is not str for name in files):
        raise RuntimeError("libRSI shared-utility adapter file set is invalid")
    return {
        "content_root_sha256": _sha256(row["content_root_sha256"], "adapter root"),
        "protocol_schema_root_sha256": _sha256(
            row["protocol_schema_root_sha256"], "protocol schema root"
        ),
        "files": tuple(sorted(files)),
    }
