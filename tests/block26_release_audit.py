"""Exact source and distribution audit for the Block 26 release gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, NoReturn

ReleaseLicense = Literal["pending", "MIT", "Apache-2.0", "no-license"]

EXPECTED_VERSION = "0.3.0"
INTERNAL_DISTRIBUTIONS = (
    "codex-app-server-client",
    "embedded-service-contract",
    "runtime-manifest",
)
INTERNAL_IMPORT_ROOTS = (
    "codex_app_server_client",
    "embedded_service_contract",
    "runtime_manifest",
)
PUBLIC_EXTRAS = {"dev", "mcp", "openai", "providers", "server", "service"}
PUBLIC_SCRIPTS = {
    "librsi": "librsi.cli.main:entrypoint",
    "librsi-http": "librsi.http.__main__:entrypoint",
    "librsi-mcp": "librsi.mcp.__main__:entrypoint",
}
REQUIRED_FACADE_EXPORTS = {
    "HypothesisTestResult",
    "LibRSI",
    "LibRSIRun",
    "WorkflowRequest",
}
MIT_LICENSE_TEXT = """MIT License

Copyright (c) 2026 Ethan Stillman

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


class ReleaseAuditError(RuntimeError):
    """Raised when source or an artifact violates the release contract."""


def _fail(message: str) -> NoReturn:
    raise ReleaseAuditError(message)


def validate_requirements(requirements: list[str]) -> None:
    """Reject internal artifacts and non-registry public dependency locators."""

    for requirement in requirements:
        normalized = requirement.lower().replace("_", "-")
        if any(name in normalized for name in INTERNAL_DISTRIBUTIONS):
            _fail(f"public metadata requires internal utility: {requirement}")
        if " @ " in requirement or "git+" in normalized or "file:" in normalized:
            _fail(f"public metadata contains a direct dependency locator: {requirement}")


def validate_public_exports(module: ModuleType) -> None:
    exports = getattr(module, "__all__", None)
    if not isinstance(exports, list) or any(not isinstance(name, str) for name in exports):
        _fail("librsi.__all__ must be a list of strings")
    if len(exports) != len(set(exports)):
        _fail("librsi.__all__ contains duplicate exports")
    missing = sorted(name for name in exports if not hasattr(module, name))
    if missing:
        _fail(f"librsi.__all__ names missing attributes: {missing}")
    absent_facade = sorted(REQUIRED_FACADE_EXPORTS - set(exports))
    if absent_facade:
        _fail(f"facade-first exports are absent: {absent_facade}")
    if getattr(module, "__version__", None) != EXPECTED_VERSION:
        _fail("runtime version differs from the release version")


def _license_classifier(classifiers: list[str]) -> str | None:
    observed = [item for item in classifiers if item.startswith("License ::")]
    if len(observed) > 1:
        _fail("project metadata contains multiple license classifiers")
    return observed[0] if observed else None


def validate_project_document(document: dict[str, Any], license_choice: ReleaseLicense) -> None:
    project = document.get("project")
    if not isinstance(project, dict):
        _fail("pyproject has no project table")
    if project.get("name") != "libRSI" or project.get("version") != EXPECTED_VERSION:
        _fail("project name/version differs from the release contract")
    dependencies = project.get("dependencies")
    if dependencies != []:
        _fail("base distribution must have zero dependencies")
    optional = project.get("optional-dependencies")
    if not isinstance(optional, dict) or set(optional) != PUBLIC_EXTRAS:
        _fail("public optional extras differ from the frozen release set")
    requirements: list[str] = []
    for extra, values in optional.items():
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            _fail(f"optional extra {extra} is malformed")
        requirements.extend(values)
    validate_requirements(requirements)
    if optional.get("providers") != optional.get("openai"):
        _fail("providers extra must be the published OpenAI aggregate only")
    scripts = project.get("scripts")
    if scripts != PUBLIC_SCRIPTS:
        _fail("console entrypoints differ from the frozen release set")
    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list) or any(
        not isinstance(value, str) for value in classifiers
    ):
        _fail("project classifiers are malformed")
    observed_classifier = _license_classifier(classifiers)
    observed_license = project.get("license")
    if observed_classifier is not None:
        _fail("project metadata contains a deprecated license classifier")
    if license_choice in {"pending", "no-license"}:
        if observed_license is not None:
            _fail("no-license posture contains a license grant")
    else:
        if observed_license != license_choice:
            _fail("project license expression differs from the selected license")


def validate_public_texts(texts: dict[str, str]) -> None:
    for label, text in texts.items():
        lowered = text.lower()
        if "@v0.2.0" in lowered:
            _fail(f"{label} contains a stale v0.2.0 install target")
        if "librsi[codex]" in lowered:
            _fail(f"{label} presents the internal Codex lane as a public extra")
        if "git+https://github.com/estill01/utils" in lowered:
            _fail(f"{label} presents an internal utility Git dependency")
        if "matching trove classifier" in lowered:
            _fail(f"{label} contains superseded license-classifier guidance")


def validate_source_tree(project_root: Path, license_choice: ReleaseLicense) -> None:
    with (project_root / "pyproject.toml").open("rb") as source:
        document = tomllib.load(source)
    validate_project_document(document, license_choice)
    required = (
        "CHANGELOG.md",
        "MANIFEST.in",
        "README.md",
        "docs/api.md",
        "docs/license-decision.md",
        "docs/migration-0.2.md",
        "docs/release-gate.md",
        "examples/local_hypothesis.py",
        "examples/local_validation.py",
        "src/librsi/py.typed",
    )
    missing = [relative for relative in required if not (project_root / relative).is_file()]
    if missing:
        _fail(f"release source files are absent: {missing}")
    validate_public_texts(
        {
            relative: (project_root / relative).read_text(encoding="utf-8")
            for relative in (
                "README.md",
                "docs/api.md",
                "docs/license-decision.md",
                "docs/migration-0.2.md",
                "examples/local_hypothesis.py",
                "examples/local_validation.py",
            )
        }
    )
    licenses = sorted(path.name for path in project_root.glob("LICENSE*"))
    if license_choice in {"pending", "no-license"} and licenses:
        _fail(f"no-license posture unexpectedly contains: {licenses}")
    if license_choice in {"MIT", "Apache-2.0"} and licenses != ["LICENSE"]:
        _fail("selected license requires exactly one root LICENSE file")
    if (
        license_choice == "MIT"
        and (project_root / "LICENSE").read_text(encoding="utf-8") != MIT_LICENSE_TEXT
    ):
        _fail("root LICENSE differs from the selected canonical MIT text")
    compatibility = json.loads(
        (project_root / "src/librsi/providers/compatibility.json").read_text(encoding="utf-8")
    )
    if compatibility.get("posture") != "no-license-selected/unpublished":
        _fail("utils compatibility posture overstates upstream authority")
    adapter = compatibility.get("librsi_adapter")
    if not isinstance(adapter, dict) or adapter.get("version") != EXPECTED_VERSION:
        _fail("provider adapter version differs from the release version")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _single(paths: list[Path], label: str) -> Path:
    if len(paths) != 1:
        _fail(f"expected one {label}, observed {[path.name for path in paths]}")
    return paths[0]


def _validate_wheel(path: Path, license_choice: ReleaseLicense) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        metadata_name = _single(
            [Path(name) for name in names if name.endswith(".dist-info/METADATA")],
            "wheel METADATA",
        ).as_posix()
        entrypoints_name = _single(
            [Path(name) for name in names if name.endswith(".dist-info/entry_points.txt")],
            "wheel entry_points.txt",
        ).as_posix()
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        if metadata.get("Name") != "libRSI" or metadata.get("Version") != EXPECTED_VERSION:
            _fail("wheel metadata name/version differs from the release contract")
        requirements = metadata.get_all("Requires-Dist", [])
        validate_requirements(requirements)
        unconditional = [item for item in requirements if "extra ==" not in item]
        if unconditional:
            _fail(f"wheel base install has dependencies: {unconditional}")
        classifiers = metadata.get_all("Classifier", [])
        observed_classifier = _license_classifier(classifiers)
        observed_license = metadata.get("License-Expression")
        if observed_classifier is not None:
            _fail("wheel metadata contains a deprecated license classifier")
        if license_choice in {"pending", "no-license"}:
            if observed_license:
                _fail("wheel grants a license under a no-license posture")
        else:
            if observed_license != license_choice:
                _fail("wheel license expression differs from the selection")
        license_files = metadata.get_all("License-File", [])
        embedded_license_names = sorted(
            name for name in names if name.endswith(".dist-info/licenses/LICENSE")
        )
        if license_choice in {"pending", "no-license"}:
            if license_files or embedded_license_names:
                _fail("wheel embeds a license under a no-license posture")
        elif license_files != ["LICENSE"] or len(embedded_license_names) != 1:
            _fail("wheel does not declare and embed the selected root LICENSE")
        if (
            license_choice == "MIT"
            and archive.read(embedded_license_names[0]).decode("utf-8") != MIT_LICENSE_TEXT
        ):
            _fail("wheel LICENSE differs from the selected canonical MIT text")
        required = {
            "librsi/README.md",
            "librsi/__init__.py",
            "librsi/_version.py",
            "librsi/conformance/shared-utilities.json",
            "librsi/providers/compatibility.json",
            "librsi/py.typed",
        }
        absent = sorted(required - names)
        if absent:
            _fail(f"wheel package data is incomplete: {absent}")
        compatibility = json.loads(archive.read("librsi/providers/compatibility.json"))
        if compatibility.get("posture") != "no-license-selected/unpublished":
            _fail("wheel utils posture overstates upstream authority")
        adapter = compatibility.get("librsi_adapter")
        if not isinstance(adapter, dict) or adapter.get("version") != EXPECTED_VERSION:
            _fail("wheel provider adapter version differs from the release version")
        first_parts = {Path(name).parts[0] for name in names}
        embedded = sorted(set(INTERNAL_IMPORT_ROOTS) & first_parts)
        if embedded:
            _fail(f"wheel embeds internal utility packages: {embedded}")
        entrypoints = archive.read(entrypoints_name).decode("utf-8")
        for name, target in PUBLIC_SCRIPTS.items():
            if f"{name} = {target}" not in entrypoints:
                _fail(f"wheel omits console entrypoint {name}")


def _validate_sdist(path: Path, license_choice: ReleaseLicense) -> None:
    with tarfile.open(path, mode="r:gz") as archive:
        members = {member.name for member in archive.getmembers() if member.isfile()}
        roots = {Path(name).parts[0] for name in members}
        if roots != {f"librsi-{EXPECTED_VERSION}"}:
            _fail(f"sdist root differs from version: {sorted(roots)}")
        root = next(iter(roots))
        required = {
            f"{root}/CHANGELOG.md",
            f"{root}/README.md",
            f"{root}/docs/api.md",
            f"{root}/docs/license-decision.md",
            f"{root}/docs/migration-0.2.md",
            f"{root}/docs/release-gate.md",
            f"{root}/examples/local_hypothesis.py",
            f"{root}/examples/local_validation.py",
            f"{root}/pyproject.toml",
            f"{root}/src/librsi/py.typed",
        }
        absent = sorted(required - members)
        if absent:
            _fail(f"sdist source surface is incomplete: {absent}")
        forbidden_release_paths = (
            f"{root}/docs/implementation/",
            f"{root}/docs/tracker.md",
            f"{root}/tests/",
        )
        leaked = sorted(
            name
            for name in members
            if any(name == prefix or name.startswith(prefix) for prefix in forbidden_release_paths)
        )
        if leaked:
            _fail(f"sdist contains internal implementation evidence: {leaked}")
        for import_root in INTERNAL_IMPORT_ROOTS:
            prefix = f"{root}/{import_root}/"
            if any(name.startswith(prefix) for name in members):
                _fail(f"sdist embeds internal utility package {import_root}")
        pyproject_file = archive.extractfile(f"{root}/pyproject.toml")
        if pyproject_file is None:
            _fail("sdist pyproject is unreadable")
        document = tomllib.loads(pyproject_file.read().decode("utf-8"))
        validate_project_document(document, license_choice)
        public_texts: dict[str, str] = {}
        for relative in (
            "README.md",
            "docs/api.md",
            "docs/license-decision.md",
            "docs/migration-0.2.md",
            "examples/local_hypothesis.py",
            "examples/local_validation.py",
        ):
            member = archive.extractfile(f"{root}/{relative}")
            if member is None:
                _fail(f"sdist public file is unreadable: {relative}")
            public_texts[relative] = member.read().decode("utf-8")
        validate_public_texts(public_texts)
        license_members = sorted(
            name
            for name in members
            if Path(name).parent == Path(root) and Path(name).name.startswith("LICENSE")
        )
        if license_choice in {"pending", "no-license"} and license_members:
            _fail(f"sdist unexpectedly contains a license: {license_members}")
        if license_choice in {"MIT", "Apache-2.0"} and license_members != [f"{root}/LICENSE"]:
            _fail("sdist does not contain the selected root LICENSE")
        if license_choice == "MIT":
            license_file = archive.extractfile(f"{root}/LICENSE")
            if license_file is None or license_file.read().decode("utf-8") != MIT_LICENSE_TEXT:
                _fail("sdist LICENSE differs from the selected canonical MIT text")


def audit_distributions(dist: Path, license_choice: ReleaseLicense) -> dict[str, str]:
    wheel = _single(sorted(dist.glob("*.whl")), "wheel")
    sdist = _single(sorted(dist.glob("*.tar.gz")), "sdist")
    _validate_wheel(wheel, license_choice)
    _validate_sdist(sdist, license_choice)
    return {wheel.name: _sha256(wheel), sdist.name: _sha256(sdist)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument(
        "--license",
        choices=("pending", "MIT", "Apache-2.0", "no-license"),
        default="pending",
    )
    args = parser.parse_args(argv)
    project_root = Path(__file__).parents[1]
    validate_source_tree(project_root, args.license)
    print(json.dumps(audit_distributions(args.dist, args.license), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
