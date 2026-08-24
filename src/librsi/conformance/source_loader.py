"""libRSI-owned execution boundary for exact qualified source packages."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import MappingProxyType, ModuleType

_LOAD_LOCK = RLock()


@dataclass(frozen=True, slots=True)
class CanonicalSourcePackage:
    """Module graph created by executing one installed package from exact sources."""

    import_root: str
    alias: str
    package: Path
    root: ModuleType
    modules: Mapping[str, ModuleType]
    namespaces: Mapping[str, Mapping[str, object]]


def execute_source_package(import_root: str, package: Path) -> CanonicalSourcePackage:
    """Execute an installed package under a private namespace owned by libRSI."""

    if type(import_root) is not str or not import_root:
        raise ValueError("qualified source import root is required")
    if not isinstance(package, Path) or not package.is_absolute():
        raise TypeError("qualified source package requires an absolute Path")
    source = package / "__init__.py"
    if not source.is_file():
        raise RuntimeError("qualified source package has no importable root")
    alias = f"_librsi_qualified_{import_root}"
    prefix = f"{alias}."
    with _LOAD_LOCK:
        for name in tuple(sys.modules):
            if name == alias or name.startswith(prefix):
                del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            alias,
            source,
            submodule_search_locations=[str(package)],
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("qualified source package loader is unavailable")
        root = importlib.util.module_from_spec(spec)
        sys.modules[alias] = root
        try:
            spec.loader.exec_module(root)
            modules = {
                name: module
                for name, module in sys.modules.items()
                if (name == alias or name.startswith(prefix)) and type(module) is ModuleType
            }
            namespaces = {
                name: MappingProxyType(dict(module.__dict__)) for name, module in modules.items()
            }
        except Exception:
            for name in tuple(sys.modules):
                if name == alias or name.startswith(prefix):
                    del sys.modules[name]
            raise
        if modules.get(alias) is not root:
            raise RuntimeError("qualified source package root was not executed exactly")
        return CanonicalSourcePackage(
            import_root=import_root,
            alias=alias,
            package=package,
            root=root,
            modules=MappingProxyType(modules),
            namespaces=MappingProxyType(namespaces),
        )
