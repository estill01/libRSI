from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

GENERIC_TOP_LEVEL_MODULES = (
    "checkpoints.py",
    "epistemics.py",
    "errors.py",
    "evaluation.py",
    "experiments.py",
    "hypotheses.py",
    "identity.py",
    "kernel.py",
    "knowledge.py",
    "models.py",
    "portfolios.py",
    "ports.py",
    "programs.py",
    "records.py",
    "reviews.py",
    "selections.py",
    "selector_policies.py",
    "sqlite_knowledge.py",
    "sqlite_schema.py",
    "sqlite_support.py",
    "targets.py",
)
GENERIC_PACKAGES = (
    "application",
    "capabilities",
    "comparison",
    "governance",
    "improvement",
    "intent",
    "interventions",
    "investigation",
    "projections",
    "protocol",
    "reasoning",
    "rsi",
    "runtime",
    "service",
    "validation",
)
FORBIDDEN_ADAPTER_IMPORTS = (
    "dulwich",
    "git",
    "gitpython",
    "librsi.cli",
    "librsi.http",
    "librsi.local",
    "librsi.mcp",
    "librsi.providers",
    "pygit2",
)
SOFTWARE_TARGET_KINDS = {
    "git-repository",
    "repository",
    "software-repository",
    "source-tree",
    "worktree",
}


@dataclass(frozen=True, order=True)
class DomainLeak:
    module: str
    line: int
    detail: str


@dataclass(frozen=True)
class DomainAudit:
    paths: tuple[str, ...]
    source_root: str
    leaks: tuple[DomainLeak, ...]


def _module_name(path: Path, source_root: Path) -> str:
    relative = path.relative_to(source_root).with_suffix("")
    return ".".join(relative.parts)


def _resolve_import(module_name: str, node: ast.ImportFrom) -> str:
    if node.level == 0:
        return node.module or ""
    package = module_name.split(".")[:-1]
    keep = len(package) - (node.level - 1)
    prefix = package[: max(0, keep)]
    suffix = [] if node.module is None else node.module.split(".")
    return ".".join((*prefix, *suffix))


def _forbidden_import(name: str) -> bool:
    return any(
        name == prefix or name.startswith(f"{prefix}.") for prefix in FORBIDDEN_ADAPTER_IMPORTS
    )


def _software_identifier(name: str) -> bool:
    words = tuple(item for item in re.split(r"[^a-z0-9]+", name.lower()) if item)
    tokens = set(words)
    return bool(
        tokens & {"git", "github", "patch", "repo", "repository", "worktree"}
        or ({"build", "command"} <= tokens)
        or ({"commit", "sha"} <= tokens)
        or ({"pull", "request"} <= tokens)
        or {"source", "tree"} <= tokens
        or {"software", "repository"} <= tokens
    )


def audit_source(source: str, *, module_name: str) -> tuple[DomainLeak, ...]:
    tree = ast.parse(source, filename=module_name)
    leaks: set[DomainLeak] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden_import(alias.name):
                    leaks.add(
                        DomainLeak(
                            module_name,
                            node.lineno,
                            f"forbidden adapter import: {alias.name}",
                        )
                    )
        elif isinstance(node, ast.ImportFrom):
            imported = _resolve_import(module_name, node)
            candidates = (imported, *(f"{imported}.{alias.name}" for alias in node.names))
            for candidate in candidates:
                if _forbidden_import(candidate):
                    leaks.add(
                        DomainLeak(
                            module_name,
                            node.lineno,
                            f"forbidden adapter import: {candidate}",
                        )
                    )
        elif isinstance(node, (ast.Name, ast.Attribute, ast.arg, ast.keyword)):
            name = (
                node.id
                if isinstance(node, ast.Name)
                else node.attr
                if isinstance(node, ast.Attribute)
                else node.arg
            )
            if name is None:
                continue
            if _software_identifier(name):
                leaks.add(
                    DomainLeak(
                        module_name,
                        node.lineno,
                        f"software-specific generic identifier: {name}",
                    )
                )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.lower()
            if value in SOFTWARE_TARGET_KINDS:
                leaks.add(
                    DomainLeak(
                        module_name,
                        node.lineno,
                        f"software-only target branch: {value}",
                    )
                )
        elif isinstance(node, ast.Dict):
            for key in node.keys:
                if (
                    isinstance(key, ast.Constant)
                    and isinstance(key.value, str)
                    and _software_identifier(key.value)
                ):
                    leaks.add(
                        DomainLeak(
                            module_name,
                            key.lineno,
                            f"software-specific generic field: {key.value}",
                        )
                    )
    return tuple(sorted(leaks))


def generic_source_paths(source_root: Path) -> tuple[Path, ...]:
    librsi_root = source_root / "librsi"
    paths = [librsi_root / name for name in GENERIC_TOP_LEVEL_MODULES]
    for package in GENERIC_PACKAGES:
        paths.extend(sorted((librsi_root / package).rglob("*.py")))
    return tuple(sorted(set(paths)))


def audit_generic_tree(source_root: Path) -> DomainAudit:
    paths = generic_source_paths(source_root)
    missing = tuple(path for path in paths if not path.is_file())
    if missing:
        raise FileNotFoundError(f"generic source audit paths are missing: {missing}")
    leaks: list[DomainLeak] = []
    source_entries: list[str] = []
    for path in paths:
        source = path.read_text(encoding="utf-8")
        relative = path.relative_to(source_root).as_posix()
        source_entries.append(f"{relative}\0{hashlib.sha256(source.encode()).hexdigest()}")
        leaks.extend(audit_source(source, module_name=_module_name(path, source_root)))
    source_root_hash = hashlib.sha256("\n".join(source_entries).encode()).hexdigest()
    return DomainAudit(
        paths=tuple(path.relative_to(source_root).as_posix() for path in paths),
        source_root=source_root_hash,
        leaks=tuple(sorted(leaks)),
    )
