"""Optional MCP bearer verifier kept outside canonical libRSI state."""

from __future__ import annotations

import hmac

from mcp.server.auth.provider import AccessToken


class StaticTokenVerifier:
    """Small deployment seam for one externally supplied MCP bearer token."""

    def __init__(self, token: str, *, scopes: tuple[str, ...] = ("librsi",)) -> None:
        if type(token) is not str or not token:
            raise ValueError("MCP bearer token is required")
        if not scopes or any(type(item) is not str or not item.strip() for item in scopes):
            raise ValueError("MCP bearer scopes are required")
        self._token = token
        self._scopes = tuple(item.strip() for item in scopes)

    async def verify_token(self, token: str) -> AccessToken | None:
        if not hmac.compare_digest(token, self._token):
            return None
        return AccessToken(
            token=token,
            client_id="librsi-configured-client",
            scopes=list(self._scopes),
            subject="librsi-configured-client",
        )
