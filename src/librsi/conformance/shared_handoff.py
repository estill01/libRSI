"""Exact internal handoffs for utils-backed conformance packages."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import dataclass
from importlib import resources
from importlib.machinery import ModuleSpec, SourceFileLoader
from pathlib import Path
from types import ModuleType
from typing import Any

from .behavior import module_behavior_root
from .source_loader import CanonicalSourcePackage, execute_source_package

_OPERATIONAL_EXPORT_OWNERS = {
    "embedded_service_contract": {
        "contract": (
            "CancelResult",
            "Cancelled",
            "EventRecord",
            "Failed",
            "HostContract",
            "HostShape",
            "InvalidCursorError",
            "LifecycleContractError",
            "LifecycleHost",
            "RunRef",
            "RunState",
            "RunStatus",
            "Succeeded",
            "UnknownRunError",
        ),
        "conformance": (
            "ConformanceError",
            "ConformanceFixture",
            "ConformanceReport",
            "assert_lifecycle_conformance",
        ),
    },
    "runtime_manifest": {
        "model": (
            "Capability",
            "CompatibilityReport",
            "Component",
            "ManifestDecodeError",
            "ManifestError",
            "ManifestValidationError",
            "Protocol",
            "RuntimeManifest",
            "Sha256Root",
            "UnavailableKind",
            "UnavailableReason",
            "UnsupportedSchemaError",
        ),
        "compatibility": ("compare_manifests",),
        "serialization": ("canonical_json", "parse_manifest"),
    },
}


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

_CANONICAL_PACKAGES: dict[str, CanonicalSourcePackage] = {}


def _runtime_content_root(module: ModuleType, handoff: SharedPackageHandoff) -> str:
    origin = getattr(module, "__file__", None)
    if type(origin) is not str:
        raise RuntimeError(f"{handoff.distribution} has no stable filesystem origin")
    package = Path(origin).resolve().parent
    return _package_runtime_content_root(package, handoff)


def _package_runtime_content_root(package: Path, handoff: SharedPackageHandoff) -> str:
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


def _validate_source_module(module: ModuleType, expected: Path, distribution: str) -> None:
    spec = getattr(module, "__spec__", None)
    loader = getattr(module, "__loader__", None)
    if type(spec) is not ModuleSpec or type(loader) is not SourceFileLoader:
        raise RuntimeError(f"{distribution} source loader is not exact")
    if (
        spec.loader is not loader
        or spec.name != module.__name__
        or loader.name != module.__name__
        or spec.origin is None
        or Path(spec.origin).resolve() != expected
        or Path(loader.path).resolve() != expected
        or spec.has_location is not True
    ):
        raise RuntimeError(f"{distribution} source loader identity has drifted")
    try:
        source = loader.get_data(str(expected))
        installed = expected.read_bytes()
    except OSError as exc:
        raise RuntimeError(f"{distribution} exact source is unavailable") from exc
    if source != installed:
        raise RuntimeError(f"{distribution} source loader bytes have drifted")


def _validate_export_owners(
    module: ModuleType,
    package: Path,
    handoff: SharedPackageHandoff,
    package_source: CanonicalSourcePackage,
) -> None:
    owners = _OPERATIONAL_EXPORT_OWNERS.get(handoff.import_root)
    if owners is None:
        raise RuntimeError(f"{handoff.distribution} has no accepted export-owner map")
    expected_names = {name for names in owners.values() for name in names}
    if expected_names != set(module.__all__) - {"__version__"}:
        raise RuntimeError(f"{handoff.distribution} export-owner map has drifted")
    for relative_module, names in owners.items():
        owner_name = f"{module.__name__}.{relative_module}"
        owner = package_source.modules.get(owner_name)
        if type(owner) is not ModuleType:
            raise RuntimeError(f"{handoff.distribution} export owner was not source-loaded")
        origin = getattr(owner, "__file__", None)
        expected = package / f"{relative_module}.py"
        if type(origin) is not str or Path(origin).resolve() != expected:
            raise RuntimeError(f"{handoff.distribution} export owner source has drifted")
        _validate_source_module(owner, expected, handoff.distribution)
        for name in names:
            root_object = getattr(module, name, None)
            owner_object = getattr(owner, name, None)
            if (
                root_object is not owner_object
                or root_object is not package_source.namespaces[module.__name__].get(name)
                or owner_object is not package_source.namespaces[owner_name].get(name)
                or getattr(root_object, "__module__", None) != owner_name
            ):
                raise RuntimeError(f"{handoff.distribution} operational export owner has drifted")


def _validate_canonical_package(
    package_source: CanonicalSourcePackage,
    handoff: SharedPackageHandoff,
) -> None:
    module = package_source.root
    package = package_source.package
    if package_source.import_root != handoff.import_root:
        raise RuntimeError(f"{handoff.distribution} import root does not match its handoff")
    if getattr(module, "__version__", None) != handoff.version:
        raise RuntimeError(f"{handoff.distribution} version does not match its handoff")
    origin = getattr(module, "__file__", None)
    if type(origin) is not str or Path(origin).resolve() != package / "__init__.py":
        raise RuntimeError(f"{handoff.distribution} has no stable filesystem origin")
    _validate_source_module(module, package / "__init__.py", handoff.distribution)
    if set(package_source.modules) != set(package_source.behavior_roots):
        raise RuntimeError(f"{handoff.distribution} executed behavior module set has drifted")
    for name, owned in package_source.modules.items():
        if module_behavior_root(owned) != package_source.behavior_roots[name]:
            raise RuntimeError(f"{handoff.distribution} executed behavior root has drifted: {name}")
    _validate_contracts(package, handoff)
    if _package_runtime_content_root(package, handoff) != handoff.runtime_content_root_sha256:
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
    _validate_export_owners(module, package, handoff, package_source)


def _installed_package_path(handoff: SharedPackageHandoff) -> Path:
    try:
        distribution = importlib.metadata.distribution(handoff.distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ModuleNotFoundError(f"mapped {handoff.distribution} lane is unavailable") from exc
    if distribution.version != handoff.version:
        raise RuntimeError(f"{handoff.distribution} installed version has drifted")
    package = Path(str(distribution.locate_file(handoff.import_root))).resolve()
    if not package.is_dir():
        raise ModuleNotFoundError(f"mapped {handoff.distribution} lane is unavailable")
    return package


def _canonical_package(handoff: SharedPackageHandoff) -> CanonicalSourcePackage:
    package_source = _CANONICAL_PACKAGES.get(handoff.import_root)
    if package_source is None:
        package = _installed_package_path(handoff)
        _validate_contracts(package, handoff)
        if _package_runtime_content_root(package, handoff) != handoff.runtime_content_root_sha256:
            raise RuntimeError(f"{handoff.distribution} runtime content root has drifted")
        package_source = execute_source_package(handoff.import_root, package)
        _CANONICAL_PACKAGES[handoff.import_root] = package_source
    _validate_canonical_package(package_source, handoff)
    return package_source


def validate_shared_package(module: ModuleType, handoff: SharedPackageHandoff) -> None:
    """Fail closed unless a module is the libRSI-loaded exact accepted handoff."""

    if type(module) is not ModuleType:
        raise TypeError("shared utility validation requires an imported module")
    package_source = _canonical_package(handoff)
    if module is not package_source.root:
        raise RuntimeError(f"{handoff.distribution} is not the canonical loaded module")


def load_shared_utilities() -> tuple[ModuleType, ModuleType]:
    """Import and validate both exact internal shared packages as one set."""

    lifecycle = _canonical_package(EMBEDDED_SERVICE_HANDOFF).root
    manifest = _canonical_package(RUNTIME_MANIFEST_HANDOFF).root
    return lifecycle, manifest
