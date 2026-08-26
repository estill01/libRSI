"""Optional maintained HTTP projection with dependency-lazy exports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .app import create_http_app
    from .auth import HTTP_PERMISSIONS, HTTPTokenCredential, HTTPTokenPolicy

__all__ = [
    "HTTP_PERMISSIONS",
    "HTTPTokenCredential",
    "HTTPTokenPolicy",
    "create_http_app",
]


def __getattr__(name: str) -> Any:
    if name == "create_http_app":
        from .app import create_http_app

        return create_http_app
    if name in {"HTTP_PERMISSIONS", "HTTPTokenCredential", "HTTPTokenPolicy"}:
        from . import auth

        return getattr(auth, name)
    raise AttributeError(name)
