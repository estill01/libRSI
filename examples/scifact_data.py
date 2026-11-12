"""Download and read BEIR SciFact without redistributing the upstream corpus.

    python examples/scifact_data.py --download /path/to/scifact.zip

Source: https://github.com/beir-cellar/beir/wiki/Datasets-available
The published archive's MD5 is 5f7d1de60b170fc8027bb7898e2efca1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip"
SHA256 = "536e14446a0ba56ed1398ab1055f39fe852686ecad24a6306c80c490fa8e0165"
SEED = 20261111


def download(path: Path) -> None:
    if path.exists():
        verify(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=60) as response:
        contents = response.read(4 * 1024 * 1024)
    if hashlib.sha256(contents).hexdigest() != SHA256:
        raise ValueError("download does not match the pinned SciFact archive")
    with path.open("xb") as handle:
        handle.write(contents)


def verify(path: Path) -> None:
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise ValueError("dataset does not match the pinned SciFact archive")


def load(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    verify(path)
    with zipfile.ZipFile(path) as archive:
        documents = [json.loads(row) for row in archive.read("scifact/corpus.jsonl").splitlines()]
        queries = {
            row["_id"]: row["text"]
            for line in archive.read("scifact/queries.jsonl").splitlines()
            if (row := json.loads(line))
        }
        qrels: dict[str, list[str]] = {}
        split_ids = {}
        for split in ("train", "test"):
            ids = set()
            for line in archive.read(f"scifact/qrels/{split}.tsv").decode().splitlines()[1:]:
                query, document, score = line.split("\t")
                if int(score) > 0:
                    qrels.setdefault(query, []).append(document)
                    ids.add(query)
            split_ids[split] = sorted(ids, key=int)
    if set(split_ids["train"]) & set(split_ids["test"]):
        raise ValueError("upstream train/test overlap")
    training = split_ids["train"][:]
    random.Random(SEED).shuffle(training)
    splits = {}
    offset = 0
    for prefix, size in (("meta", 200), ("ordinary", 60)):
        for part in ("train", "shadow", "verification"):
            splits[f"{prefix}_{part}"] = training[offset : offset + size]
            offset += size
    splits["unused_train"] = training[offset:]
    splits["test"] = split_ids["test"]
    manifest = json.loads((Path(__file__).parent / "data/scifact-split.json").read_text())
    if manifest != {"archive_sha256": SHA256, "seed": SEED, "splits": splits}:
        raise ValueError("generated split differs from the frozen benchmark manifest")
    corpus = {
        "source_repository": "https://github.com/beir-cellar/beir",
        "source_revision": SHA256,
        "documents": [
            {"path": row["_id"], "text": f"# {row['title']}\n{row['text']}"} for row in documents
        ],
    }
    dataset = {
        "splits": splits,
        "queries": {
            key: {"id": key, "query": queries[key], "relevant": sorted(qrels[key])} for key in qrels
        },
        "archive_sha256": SHA256,
        "seed": SEED,
    }
    all_ids = [key for ids in splits.values() for key in ids]
    if len(all_ids) != len(set(all_ids)) or len(splits["test"]) != 300 or len(training) != 809:
        raise ValueError("SciFact split contract changed")
    return corpus, dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", type=Path, required=True)
    download(parser.parse_args().download)
