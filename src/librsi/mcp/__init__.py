"""Optional maintained MCP projection."""

from .auth import StaticTokenVerifier
from .server import create_mcp_server

__all__ = ["StaticTokenVerifier", "create_mcp_server"]
