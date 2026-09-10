"""One bounded JSON request on stdin, one JSON response on stdout."""

from __future__ import annotations

import json
import sys
from typing import Any

from .external import RESPONSE_SCHEMA, evaluate_request

MAX_INPUT_BYTES = 8 * 1024 * 1024


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError("nonfinite JSON number")


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        if len(data) > MAX_INPUT_BYTES:
            raise ValueError("comparison input exceeds byte limit")
        payload = json.loads(data, object_pairs_hook=_object, parse_constant=_constant)
        response = evaluate_request(payload)
        encoded = json.dumps(response, allow_nan=False, separators=(",", ":"))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        # Do not echo arbitrary input, paths, or exception text into host logs.
        print(
            json.dumps(
                {
                    "schema": RESPONSE_SCHEMA,
                    "status": "failed",
                    "activation_authorized": False,
                    "error": {
                        "code": "invalid_comparison_request",
                        "message": "Invalid comparison request",
                    },
                }
            )
        )
        return 2
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
