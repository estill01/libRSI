"""Executable entrypoint for the optional HTTP service."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, NoReturn


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librsi-http")
    parser.add_argument("--data-dir", default=".librsi")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--max-request-bytes", type=int, default=1_048_576)
    parser.add_argument("--read-token-env", default="LIBRSI_HTTP_READ_TOKEN")
    parser.add_argument("--mutate-token-env", default="LIBRSI_HTTP_MUTATE_TOKEN")
    parser.add_argument("--apply-token-env", default="LIBRSI_HTTP_APPLY_TOKEN")
    return parser


def __getattr__(name: str) -> Any:
    """Resolve optional runtime dependencies only when execution needs them."""

    if name == "uvicorn":
        import uvicorn

        return uvicorn
    if name in {"LibRSIService", "ServiceLimits"}:
        from .. import service

        return getattr(service, name)
    if name == "create_http_app":
        from .app import create_http_app

        return create_http_app
    if name == "HTTPTokenPolicy":
        from .auth import HTTPTokenPolicy

        return HTTPTokenPolicy
    raise AttributeError(name)


def _dependencies() -> tuple[Any, Any, Any, Any, Any]:
    module = sys.modules[__name__]
    return tuple(
        getattr(module, name)
        for name in (
            "uvicorn",
            "LibRSIService",
            "ServiceLimits",
            "create_http_app",
            "HTTPTokenPolicy",
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    tokens = {
        "read_token": os.environ.get(args.read_token_env),
        "mutate_token": os.environ.get(args.mutate_token_env),
        "apply_token": os.environ.get(args.apply_token_env),
    }
    protected = any(value is not None for value in tokens.values())
    if args.host not in {"127.0.0.1", "::1", "localhost"} and not protected:
        raise ValueError("non-loopback HTTP binding requires configured bearer tokens")
    uvicorn, LibRSIService, ServiceLimits, create_http_app, HTTPTokenPolicy = _dependencies()

    policy = HTTPTokenPolicy.from_tokens(**tokens) if protected else None
    service = LibRSIService.local(
        args.data_dir,
        limits=ServiceLimits(max_request_bytes=args.max_request_bytes),
    )
    try:
        app = create_http_app(service, token_policy=policy)
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        service.close()
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - executable module
    entrypoint()
