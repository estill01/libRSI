from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest

from librsi.local import LocalCommandRunner
from librsi.models import CommandExperimentInput


def test_nonzero_exit_is_an_observation_not_an_execution_failure(tmp_path) -> None:
    result = LocalCommandRunner(allowed_roots=(tmp_path,)).run(
        CommandExperimentInput(
            "nonzero",
            (sys.executable, "-c", "import sys; print('measured'); sys.exit(7)"),
            str(tmp_path),
        ),
        timeout_seconds=5,
    )
    assert result.exit_code == 7 and result.stdout == "measured\n"
    assert result.invalid is False


@pytest.mark.skipif(os.name != "posix", reason="process-group cleanup is POSIX-only")
@pytest.mark.parametrize("ignore_term", [False, True])
def test_timeout_stops_owned_descendants_but_leaves_other_processes(tmp_path, ignore_term) -> None:
    marker = tmp_path / "late-effect"
    ready = tmp_path / "ready"
    child = (
        "import signal,time; from pathlib import Path; "
        + ("signal.signal(signal.SIGTERM,signal.SIG_IGN); " if ignore_term else "")
        + f"Path({str(ready)!r}).touch(); time.sleep(2); Path({str(marker)!r}).touch()"
    )
    parent = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable,'-c',{child!r}],"
        "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
        "print('started',flush=True); time.sleep(10)"
    )
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(15)"])
    try:
        result = LocalCommandRunner(allowed_roots=(tmp_path,)).run(
            CommandExperimentInput("timeout-tree", (sys.executable, "-c", parent), str(tmp_path)),
            timeout_seconds=1,
        )
        assert result.invalid and result.exit_code is None
        assert result.stdout == "started\n"
        assert ready.exists(), "child must start before testing descendant cleanup"
        time.sleep(1.4)
        assert not marker.exists()
        assert unrelated.poll() is None
    finally:
        unrelated.terminate()
        unrelated.wait(timeout=5)
