"""Run with: python examples/local_hypothesis.py"""

from __future__ import annotations

import sys
from tempfile import TemporaryDirectory

from librsi import LibRSI

with TemporaryDirectory(prefix="librsi-hypothesis-") as workspace, LibRSI.local(workspace) as lib:
    result = lib.test_hypothesis(
        "The local command reports READY",
        command=(sys.executable, "-c", "print('READY')"),
        success_criteria={
            "accepted_exit_codes": [0],
            "stdout_contains": ["READY"],
        },
    )

print(result.evidence.evidence_type)
