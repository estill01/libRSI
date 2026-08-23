"""Explicit filesystem layout for the local reference composition."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _directory(value: str | Path, label: str, *, create: bool) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{label} must be text or a Path")
    path = Path(value).expanduser().resolve()
    if path.exists() and not path.is_dir():
        raise ValueError(f"{label} must identify a directory")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise ValueError(f"{label} must identify a directory")
    return path


@dataclass(frozen=True)
class LocalLayout:
    """All local paths are explicit and instance-owned."""

    workspace: Path
    data_directory: Path
    runtime_database: Path
    knowledge_database: Path
    artifact_directory: Path

    @classmethod
    def create(
        cls,
        workspace: str | Path = ".",
        *,
        data_directory: str | Path | None = None,
    ) -> LocalLayout:
        root = _directory(workspace, "local workspace", create=False)
        data = _directory(
            root / ".librsi" if data_directory is None else data_directory,
            "local data directory",
            create=True,
        )
        if data == root:
            raise ValueError("local data directory must be separate from the workspace root")
        artifacts = _directory(data / "artifacts", "local artifact directory", create=True)
        return cls(
            workspace=root,
            data_directory=data,
            runtime_database=data / "runtime.sqlite",
            knowledge_database=data / "knowledge.sqlite",
            artifact_directory=artifacts,
        )
