"""Executable entrypoint for the optional HTTP service."""

from __future__ import annotations

import argparse
import os
from typing import NoReturn


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
    import uvicorn

    from ..service import LibRSIService, ServiceLimits
    from .app import create_http_app
    from .auth import HTTPTokenPolicy

    policy = HTTPTokenPolicy.from_tokens(**tokens) if protected else None
    service = LibRSIService.local(
        args.data_dir,
        limits=ServiceLimits(max_request_bytes=args.max_request_bytes),
    )
    app = create_http_app(service, token_policy=policy)
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        service.close()
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - executable module
    entrypoint()
