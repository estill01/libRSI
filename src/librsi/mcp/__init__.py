"""Optional maintained MCP projection with dependency-lazy exports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .auth import StaticTokenVerifier
    from .server import create_mcp_server

__all__ = ["StaticTokenVerifier", "create_mcp_server"]


def __getattr__(name: str) -> Any:
    if name == "StaticTokenVerifier":
        from .auth import StaticTokenVerifier

        return StaticTokenVerifier
    if name == "create_mcp_server":
        from .server import create_mcp_server

        return create_mcp_server
    raise AttributeError(name)
