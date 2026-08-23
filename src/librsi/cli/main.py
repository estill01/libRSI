"""Structured command-line projection over :mod:`librsi.protocol`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from ..protocol import ExternalAgentController, TargetAdmission, error_document, serialize_response
from ..records import SemanticRecord, TargetSnapshot, record_from_dict
from ..runtime import ActionResult


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="librsi", description="Structured external-agent projection")
    parser.add_argument("--data-dir", default=".librsi", help="durable local state directory")
    commands = parser.add_subparsers(dest="command", required=True)

    target = commands.add_parser("target")
    target_commands = target.add_subparsers(dest="target_command", required=True)
    target_submit = target_commands.add_parser("submit")
    target_submit.add_argument("--input", required=True)

    for name in ("validate", "investigate", "improve", "rsi"):
        start = commands.add_parser(name)
        start.add_argument("--request", required=True)
        start.add_argument("--admission", required=True)

    for name in ("status", "next", "resume", "outcome"):
        operation = commands.add_parser(name)
        operation.add_argument("run_id")

    submit = commands.add_parser("submit")
    submit.add_argument("run_id")
    submit.add_argument("--input", required=True)
    submit.add_argument(
        "--authority",
        required=True,
        choices=("automatic", "external", "human-reserved"),
    )
    submit.add_argument("--current-snapshot")
    return parser


def _record(path: str) -> SemanticRecord:
    text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("input must contain valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("input must contain one JSON object")
    record = record_from_dict(payload)
    if payload != record.to_dict():
        raise ValueError("input fields diverge from the canonical record")
    return record


def _run(args: argparse.Namespace) -> dict[str, object]:
    controller = ExternalAgentController.local(args.data_dir)
    try:
        if args.command == "target":
            admission = _record(args.input)
            if type(admission) is not TargetAdmission:
                raise TypeError("target submit requires a TargetAdmission record")
            return controller.submit_target(admission)
        if args.command in {"validate", "investigate", "improve", "rsi"}:
            request = _record(args.request)
            expected_type = {
                "validate": "validation_request",
                "investigate": "investigation_request",
                "improve": "improvement_request",
                "rsi": "rsi_request",
            }[args.command]
            if request.record_type != expected_type:
                raise TypeError(f"{args.command} requires a {expected_type} record")
            return controller.start(request, admission_id=args.admission)  # type: ignore[arg-type]
        if args.command == "status":
            return controller.status(args.run_id)
        if args.command == "next":
            return controller.next(args.run_id)
        if args.command == "resume":
            return controller.resume(args.run_id)
        if args.command == "outcome":
            return controller.outcome(args.run_id)
        if args.command == "submit":
            result = _record(args.input)
            if type(result) is not ActionResult:
                raise TypeError("submit requires an ActionResult record")
            snapshot = None
            if args.current_snapshot is not None:
                supplied = _record(args.current_snapshot)
                if type(supplied) is not TargetSnapshot:
                    raise TypeError("current snapshot must be a TargetSnapshot record")
                snapshot = supplied
            return controller.submit(
                args.run_id,
                result,
                authority=args.authority,
                current_snapshot=snapshot,
            )
        raise ValueError("unsupported command")
    finally:
        controller.close()


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        document = _run(args)
    except Exception as error:
        sys.stderr.write(serialize_response(error_document(error)) + "\n")
        return 2
    sys.stdout.write(serialize_response(document) + "\n")
    return 0


def entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover - installed entrypoint exercises this
    entrypoint()
