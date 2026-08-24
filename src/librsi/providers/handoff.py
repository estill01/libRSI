"""Exact internal handoff for the accepted utils app-server client."""

from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType


@dataclass(frozen=True, slots=True)
class CodexClientHandoff:
    distribution: str
    version: str
    producer_repository: str
    producer_source_commit: str
    qualification_commit: str
    wheel_sha256: str
    content_root_sha256: str
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
    producer_source_commit="08c416da4202b7036110e33e43d34ea590054e2e",
    qualification_commit="7f1674aa31dd64a1621bf1a746ba78e8f4c51305",
    wheel_sha256="1e9dc5b9c7f2edb9676b5a47eb2c9b96498f1b429acec474cd26702fe8e3fdb9",
    content_root_sha256="6ecc26e75197d06682fe9d8d0612edb1e56ead6d04c3a41cde1132e2618efd8f",
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


def validate_codex_client(module: ModuleType) -> None:
    """Fail closed unless the imported client matches the accepted protocol handoff."""

    if not isinstance(module, ModuleType):
        raise TypeError("Codex client must be an imported module")
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
    if observed != expected or len(getattr(module, "__all__", ())) != 92:
        raise RuntimeError("Codex client protocol surface does not match the accepted handoff")
