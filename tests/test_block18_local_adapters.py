from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from librsi import (
    Action,
    ArtifactRef,
    Goal,
    LocalArtifactStore,
    LocalCommandRunner,
    LocalFilesystemInspector,
    LocalLayout,
    LoggingTransitionSink,
    Run,
    RuntimeEngine,
    TargetRef,
    Transition,
    emit_transitions,
)
from librsi.models import CommandExperimentInput


def _transition() -> Transition:
    run = Run(run_id="logged-run", intent=Goal(statement="observe transitions").ref)
    started = RuntimeEngine.start(run)
    assert started.transition is not None
    requested = RuntimeEngine.request(
        started.state,
        Action(run=run.ref, action_id="inspect", kind="inspect"),
    )
    assert requested.transition is not None
    return requested.transition


def test_local_layout_is_explicit_and_separate(tmp_path: Path) -> None:
    layout = LocalLayout.create(tmp_path)

    assert layout.workspace == tmp_path
    assert layout.data_directory == tmp_path / ".librsi"
    assert layout.artifact_directory.is_dir()
    assert layout.runtime_database.parent == layout.data_directory

    with pytest.raises(ValueError, match="separate"):
        LocalLayout.create(tmp_path, data_directory=tmp_path)
    with pytest.raises(ValueError, match="directory"):
        LocalLayout.create(tmp_path / "missing")


def test_filesystem_snapshot_is_deterministic_and_ignores_local_state(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    source = tmp_path / "src" / "module.py"
    source.write_text("value = 1\n")
    (tmp_path / ".librsi").mkdir()
    (tmp_path / ".librsi" / "runtime.sqlite").write_bytes(b"changing state")
    (tmp_path / "link.py").symlink_to("src/module.py")
    inspector = LocalFilesystemInspector(tmp_path)
    target = inspector.target(target_id="workspace")

    first = inspector.snapshot(target)
    (tmp_path / ".librsi" / "runtime.sqlite").write_bytes(b"different local state")
    second = inspector.snapshot(target)

    assert first == second
    assert first.state["entry_count"] == 2
    assert {entry["type"] for entry in first.state["entries"]} == {"file", "symlink"}

    source.write_text("value = 2\n")
    assert inspector.snapshot(target) != first
    with pytest.raises(ValueError, match="outside"):
        inspector.snapshot(TargetRef(target_id="other", locator={"path": "/elsewhere"}))


def test_filesystem_inspector_ignores_only_configured_descendants(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "kept.txt").write_text("kept")
    ignored = workspace / "generated"
    ignored.mkdir()
    (ignored / "ignored.txt").write_text("ignored")
    inspector = LocalFilesystemInspector(
        workspace,
        ignored_names=(),
        ignored_paths=(ignored, tmp_path),
    )

    snapshot = inspector.snapshot(inspector.target())

    assert tuple(item["path"] for item in snapshot.state["entries"]) == ("kept.txt",)


def test_local_command_runner_preserves_exact_input_and_never_uses_shell(tmp_path: Path) -> None:
    runner = LocalCommandRunner(allowed_roots=(tmp_path,))
    experiment = CommandExperimentInput(
        exact_input_root="exact-root",
        command=(sys.executable, "-c", "print('READY')"),
        cwd=str(tmp_path),
    )

    observation = runner.run(experiment, timeout_seconds=5)

    assert observation.exit_code == 0
    assert observation.stdout == "READY\n"
    assert observation.exact_input_root == "exact-root"
    assert observation.invalid is False


def test_local_command_runner_bounds_authority_and_operational_failures(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    runner = LocalCommandRunner(allowed_roots=(allowed,))

    with pytest.raises(PermissionError, match="outside configured authority"):
        runner.run(
            CommandExperimentInput("outside", (sys.executable, "-V"), str(outside)),
            timeout_seconds=5,
        )

    missing = runner.run(
        CommandExperimentInput("missing", ("definitely-not-a-real-command",), str(allowed)),
        timeout_seconds=5,
    )
    assert missing.invalid is True
    assert missing.exit_code is None
    assert missing.exact_input_root == "missing"

    timed_out = runner.run(
        CommandExperimentInput(
            "timeout",
            (sys.executable, "-c", "import time; time.sleep(2)"),
            str(allowed),
        ),
        timeout_seconds=1,
    )
    assert timed_out.invalid is True
    assert timed_out.stderr == "command timed out"

    with pytest.raises(ValueError, match="positive"):
        runner.run(
            CommandExperimentInput("bad-timeout", (sys.executable, "-V"), str(allowed)),
            timeout_seconds=0,
        )


def test_local_artifacts_are_immutable_scoped_and_content_checked(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    reference = store.put("reports/result.txt", b"accepted", media_type="text/plain")

    assert reference.content_digest is not None
    assert store.get(reference) == b"accepted"
    assert store.put("reports/result.txt", b"accepted") == ArtifactRef(
        artifact_id="reports/result.txt",
        uri=(tmp_path / "artifacts" / "reports" / "result.txt").resolve().as_uri(),
        content_digest=reference.content_digest,
    )

    with pytest.raises(ValueError, match="different content"):
        store.put("reports/result.txt", b"replaced")
    with pytest.raises(ValueError, match="safe relative"):
        store.put("../escape.txt", b"escape")

    (tmp_path / "artifacts" / "reports" / "result.txt").write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="exact digest"):
        store.get(reference)
    with pytest.raises(ValueError, match="configured directory"):
        store.get(
            ArtifactRef(
                artifact_id="reports/result.txt",
                uri=(tmp_path / "elsewhere.txt").as_uri(),
                content_digest=reference.content_digest,
            )
        )


def test_logging_sink_exposes_structured_canonical_transition(caplog) -> None:
    logger = logging.getLogger("tests.librsi.local")
    sink = LoggingTransitionSink(logger)
    transition = _transition()

    with caplog.at_level(logging.INFO, logger=logger.name):
        emit_transitions(sink, (transition,))

    structured = caplog.records[-1].librsi_transition
    assert structured == {
        "run_id": "logged-run",
        "sequence": transition.event.sequence,
        "kind": "action_requested",
        "event_root": transition.event.root,
        "transition_root": transition.root,
        "state_root": transition.next_state.root,
    }
    with pytest.raises(TypeError, match="Transition values"):
        emit_transitions(sink, (object(),))  # type: ignore[arg-type]


def test_local_layout_and_artifact_store_reject_invalid_directory_inputs(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.write_text("file")

    with pytest.raises(TypeError, match="Path"):
        LocalLayout.create(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="directory"):
        LocalLayout.create(tmp_path, data_directory=occupied)
    with pytest.raises(TypeError, match="artifact directory"):
        LocalArtifactStore(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="directory"):
        LocalArtifactStore(occupied)


def test_local_filesystem_inspector_validates_configuration_and_inputs(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="filesystem root"):
        LocalFilesystemInspector(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="directory"):
        LocalFilesystemInspector(tmp_path / "missing")
    with pytest.raises(TypeError, match="ignored names"):
        LocalFilesystemInspector(tmp_path, ignored_names=".git")
    with pytest.raises(ValueError, match="ignored name"):
        LocalFilesystemInspector(tmp_path, ignored_names=("",))
    with pytest.raises(TypeError, match="ignored paths"):
        LocalFilesystemInspector(tmp_path, ignored_paths=str(tmp_path))

    inspector = LocalFilesystemInspector(tmp_path)
    assert inspector.root == tmp_path
    with pytest.raises(TypeError, match="target id"):
        inspector.target(target_id=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="target kind"):
        inspector.target(kind=" ")
    with pytest.raises(TypeError, match="TargetRef"):
        inspector.snapshot(object())  # type: ignore[arg-type]


def test_local_command_runner_validates_configuration_and_boundary_types(
    tmp_path: Path, monkeypatch
) -> None:
    with pytest.raises(TypeError, match="sequence"):
        LocalCommandRunner(allowed_roots=str(tmp_path))
    with pytest.raises(ValueError, match="allowed root"):
        LocalCommandRunner(allowed_roots=())
    with pytest.raises(ValueError, match="identify a directory"):
        LocalCommandRunner(allowed_roots=(tmp_path / "missing",))

    runner = LocalCommandRunner(allowed_roots=(tmp_path, tmp_path))
    assert runner.allowed_roots == (tmp_path,)
    with pytest.raises(TypeError, match="CommandExperimentInput"):
        runner.run(object(), timeout_seconds=1)  # type: ignore[arg-type]
    experiment = CommandExperimentInput("root", (sys.executable, "-V"), str(tmp_path))
    with pytest.raises(TypeError, match="integer"):
        runner.run(experiment, timeout_seconds=True)
    with pytest.raises(ValueError, match="working directory"):
        runner.run(
            CommandExperimentInput("root", (sys.executable, "-V"), str(tmp_path / "missing")),
            timeout_seconds=1,
        )

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("command", 1, output=b"partial", stderr=b"late")

    monkeypatch.setattr("librsi.local.commands.subprocess.run", timeout)
    observation = runner.run(experiment, timeout_seconds=1)
    assert observation.stdout == "partial"
    assert observation.stderr == "late"


def test_local_artifact_and_logging_boundaries_are_explicit(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "artifacts")
    with pytest.raises(TypeError, match="artifact id"):
        store.put(1, b"content")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="required"):
        store.put(" ", b"content")
    with pytest.raises(TypeError, match="content must be bytes"):
        store.put("value.txt", "content")  # type: ignore[arg-type]
    temporary = store.directory / ".value.txt.tmp"
    temporary.write_text("occupied")
    with pytest.raises(ValueError, match="temporary path"):
        store.put("value.txt", b"content")
    with pytest.raises(TypeError, match="ArtifactRef"):
        store.get(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="local file URI"):
        store.get(ArtifactRef(artifact_id="remote", uri="https://example.com/remote"))

    with pytest.raises(TypeError, match="logging.Logger"):
        LoggingTransitionSink(object())  # type: ignore[arg-type]
    sink = LoggingTransitionSink()
    assert sink.logger.name == "librsi.local"
    with pytest.raises(TypeError, match="Transition"):
        sink.emit(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="TransitionSink"):
        emit_transitions(object(), ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="sequence"):
        emit_transitions(sink, "not-a-sequence")  # type: ignore[arg-type]
