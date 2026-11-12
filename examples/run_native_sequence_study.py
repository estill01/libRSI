"""Run, audit and graph the registered three-case Astra/libRSI comparison."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from audit_native_sequence import audit
from extend_native_confirmation import register
from extend_native_confirmation import run as confirm
from plot_native_sequence import render


def run(output, reuse=None):
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    command = [
        sys.executable,
        str(Path(__file__).with_name("benchmark_native_sequence.py")),
        "--output",
        str(raw),
    ]
    if reuse is not None:
        command += ["--reuse-proposals", str(reuse)]
    process = subprocess.Popen(command, start_new_session=os.name == "posix")
    try:
        while True:
            try:
                json.loads((raw / "protocol.json").read_text())
                break
            except (FileNotFoundError, json.JSONDecodeError):
                if process.poll() is not None:
                    raise RuntimeError(
                        f"native runner stopped before registration: {process.returncode}"
                    ) from None
                time.sleep(0.2)
        # Register before the model starts meta development or final confirmation.
        register(raw)
        if process.wait():
            raise RuntimeError(
                "native run failed; retained receipts and stores identify the unfinished work"
            )
    except BaseException:
        if process.poll() is None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=10)
        raise
    audit(raw, output / "audit")
    confirm(raw, output / "confirmation")
    report = json.loads(
        gzip.decompress((output / "confirmation/confirmed-report.json.gz").read_bytes())
    )
    render(report, json.loads((raw / "receipts.json").read_text()), output / "plots")
    print(f"Completed data and graphs: {output.resolve()}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-proposals", type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.reuse_proposals)
