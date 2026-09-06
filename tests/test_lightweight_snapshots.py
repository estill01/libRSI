from __future__ import annotations

import os

import pytest

from librsi import LocalFilesystemInspector


@pytest.mark.skipif(os.name != "posix", reason="POSIX executable mode bits")
def test_snapshot_tracks_executable_bits_and_ignores_incidental_timestamps(tmp_path) -> None:
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o644)
    inspector = LocalFilesystemInspector(tmp_path)
    target = inspector.target()
    plain = inspector.snapshot(target)
    script.touch()
    assert inspector.snapshot(target) == plain
    script.chmod(0o755)
    executable = inspector.snapshot(target)
    assert executable != plain
    assert executable.state["entries"][0]["executable_bits"] == 0o111
    assert inspector.snapshot(target) == executable
    script.chmod(0o744)
    owner_only = inspector.snapshot(target)
    assert owner_only != executable
    assert owner_only.state["entries"][0]["executable_bits"] == 0o100
    script.chmod(0o644)
    assert inspector.snapshot(target) == plain
