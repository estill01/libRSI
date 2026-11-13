"""Losslessly archive closed benchmark stores; validate temporary restores."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_manifest(directory):
    files = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f"Unexpected store entry: {path}")
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": file_hash(path),
            }
    return files


def verify_archive(archive, expected=None):
    """Read every archived byte, reject links/unsafe names, and verify all files."""
    if expected is None:
        expected = json.loads(archive.with_suffix(".gz.json").read_text())
    assert file_hash(archive) == expected["archive_sha256"], "archive checksum mismatch"
    found, names = {}, set()
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or member.name in names:
                raise ValueError("Unsafe or duplicate archive entry")
            names.add(member.name)
            if member.isfile():
                stream = tar.extractfile(member)
                assert stream is not None
                fingerprint = hashlib.sha256()
                while block := stream.read(1024 * 1024):
                    fingerprint.update(block)
                found[member.name] = {
                    "bytes": member.size,
                    "sha256": fingerprint.hexdigest(),
                }
            elif not member.isdir():
                raise ValueError("Archive must contain only regular files and directories")
    assert found == expected["files"], "archive file manifest mismatch"
    return expected


def pack_store(directory, archive):
    """Call only after the native store closes and its durable outcome is saved.

    Publish and verify the archive before removing its expanded working copy.
    An interruption during removal is recoverable from the complete archive.
    Existing archives are immutable; changed working files are retained on error.
    """
    directory, archive = Path(directory), Path(archive)
    receipt_path = archive.with_suffix(".gz.json")
    if receipt_path.exists():
        receipt = verify_archive(archive)
        assert receipt["store_path"] == str(directory.resolve())
    else:
        files = file_manifest(directory)
        if not files:
            raise ValueError("Cannot archive a missing or empty store")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            temporary = archive.with_suffix(".gz.partial")
            if temporary.exists():
                raise RuntimeError(f"Unfinished archive requires diagnosis: {temporary}")
            with tarfile.open(temporary, "w:gz", compresslevel=6) as tar:
                for path in sorted(directory.rglob("*")):
                    tar.add(path, arcname=path.relative_to(directory).as_posix(), recursive=False)
            with temporary.open("rb") as stream:
                os.fsync(stream.fileno())
        else:
            # A process may have stopped after the archive rename but before its receipt.
            temporary = archive
        receipt = {
            "schema": 1,
            "store_path": str(directory.resolve()),
            "files": files,
            "uncompressed_bytes": sum(row["bytes"] for row in files.values()),
            "archive_bytes": temporary.stat().st_size,
            "archive_sha256": file_hash(temporary),
        }
        verify_archive(temporary, receipt)
        if temporary != archive:
            temporary.replace(archive)
        pending_receipt = receipt_path.with_suffix(".json.partial")
        with pending_receipt.open("w") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        pending_receipt.replace(receipt_path)
        # Make both names durable before removing the expanded copy.
        descriptor = os.open(archive.parent, os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    if directory.exists():
        remaining = file_manifest(directory)
        assert all(receipt["files"].get(name) == row for name, row in remaining.items()), (
            "working store changed; preserve it for diagnosis"
        )
        shutil.rmtree(directory)
    return receipt


@contextmanager
def unpacked_store(archive, directory):
    """Keep the archive authoritative; discard only a successfully checked restore."""
    archive = Path(archive)
    directory = Path(directory)
    receipt = verify_archive(archive)
    # Native artifact references include absolute paths. Preserve the original
    # path as well as the bytes; caller owns this completed run exclusively.
    assert receipt["store_path"] == str(directory.resolve()), "restore path must match original"
    directory.mkdir(parents=True, exist_ok=False)
    # Failed restores stay in this directory for diagnosis.
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(directory, filter="data")
    assert file_manifest(directory) == receipt["files"]
    yield directory
    assert file_manifest(directory) == receipt["files"], "restored store changed; preserve it"
    shutil.rmtree(directory)
