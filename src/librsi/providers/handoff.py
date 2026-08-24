"""Exact internal handoff for the accepted utils app-server client."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType


@dataclass(frozen=True, slots=True)
class CodexClientHandoff:
    distribution: str
    version: str
    producer_repository: str
    producer_revision: str
    package_source_commit: str
    qualification_commit: str
    qualification_matrix_sha256: str
    technical_qualification_root_sha256: str
    wheel_sha256: str
    content_root_sha256: str
    runtime_content_root_sha256: str
    public_api_sha256: str
    compatibility_fixture_sha256: str
    codex_version: str
    codex_source_commit: str
    schema_root_sha256: str
    selected_surface_root_sha256: str
    posture: str


CODEX_CLIENT_HANDOFF = CodexClientHandoff(
    distribution="codex-app-server-client",
    version="0.1.0",
    producer_repository="https://github.com/estill01/utils",
    producer_revision="a5659745a7cbcbb002b5f06051f6ed9826f721a7",
    package_source_commit="08c416da4202b7036110e33e43d34ea590054e2e",
    qualification_commit="7f1674aa31dd64a1621bf1a746ba78e8f4c51305",
    qualification_matrix_sha256=(
        "0888bed363b63842c37baa8187c9883cdddff73d936596e497e4e013341cd849"
    ),
    technical_qualification_root_sha256=(
        "9ab96149f63a45429a44ae07e309b68bb4204b4e2e6f4da6a7a93acbd5547068"
    ),
    wheel_sha256="1e9dc5b9c7f2edb9676b5a47eb2c9b96498f1b429acec474cd26702fe8e3fdb9",
    content_root_sha256="6ecc26e75197d06682fe9d8d0612edb1e56ead6d04c3a41cde1132e2618efd8f",
    runtime_content_root_sha256=(
        "23e66af500090eb176206a50bfafa60e332f11cbd073849a43e5461a96cd602a"
    ),
    public_api_sha256="7a032cfe32425aae9166217bae18e59202afe509a465e34c8c74794b6b1fdf93",
    compatibility_fixture_sha256=(
        "82e97c4564c04790d03750397d65b6989df529fbb21aedc14ae67cf96d759651"
    ),
    codex_version="0.147.0",
    codex_source_commit="be6e8eac029b183056b7e4402879f15d2c85f61b",
    schema_root_sha256="eb325d394d19f2f8d133203885b3d1c2f74dbc5a176f22078a4f99aae5926faa",
    selected_surface_root_sha256=(
        "9a773e75f2e5aa827b4cc711345bd9ca1bc2a037f19d114284a04f306097a42f"
    ),
    posture="no-license-selected/unpublished",
)


def _protocol_root(module: ModuleType) -> Path:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise RuntimeError("Codex client module has no stable filesystem origin")
    package = Path(origin).resolve().parent
    installed = package / "_protocol"
    development = package.parents[1] / "protocol" if len(package.parents) > 1 else installed
    root = installed if installed.is_dir() else development
    if not root.is_dir():
        raise RuntimeError("Codex client protocol artifacts are unavailable")
    return root


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeError("Codex client protocol artifact is unavailable") from exc


def _runtime_content_root(module: ModuleType, protocol_root: Path) -> str:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise RuntimeError("Codex client module has no stable filesystem origin")
    package = Path(origin).resolve().parent
    entries: list[dict[str, str | int]] = []
    for path in sorted(package.glob("*.py")):
        data = path.read_bytes()
        entries.append(
            {
                "path": f"codex_app_server_client/{path.name}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    for path in sorted(item for item in protocol_root.rglob("*") if item.is_file()):
        data = path.read_bytes()
        relative = path.relative_to(protocol_root).as_posix()
        entries.append(
            {
                "path": f"codex_app_server_client/_protocol/{relative}",
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    payload = (
        json.dumps(
            sorted(entries, key=lambda item: str(item["path"])),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _validate_operational_exports(module: ModuleType) -> None:
    origin = getattr(module, "__file__", None)
    if not isinstance(origin, str):
        raise RuntimeError("Codex client module has no stable filesystem origin")
    package = Path(origin).resolve().parent
    if sys.modules.get("codex_app_server_client") is not module:
        raise RuntimeError("Codex client root is not the active imported module")
    expected = {
        "resolve_codex_binary": ("codex_app_server_client.compatibility", "compatibility.py"),
        "inspect_compatibility": ("codex_app_server_client.compatibility", "compatibility.py"),
        "AppServerClient": ("codex_app_server_client.session", "session.py"),
        "AppServerSession": ("codex_app_server_client.session", "session.py"),
        "StdioTransport": ("codex_app_server_client.transport", "transport.py"),
        "ClientIdentity": ("codex_app_server_client.models", "models.py"),
        "ThreadStartParams": ("codex_app_server_client.models", "models.py"),
        "TurnStartParams": ("codex_app_server_client.models", "models.py"),
        "AgentMessageDeltaNotification": ("codex_app_server_client.models", "models.py"),
        "TurnCompletedNotification": ("codex_app_server_client.models", "models.py"),
    }
    for name, (owner, filename) in expected.items():
        implementation = getattr(module, name, None)
        owner_module = importlib.import_module(owner)
        source = getattr(owner_module, "__file__", None)
        if (
            implementation is not getattr(owner_module, name, None)
            or not isinstance(source, str)
            or Path(source).resolve() != package / filename
        ):
            raise RuntimeError(f"Codex client operational export is not exact: {name}")


def validate_codex_client(module: ModuleType) -> None:
    """Fail closed unless the imported client matches the accepted protocol handoff."""

    if not isinstance(module, ModuleType):
        raise TypeError("Codex client must be an imported module")
    if module.__name__ != "codex_app_server_client":
        raise RuntimeError("Codex client import root does not match the accepted handoff")
    if getattr(module, "__version__", None) != CODEX_CLIENT_HANDOFF.version:
        raise RuntimeError("Codex client version does not match the accepted handoff")
    target = getattr(module, "PINNED_PROTOCOL", None)
    observed = (
        getattr(target, "codex_version", None),
        getattr(target, "source_commit", None),
        getattr(target, "schema_tree_root_sha256", None),
        getattr(target, "selected_surface_root_sha256", None),
    )
    expected = (
        CODEX_CLIENT_HANDOFF.codex_version,
        CODEX_CLIENT_HANDOFF.codex_source_commit,
        CODEX_CLIENT_HANDOFF.schema_root_sha256,
        CODEX_CLIENT_HANDOFF.selected_surface_root_sha256,
    )
    root = _protocol_root(module)
    if _runtime_content_root(module, root) != CODEX_CLIENT_HANDOFF.runtime_content_root_sha256:
        raise RuntimeError("Codex client implementation root does not match the accepted handoff")
    _validate_operational_exports(module)
    compatibility = root / "compatibility.json"
    public_api = root / "public-api.json"
    if (
        _sha256(compatibility) != CODEX_CLIENT_HANDOFF.compatibility_fixture_sha256
        or _sha256(public_api) != CODEX_CLIENT_HANDOFF.public_api_sha256
    ):
        raise RuntimeError("Codex client artifact hashes do not match the accepted handoff")
    try:
        document = json.loads(public_api.read_text(encoding="utf-8"))
        exports = document["root_exports"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Codex client public API fixture is malformed") from exc
    if (
        observed != expected
        or not isinstance(exports, list)
        or any(not isinstance(item, str) for item in exports)
        or tuple(sorted(getattr(module, "__all__", ()))) != tuple(sorted(exports))
        or any(not hasattr(module, item) for item in exports)
    ):
        raise RuntimeError("Codex client protocol surface does not match the accepted handoff")
