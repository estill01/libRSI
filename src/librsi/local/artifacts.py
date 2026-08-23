"""Small content-checked artifact-directory adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from ..records import ArtifactRef


def _artifact_path(root: Path, artifact_id: str) -> Path:
    if not isinstance(artifact_id, str):
        raise TypeError("artifact id must be text")
    normalized = artifact_id.strip()
    if not normalized:
        raise ValueError("artifact id is required")
    relative = PurePosixPath(normalized)
    if (
        normalized != artifact_id
        or relative.as_posix() != normalized
        or relative.is_absolute()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("artifact id must be a canonical safe relative path")
    candidate = root.joinpath(*relative.parts).resolve()
    if not candidate.is_relative_to(root):
        raise ValueError("artifact path escapes its configured directory")
    return candidate


def _digest(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


class LocalArtifactStore:
    """Persist immutable artifact bytes under one configured directory."""

    def __init__(self, directory: str | Path) -> None:
        if not isinstance(directory, (str, Path)):
            raise TypeError("artifact directory must be text or a Path")
        self._directory = Path(directory).expanduser().resolve()
        if self._directory.exists() and not self._directory.is_dir():
            raise ValueError("artifact directory must identify a directory")
        self._directory.mkdir(parents=True, exist_ok=True)
        if not self._directory.is_dir():
            raise ValueError("artifact directory must identify a directory")

    @property
    def directory(self) -> Path:
        return self._directory

    def put(
        self,
        artifact_id: str,
        content: bytes,
        *,
        media_type: str | None = None,
    ) -> ArtifactRef:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        path = _artifact_path(self._directory, artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if not path.is_file() or path.read_bytes() != content:
                raise ValueError("artifact id already names different content")
        else:
            temporary = path.with_name(f".{path.name}.tmp")
            if temporary.exists():
                raise ValueError("artifact temporary path is already occupied")
            temporary.write_bytes(content)
            temporary.replace(path)
        return ArtifactRef(
            artifact_id=artifact_id.strip(),
            uri=path.as_uri(),
            content_digest=_digest(content),
            media_type=media_type,
        )

    def get(self, artifact: ArtifactRef) -> bytes:
        if not isinstance(artifact, ArtifactRef):
            raise TypeError("artifact retrieval requires an ArtifactRef")
        parsed = urlparse(artifact.uri)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise ValueError("local artifact references require a local file URI")
        path = Path(url2pathname(unquote(parsed.path))).resolve()
        expected = _artifact_path(self._directory, artifact.artifact_id)
        if path != expected or not path.is_file():
            raise ValueError("artifact reference is outside the configured directory")
        content = path.read_bytes()
        if artifact.content_digest != _digest(content):
            raise ValueError("artifact content no longer matches its exact digest")
        return content
