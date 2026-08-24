"""Descriptive runtime-manifest projection for the exact qualified package set."""

from __future__ import annotations

import hashlib
import importlib
import json
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..providers import CODEX_CLIENT_HANDOFF, validate_codex_client
from .shared_handoff import (
    EMBEDDED_SERVICE_HANDOFF,
    RUNTIME_MANIFEST_HANDOFF,
    load_shared_utilities,
)

if TYPE_CHECKING:
    from runtime_manifest import (  # type: ignore[import-untyped]
        Capability,
        Component,
        Protocol,
        RuntimeManifest,
        Sha256Root,
    )
else:
    _, _manifest_api = load_shared_utilities()
    Capability = _manifest_api.Capability
    Component = _manifest_api.Component
    Protocol = _manifest_api.Protocol
    RuntimeManifest = _manifest_api.RuntimeManifest
    Sha256Root = _manifest_api.Sha256Root

ADAPTER_RUNTIME_FILES = (
    "__init__.py",
    "lifecycle.py",
    "manifest.py",
    "shared-utilities.json",
    "shared_handoff.py",
    "source_loader.py",
)


def _content_root(package: Path, files: tuple[str, ...]) -> str:
    rows: list[dict[str, str | int]] = []
    for relative in files:
        path = package / relative
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise RuntimeError("libRSI shared-utility adapter file is unavailable") from exc
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    payload = (json.dumps(rows, sort_keys=True, separators=(",", ":")) + "\n").encode()
    return hashlib.sha256(payload).hexdigest()


def _adapter_root() -> tuple[str, str]:
    package = Path(str(resources.files("librsi.conformance")))
    observed = _content_root(package, ADAPTER_RUNTIME_FILES)
    schema = Path(__file__).parents[1] / "protocol" / "schemas.py"
    try:
        schema_root = hashlib.sha256(schema.read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeError("libRSI external protocol schema is unavailable") from exc
    return observed, schema_root


def build_runtime_manifest() -> RuntimeManifest:
    """Describe exact components and roots without deciding capability or authority."""

    load_shared_utilities()
    client = importlib.import_module("codex_app_server_client")
    validate_codex_client(client)
    adapter_root, protocol_schema_root = _adapter_root()
    return RuntimeManifest(
        component=Component("librsi", "0.2.0", Sha256Root(adapter_root)),
        protocols=(
            Protocol(
                "embedded-service-lifecycle",
                "1",
                Sha256Root(
                    dict(EMBEDDED_SERVICE_HANDOFF.public_contracts)["structural-contract.json"]
                ),
                ("cancel", "embedded", "events", "service", "status"),
            ),
            Protocol(
                "librsi-external-agent",
                "1",
                Sha256Root(protocol_schema_root),
                ("managed", "resume", "typed-outcome"),
            ),
        ),
        capabilities=tuple(
            Capability(name, "1")
            for name in (
                "external-control",
                "improvement",
                "investigation",
                "managed-service",
                "rsi",
                "validation",
            )
        ),
        dependencies=(
            Component(
                "codex-app-server-client",
                CODEX_CLIENT_HANDOFF.version,
                Sha256Root(CODEX_CLIENT_HANDOFF.content_root_sha256),
            ),
            Component(
                EMBEDDED_SERVICE_HANDOFF.distribution,
                EMBEDDED_SERVICE_HANDOFF.version,
                Sha256Root(EMBEDDED_SERVICE_HANDOFF.wheel_content_root_sha256),
            ),
            Component(
                RUNTIME_MANIFEST_HANDOFF.distribution,
                RUNTIME_MANIFEST_HANDOFF.version,
                Sha256Root(RUNTIME_MANIFEST_HANDOFF.wheel_content_root_sha256),
            ),
        ),
    )


def runtime_manifest_document() -> str:
    """Return the canonical descriptive document from the accepted package API."""

    _, manifest_api = load_shared_utilities()
    canonical_json = manifest_api.canonical_json
    return canonical_json(build_runtime_manifest())


def compare_runtime_description(observed: RuntimeManifest) -> Any:
    """Return diagnostics only; callers must not interpret them as authority."""

    if type(observed) is not RuntimeManifest:
        raise TypeError("runtime description comparison requires RuntimeManifest")
    _, manifest_api = load_shared_utilities()
    compare_manifests = manifest_api.compare_manifests
    return compare_manifests(build_runtime_manifest(), observed)
