"""Run with: python examples/local_hypothesis.py"""

from __future__ import annotations

import sys

from librsi import LibRSI

with LibRSI.local(".") as lib:
    result = lib.test_hypothesis(
        "The local command reports READY",
        command=(sys.executable, "-c", "print('READY')"),
        success_criteria={
            "accepted_exit_codes": [0],
            "stdout_contains": ["READY"],
        },
    )

print(result.evidence.evidence_type)
