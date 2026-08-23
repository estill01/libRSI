"""Thin standard-library defaults for local libRSI composition."""

from .artifacts import LocalArtifactStore
from .commands import LocalCommandRunner
from .filesystem import LocalFilesystemInspector
from .layout import LocalLayout
from .logging import LoggingTransitionSink
from .protocols import ArtifactStore, TransitionSink, WorkspaceInspector, emit_transitions

__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "LocalCommandRunner",
    "LocalFilesystemInspector",
    "LocalLayout",
    "LoggingTransitionSink",
    "TransitionSink",
    "WorkspaceInspector",
    "emit_transitions",
]
