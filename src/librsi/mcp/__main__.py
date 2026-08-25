"""Executable stdio or Streamable HTTP MCP server."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, NoReturn


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librsi-mcp")
    parser.add_argument("--data-dir", default=".librsi")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--max-request-bytes", type=int, default=1_048_576)
    parser.add_argument("--token-env", default="LIBRSI_MCP_TOKEN")
    parser.add_argument("--auth-issuer-url")
    parser.add_argument("--auth-resource-url")
    return parser


def __getattr__(name: str) -> Any:
    """Resolve optional runtime dependencies only when execution needs them."""

    if name == "AuthSettings":
        from mcp.server.auth.settings import AuthSettings

        return AuthSettings
    if name in {"LibRSIService", "ServiceLimits"}:
        from .. import service

        return getattr(service, name)
    if name == "StaticTokenVerifier":
        from .auth import StaticTokenVerifier

        return StaticTokenVerifier
    if name == "create_mcp_server":
        from .server import create_mcp_server

        return create_mcp_server
    raise AttributeError(name)


def _dependencies() -> tuple[Any, Any, Any, Any, Any]:
    module = sys.modules[__name__]
    return tuple(
        getattr(module, name)
        for name in (
            "AuthSettings",
            "LibRSIService",
            "ServiceLimits",
            "StaticTokenVerifier",
            "create_mcp_server",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.environ.get(args.token_env)
    remote = args.host not in {"127.0.0.1", "::1", "localhost"}
    auth_values = (token, args.auth_issuer_url, args.auth_resource_url)
    if remote and any(value is None for value in auth_values):
        raise ValueError("non-loopback MCP binding requires bearer and OAuth resource metadata")
    if any(value is not None for value in auth_values) and any(
        value is None for value in auth_values
    ):
        raise ValueError("MCP auth token, issuer URL, and resource URL must be configured together")
    AuthSettings, LibRSIService, ServiceLimits, StaticTokenVerifier, create_mcp_server = (
        _dependencies()
    )

    auth = None
    verifier = None
    if token is not None:
        auth = AuthSettings(
            issuer_url=args.auth_issuer_url,
            resource_server_url=args.auth_resource_url,
            required_scopes=["librsi"],
        )
        verifier = StaticTokenVerifier(token)
    service = LibRSIService.local(
        args.data_dir,
        limits=ServiceLimits(max_request_bytes=args.max_request_bytes),
    )
    try:
        server = create_mcp_server(service, auth=auth, token_verifier=verifier)
        if args.transport == "stdio":
            server.run("stdio")
        else:
            server.run(
                "streamable-http",
                host=args.host,
                port=args.port,
                stateless_http=True,
                max_request_body_size=args.max_request_bytes,
            )
    finally:
        service.close()
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - executable module
    entrypoint()
