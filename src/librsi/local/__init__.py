"""Thin standard-library defaults for local libRSI composition."""

from .artifacts import LocalArtifactStore
from .commands import LocalCommandRunner
from .concurrent_learning import LocalConcurrentLearningStore
from .filesystem import LocalFilesystemInspector
from .layout import LocalLayout
from .learning import LocalLearningStore
from .logging import LoggingTransitionSink
from .protocols import ArtifactStore, TransitionSink, WorkspaceInspector, emit_transitions

__all__ = [
    "ArtifactStore",
    "LocalArtifactStore",
    "LocalCommandRunner",
    "LocalConcurrentLearningStore",
    "LocalFilesystemInspector",
    "LocalLayout",
    "LocalLearningStore",
    "LoggingTransitionSink",
    "TransitionSink",
    "WorkspaceInspector",
    "emit_transitions",
]
