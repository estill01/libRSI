"""Completed benchmark evidence survives compaction, interruption, and restoration."""

import json
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
import compact_benchmark_store as compact  # noqa: E402


def fixture(tmp_path):
    store = tmp_path / "store"
    (store / "artifacts").mkdir(parents=True)
    (store / "profile.json").write_text('{"active":"original"}\n')
    (store / "artifacts" / "record.json").write_bytes(b"complete evidence\n" * 10000)
    return store, tmp_path / "archives" / "store.tar.gz"


def test_archive_retains_every_byte_and_validated_restore_can_be_repeated(tmp_path):
    store, archive = fixture(tmp_path)
    original = compact.file_manifest(store)
    receipt = compact.pack_store(store, archive)
    assert not store.exists() and receipt["files"] == original
    assert receipt["archive_bytes"] < receipt["uncompressed_bytes"] / 10
    for _ in range(2):
        with compact.unpacked_store(archive, store) as restored:
            assert compact.file_manifest(restored) == original
        assert not restored.exists()
    assert compact.verify_archive(archive) == receipt


def test_failed_verification_never_removes_original_store(tmp_path, monkeypatch):
    store, archive = fixture(tmp_path)
    original = compact.file_manifest(store)

    def refuse(*args):
        raise ValueError("injected verification failure")

    monkeypatch.setattr(compact, "verify_archive", refuse)
    with pytest.raises(ValueError, match="verification failure"):
        compact.pack_store(store, archive)
    assert compact.file_manifest(store) == original
    assert not archive.exists()


def test_interrupted_removal_finishes_only_for_unchanged_remaining_files(tmp_path):
    store, archive = fixture(tmp_path)
    compact.pack_store(store, archive)
    store.mkdir()
    (store / "profile.json").write_text('{"active":"changed"}\n')
    with pytest.raises(AssertionError, match="working store changed"):
        compact.pack_store(store, archive)
    assert store.exists()
    (store / "profile.json").write_text('{"active":"original"}\n')
    compact.pack_store(store, archive)
    assert not store.exists()


def test_corrupt_archive_fails_before_restore(tmp_path):
    store, archive = fixture(tmp_path)
    compact.pack_store(store, archive)
    data = archive.read_bytes()
    archive.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(AssertionError, match="checksum"), compact.unpacked_store(archive, store):
        pytest.fail("must not yield corrupt evidence")


def test_missing_receipt_is_recovered_without_recompressing(tmp_path):
    store, archive = fixture(tmp_path)
    receipt = compact.pack_store(store, archive)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(store, filter="data")
    archive.with_suffix(".gz.json").unlink()
    assert compact.pack_store(store, archive) == receipt
    assert json.loads(archive.with_suffix(".gz.json").read_text()) == receipt


def test_restore_requires_original_absolute_path_for_native_artifact_references(tmp_path):
    store, archive = fixture(tmp_path)
    compact.pack_store(store, archive)
    with (
        pytest.raises(AssertionError, match="restore path"),
        compact.unpacked_store(archive, tmp_path / "elsewhere"),
    ):
        pytest.fail("would invalidate native artifact references")


@pytest.mark.slow
def test_real_native_inner_run_compacts_and_restores_same_durable_outcome(tmp_path):
    import benchmark_meta_meta_sequence as cascade

    for name in ("native", "runs", "workloads"):
        (tmp_path / name).mkdir()
    oracle = cascade.build_oracle(tmp_path / "oracle")
    problems = cascade.make_problems(tmp_path, "pilot", 940000, oracle, final=True)
    choices = [
        {
            "configuration": {
                "program": json.dumps(
                    {
                        "stages": [
                            {
                                "operators": [operator],
                                "sampling": "scan",
                                "acceptance": "improve",
                                "temperature": 0,
                                "cooling": 1,
                                "restart": "continue",
                                "kick": 0,
                                "weight": 1,
                            }
                        ]
                    }
                )
            },
            "reason": "Offline storage test; no model request",
        }
        for operator in ("swap", "relocate")
    ]
    job = (tmp_path, "storage-test", choices, cascade.BASE_INSTRUCTIONS, problems, "final")
    row = cascade.compact_scheduler_run(job)
    assert not (tmp_path / "stores/storage-test").exists()
    assert cascade.compact_completed_row(job) == row
    assert not (tmp_path / "stores/storage-test").exists()
    receipt = compact.verify_archive(tmp_path / "store-archives/storage-test.tar.gz")
    assert receipt["archive_bytes"] < receipt["uncompressed_bytes"] / 5
    (tmp_path / "native-restoration-proof.json").write_text(
        json.dumps(
            {
                "active_root": row["active_root"],
                "native_root": row["native_root"],
                "full_store_restored_and_reopened": True,
                "archive_bytes": receipt["archive_bytes"],
                "uncompressed_bytes": receipt["uncompressed_bytes"],
            },
            indent=2,
        )
        + "\n"
    )
