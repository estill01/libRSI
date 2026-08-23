from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from librsi import record_from_dict, serialize_record
from librsi.runtime import Action
from tests.block20_support import target_admission, validation_request, validation_result


def _invoke(site: Path, data: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(site)
    return subprocess.run(
        [sys.executable, "-m", "librsi", "--data-dir", str(data), *arguments],
        cwd=data.parent,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_built_wheel_installs_and_drives_the_external_cli(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    wheelhouse = tmp_path / "wheelhouse"
    built = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(wheelhouse),
            str(project),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    wheels = tuple(wheelhouse.glob("*.whl"))
    assert len(wheels) == 1

    site_packages = tmp_path / "installed-site"
    with zipfile.ZipFile(wheels[0]) as archive:
        entry_points = next(
            name for name in archive.namelist() if name.endswith(".dist-info/entry_points.txt")
        )
        assert "librsi = librsi.cli.main:entrypoint" in archive.read(entry_points).decode()
        archive.extractall(site_packages)

    isolated = os.environ.copy()
    isolated["PYTHONPATH"] = str(site_packages)
    imported = subprocess.run(
        [sys.executable, "-c", "import librsi; print(librsi.__file__)"],
        cwd=tmp_path,
        env=isolated,
        text=True,
        capture_output=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr
    assert Path(imported.stdout.strip()).is_relative_to(site_packages)

    admission = target_admission()
    request = validation_request()
    admission_path = tmp_path / "admission.json"
    request_path = tmp_path / "request.json"
    admission_path.write_text(serialize_record(admission), encoding="utf-8")
    request_path.write_text(serialize_record(request), encoding="utf-8")
    data = tmp_path / "durable-state"

    admitted = _invoke(site_packages, data, "target", "submit", "--input", str(admission_path))
    started = _invoke(
        site_packages,
        data,
        "validate",
        "--request",
        str(request_path),
        "--admission",
        admission.admission_id,
    )
    pending = _invoke(site_packages, data, "next", request.validation_id)
    assert admitted.returncode == started.returncode == pending.returncode == 0

    document = json.loads(pending.stdout)
    action = record_from_dict(document["data"]["action"])
    assert type(action) is Action
    result_path = tmp_path / "result.json"
    result_path.write_text(serialize_record(validation_result(action)), encoding="utf-8")
    submitted = _invoke(
        site_packages,
        data,
        "submit",
        request.validation_id,
        "--input",
        str(result_path),
        "--authority",
        "external",
    )
    outcome = _invoke(site_packages, data, "outcome", request.validation_id)

    assert submitted.returncode == outcome.returncode == 0
    assert json.loads(submitted.stdout)["data"]["terminal"] is True
    assert json.loads(outcome.stdout)["data"]["projection"]["workflow"] == "validation"
