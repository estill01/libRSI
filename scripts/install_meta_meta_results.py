"""Install a completed, audited meta-meta comparison into its registered README."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_publication(source):
    manifest = json.loads((source / "evidence-manifest.json").read_text())
    for name, expected in manifest.items():
        path = (source / name).resolve()
        assert path.is_relative_to(source.resolve()) and sha(path) == expected, name
    report = json.loads(gzip.decompress((source / "report.json.gz").read_bytes()))
    proof = json.loads((source / "validation.json").read_text())
    assert proof["model"] == report["protocol"]["model"] == "gpt-6-astra"
    assert proof["reasoning_effort"] == report["protocol"]["reasoning_effort"] == "high"
    for key in (
        "development_and_final_scores_replayed",
        "primary_bootstrap_replayed",
        "source_hashes_verified",
        "downward_active_instruction_bindings_verified",
    ):
        assert proof[key] is True, key
    assert proof["verified_inner_runs"] == proof["complete_store_archive_hashes_verified"]
    assert proof["verified_inner_runs"] == report["effort"]["native_inner_runs"]
    assert proof["verified_attempts"] == report["effort"]["attempts"]
    assert set(report["scores"]) >= {"ordinary", "after_meta", "after_meta_meta"}
    for arm, grid in report["scores"].items():
        assert len(grid) == 32 and all(len(row) == 512 for row in grid)
        mean = statistics.mean(value for row in grid for value in row)
        assert math.isclose(mean, report["means"][arm], rel_tol=0, abs_tol=1e-14)
    expected_effect = report["means"]["after_meta_meta"] - report["means"]["after_meta"]
    assert math.isclose(expected_effect, report["primary_contrast"]["mean_effect"], abs_tol=1e-14)
    assert report["instructions"]["after_meta"] == report["propagation"]["original_meta"]["active"]
    assert (
        report["instructions"]["after_meta_meta"]
        == report["propagation"]["retained_meta"]["active"]
    )
    if not report["meta_meta"]["adopted"]:
        assert report["meta_meta"]["active"] == report["meta_meta"]["initial"]
    figures = json.loads((source / "figure-values.json").read_text())
    assert figures["means_percent"] == [
        0,
        *[report["means"][a] * 100 for a in ("ordinary", "after_meta", "after_meta_meta")],
    ]
    with (source / "run-scores.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1 + 32 * len(report["scores"])
    assert rows[0]["case"] == "base" and rows[0]["optimizer_model"] == "none"
    for row in rows[1:]:
        arm = row["case"]
        assert row["optimizer_model"] == "gpt-6-astra" and row["reasoning_effort"] == "high"
        assert (row["meta_model"] == "gpt-6-astra") == (arm != "ordinary")
        assert (row["meta_meta_model"] == "gpt-6-astra") == (
            arm in ("after_meta_meta", "forced_cascade_diagnostic")
        )
    return report


def adoption_text(report):
    if report["meta_meta"]["adopted"]:
        top = "The meta-meta pass **adopted a revised meta optimizer**."
    else:
        top = (
            "The meta-meta pass **retained the original meta optimizer**. "
            "This run therefore does not demonstrate a learned meta-meta improvement."
        )
    states = []
    for name, label in (
        ("original_meta", "Original-meta propagation"),
        ("retained_meta", "After-meta-meta propagation"),
    ):
        disposition = (
            "adopted a revised ordinary optimizer"
            if report["propagation"][name]["adopted"]
            else "retained the original ordinary optimizer"
        )
        states.append(f"{label} {disposition}.")
    return top + " " + " ".join(states)


def comparison(report):
    means, effort = report["means"], report["effort"]
    low, high = [100 * v for v in report["primary_contrast"]["bootstrap_95_percentile"]]
    effect = report["primary_contrast"]["mean_effect"] * 100
    tokens = effort["usage"]["input_tokens"] + effort["usage"]["output_tokens"]
    diagnostic = (
        "The separate forced-cascade diagnostic is included in these totals and in the detailed results, not in the four primary rows above."
        if "forced_cascade_diagnostic" in means
        else "No eligible forced-cascade diagnostic was produced."
    )
    return f"""## Base → libRSI → meta → meta-meta

The example reduces setup costs in repeating **14-job production schedules**.
Each final optimization starts from the same original scheduler, with at most
**256 cost evaluations per workload**. Every optimization arm has **32 independent
native libRSI runs**, scored on the same **512 new, unseen synthetic workloads**.

**OpenAI `gpt-6-astra`, high reasoning, drives every optimizer, meta-optimizer and
meta-meta-optimizer call via Codex CLI.** Scheduler execution, scoring and native
review use no LLM. libRSI has no built-in model choice; your backend selects it.

| Case | Model driving optimization | Mean setup-cost reduction vs. base |
| --- | --- | ---: |
| Base scheduler | None | 0.00% |
| libRSI optimizes the base | `gpt-6-astra`, high | {means["ordinary"] * 100:.2f}% |
| Meta → libRSI → base | `gpt-6-astra`, high at both levels | {means["after_meta"] * 100:.2f}% |
| Meta-meta → meta → libRSI → base | `gpt-6-astra`, high at all three levels | {means["after_meta_meta"] * 100:.2f}% |

![Base, libRSI, meta and meta-meta results; gpt-6-astra high at every optimization level](docs/assets/meta-meta-sequence-results.png)

{adoption_text(report)} Independent samples can differ even when their retained
instructions are identical.

Meta-meta cascade minus original-meta cascade: **{effect:+.2f} percentage points**,
with a crossed-bootstrap **95% interval [{low:+.2f}, {high:+.2f}]**. This interval
accounts for model-draw and workload variation, conditional on one meta-meta
training round and one fresh propagation per arm. It does not estimate variation
across repeated complete training rounds or establish equal-compute efficiency.

Total effort: **{effort["attempts"]} model attempts · {effort["logical_calls"]} logical calls ·
{tokens:,} known input/output tokens**. Timed-out attempts: {effort["timeout_attempts"]};
their token usage is unknown. {diagnostic}

![Model effort by stage; gpt-6-astra high at all three levels](docs/assets/meta-meta-sequence-effort.png)

[Methods, adoption records and diagnostic](docs/meta-meta-sequence-benchmark.md) ·
[Run-level CSV](docs/benchmarks/meta-meta-sequence/run-scores.csv) ·
[Audited data and source snapshots](docs/benchmarks/meta-meta-sequence/) ·
[Earlier meta-only experiment](docs/native-sequence-benchmark.md).
These are synthetic setup-cost measurements, not measured factory throughput.

"""


def details(report):
    text = "# Native meta-meta cascade results\n\n" + comparison(report).replace("docs/", "")
    text += "## Native propagation\n\n| Pass | Driver model | Adopted? | Disposition |\n| --- | --- | --- | --- |\n"
    gates = [*report["children"].values(), report["meta_meta"], *report["propagation"].values()]
    for gate in gates:
        text += f"| {gate['label']} | `gpt-6-astra`, high | {gate['adopted']} | {gate['disposition']} |\n"
    text += "\nThe meta-meta gate evaluates each child pass's actual retained optimizer on fresh native runs. The retained meta instruction then drives a new meta pass, which starts from the original ordinary instruction. Final runs use that pass's actual retained instruction.\n\n"
    if "forced_cascade_diagnostic" in report["means"]:
        value = report["means"]["forced_cascade_diagnostic"] * 100
        text += f"## Forced-cascade diagnostic\n\nModel: **gpt-6-astra, high at all three levels**. Mean reduction: **{value:.2f}%**, from 32 separate final native runs. This deliberately bypasses upper-level adoption, choosing the proposed meta policy by its training score, then its proposed ordinary instruction by child training score. All final native scheduler gates still run. It is exploratory and is not an accepted meta-meta update.\n\n"
    effort = report["effort"]
    storage = report["storage"]
    text += f"## Effort and retention\n\n{effort['native_inner_runs']} complete inner workflows and {effort['native_upper_passes']} upper-level passes; elapsed wall time {effort['wall_seconds'] / 3600:.2f} hours. Shared development pools count once. Dollar billing is unavailable through the recorded credentials, not zero.\n\nFull inner stores occupy {storage['archive_bytes']:,} archived bytes versus {storage['uncompressed_bytes']:,} expanded bytes. Every file is retained with SHA-256 verification. Native restoration uses original paths because artifact references contain absolute paths. Complete private archives are retained; the public package includes native records, archive manifests, model prompts/responses, CSV, workload data, source snapshots and audit receipts.\n\n"
    text += "[Frozen protocol](meta-meta-sequence-protocol.md) describes all samples, seed partitions, retries and limits. The model alias does not identify immutable weights. No final-test feedback enters model prompts. Rejected and invalid completed proposals retain their slots.\n"
    return text


def install(source, repository, plan, push=False):
    registration = json.loads(plan.read_text())
    assert sha(Path(__file__)) == registration["installer_sha256"]
    assert str(repository.resolve()) == registration["repository"]
    assert (
        subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=repository, text=True
        ).strip()
        == registration["branch"]
    )
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=repository, text=True
    ).strip(), "worktree changed; preserve it for review"
    for name, expected in registration["source_files"].items():
        assert sha(repository / name) == expected, f"{name} changed; preserve it for review"
    report = load_publication(source)
    subprocess.run(["/srv/patent-studio/tooling/bin/patent-storage-preflight"], check=True)
    artifact_manifest = json.loads((source / "evidence-manifest.json").read_text())
    files = [source / name for name in artifact_manifest] + [source / "evidence-manifest.json"]
    fs = os.statvfs(repository)
    assert (
        fs.f_bavail * fs.f_frsize - 8 * 1024**3
        > sum(p.stat().st_size for p in files) * 3 + 64 * 1024**2
    )
    data = repository / "docs/benchmarks/meta-meta-sequence"
    data.mkdir(exist_ok=False)
    for file in files:
        target = data / file.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(file, target)
        assert sha(target) == sha(file)
    for stem in ("results", "effort"):
        for suffix in ("png", "svg"):
            name = f"meta-meta-sequence-{stem}.{suffix}"
            target = repository / "docs/assets" / name
            assert not target.exists()
            shutil.copyfile(source / "plots" / name, target)
    readme = repository / "README.md"
    old = readme.read_text()
    start, end = old.index("## Base →"), old.index("## Run it")
    old_run = old[end : old.index("## Connect your application")]
    new_run = """## Run it

The [meta-meta protocol](docs/meta-meta-sequence-protocol.md#run-and-audit) gives
the full run and audit commands, model-call bounds and storage requirements.
It requires an authenticated Codex CLI with Astra access and a C++17 compiler.
The [earlier three-case example](docs/native-sequence-benchmark.md) and
[no-model companion](docs/search-benchmark.md) are also available.

"""
    updated = old[:start] + comparison(report) + old[end:]
    readme.write_text(updated.replace(old_run, new_run, 1))
    (repository / "docs/meta-meta-sequence-benchmark.md").write_text(details(report))
    protocol = repository / "docs/meta-meta-sequence-protocol.md"
    content = protocol.read_text()
    marker = content.index("This follow-up tests")
    protocol.write_text(
        "# Native meta-meta cascade experiment\n\n**Status: completed and audited.** [Results and graphs](meta-meta-sequence-benchmark.md).\n\n"
        + content[marker:]
    )
    manifest = repository / "MANIFEST.in"
    content = manifest.read_text().replace(
        "include docs/meta-meta-sequence-protocol.md",
        "include docs/meta-meta-sequence-protocol.md\ninclude docs/meta-meta-sequence-benchmark.md",
    )
    content = content.replace(
        "recursive-include docs/benchmarks *.json *.gz *.xz *.txt *.py *.csv",
        "recursive-include docs/benchmarks *.json *.gz *.xz *.txt *.py *.csv *.md *.png *.svg",
    )
    manifest.write_text(content)
    changed = [
        "README.md",
        "MANIFEST.in",
        "docs/meta-meta-sequence-protocol.md",
        "docs/meta-meta-sequence-benchmark.md",
        "docs/benchmarks/meta-meta-sequence",
        *[
            f"docs/assets/meta-meta-sequence-{s}.{ext}"
            for s in ("results", "effort")
            for ext in ("png", "svg")
        ],
    ]
    subprocess.run(
        ["git", "diff", "--check", "--", ".", ":!docs/assets/*.svg", ":!docs/benchmarks/**/*.svg"],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "add", "--", *changed], cwd=repository, check=True)
    subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--check",
            "--",
            ".",
            ":!docs/assets/*.svg",
            ":!docs/benchmarks/**/*.svg",
        ],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=estill01",
            "-c",
            "user.email=ehs.stillman@gmail.com",
            "commit",
            "-m",
            "Publish audited Astra base, libRSI, meta and meta-meta results",
        ],
        cwd=repository,
        check=True,
    )
    if push:
        subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=!gh auth git-credential",
                "push",
                "origin",
                registration["branch"],
            ],
            cwd=repository,
            check=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    result = install(
        args.source.resolve(), args.repository.resolve(), args.plan.resolve(), args.push
    )
    print(
        json.dumps(
            {
                "readme": "published",
                "means": result["means"],
                "primary_contrast": result["primary_contrast"],
            }
        ),
        flush=True,
    )
