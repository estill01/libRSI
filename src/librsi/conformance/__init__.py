"""Lightweight public helpers for consumer conformance fixtures."""

from .mapping import ComponentState, CompositeSnapshot, map_composite_snapshot
from .shared_handoff import (
    EMBEDDED_SERVICE_HANDOFF,
    QUALIFIED_PACKAGE_SET,
    RUNTIME_MANIFEST_HANDOFF,
    QualifiedPackageSet,
    SharedPackageHandoff,
    load_shared_utilities,
    validate_shared_package,
)

__all__ = [
    "EMBEDDED_SERVICE_HANDOFF",
    "QUALIFIED_PACKAGE_SET",
    "RUNTIME_MANIFEST_HANDOFF",
    "ComponentState",
    "CompositeSnapshot",
    "QualifiedPackageSet",
    "SharedPackageHandoff",
    "load_shared_utilities",
    "map_composite_snapshot",
    "validate_shared_package",
]
