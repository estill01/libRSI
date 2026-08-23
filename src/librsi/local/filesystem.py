"""Deterministic, read-only snapshots of one configured directory."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from ..records import TargetRef, TargetSnapshot


def _text(value: str, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


class LocalFilesystemInspector:
    """Hash file and symlink state without following links or mutating the target."""

    def __init__(
        self,
        root: str | Path,
        *,
        ignored_names: Sequence[str] = (
            ".git",
            ".librsi",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "build",
            "dist",
        ),
        ignored_paths: Sequence[str | Path] = (),
    ) -> None:
        if not isinstance(root, (str, Path)):
            raise TypeError("filesystem root must be text or a Path")
        self._root = Path(root).expanduser().resolve()
        if not self._root.is_dir():
            raise ValueError("filesystem root must identify a directory")
        if isinstance(ignored_names, (str, bytes, bytearray)) or not isinstance(
            ignored_names, Sequence
        ):
            raise TypeError("ignored names must be a sequence")
        self._ignored_names = frozenset(_text(item, "ignored name") for item in ignored_names)
        if isinstance(ignored_paths, (str, bytes, bytearray)) or not isinstance(
            ignored_paths, Sequence
        ):
            raise TypeError("ignored paths must be a sequence")
        candidates = tuple(Path(item).expanduser().resolve() for item in ignored_paths)
        self._ignored_paths = frozenset(
            item for item in candidates if item == self._root or item.is_relative_to(self._root)
        )

    @property
    def root(self) -> Path:
        return self._root

    def target(self, *, target_id: str | None = None, kind: str = "filesystem") -> TargetRef:
        return TargetRef(
            target_id=self._root.name if target_id is None else _text(target_id, "target id"),
            kind=_text(kind, "target kind"),
            locator={"path": str(self._root)},
        )

    def _ignored(self, path: Path) -> bool:
        relative = path.relative_to(self._root)
        if any(part in self._ignored_names for part in relative.parts):
            return True
        resolved = path.resolve()
        return any(
            resolved == item or resolved.is_relative_to(item) for item in self._ignored_paths
        )

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

    def snapshot(self, target: TargetRef) -> TargetSnapshot:
        if not isinstance(target, TargetRef):
            raise TypeError("filesystem snapshot requires a TargetRef")
        if target.locator.get("path") != str(self._root):
            raise ValueError("filesystem target is outside the configured inspector root")
        entries: list[dict[str, object]] = []
        for path in sorted(self._root.rglob("*")):
            if self._ignored(path):
                continue
            relative = path.relative_to(self._root).as_posix()
            if path.is_symlink():
                entries.append(
                    {"path": relative, "type": "symlink", "target": path.readlink().as_posix()}
                )
            elif path.is_file():
                entries.append(
                    {
                        "path": relative,
                        "type": "file",
                        "size": path.stat().st_size,
                        "digest": self._file_digest(path),
                    }
                )
        encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
        content_digest = f"sha256:{hashlib.sha256(encoded).hexdigest()}"
        return TargetSnapshot(
            target=target,
            revision=content_digest,
            state={
                "content_digest": content_digest,
                "entry_count": len(entries),
                "entries": entries,
            },
        )
