# Native meta-meta cascade experiment

**Status: prepared, not run.** This protocol does not contain measured meta-meta
results. The existing README results describe the preceding meta experiment.

This follow-up tests whether improving the **meta optimizer** improves the
ordinary optimizer and, ultimately, the original scheduler. All model calls use
**OpenAI `gpt-6-astra`, high reasoning**. Scheduler execution, measurements and
native review remain deterministic.

The frozen comparison is base → ordinary libRSI → original meta optimizer →
meta-meta-optimized meta optimizer. Every final scheduler starts from the same
original single-start nearest-neighbor scheduler and gets 256 cost evaluations.
No previous final-test results enter model feedback. All new workloads have new
seeds, including a fresh 512-workload final test panel.

## Cascade

1. Astra proposes two revisions to the instruction that generates optimizer
   instruction revisions. Its feedback contains the earlier development records,
   including failed meta proposals, but excludes earlier final-test scores.
2. The original meta instruction and both proposed meta instructions each generate
   two ordinary-optimizer instruction candidates. Each ordinary instruction is
   evaluated through 24 complete native scheduler optimizations: eight training,
   eight shadow and eight verification draws. The unchanged ordinary instruction
   is a shared control. Each of the three child meta passes retains its actual
   accepted instruction, or the original if it rejects both candidates.
3. Fresh sets of 24 native scheduler runs evaluate those retained ordinary
   instructions. A native meta-meta pass compares the resulting cascade utility
   of each meta instruction, with distinct training/shadow/verification draws and
   scoring workloads. Its minimum worthwhile effect is 0.5 percentage points.
4. Propagate the reopened active meta instruction through a **new meta proposal
   and adoption pass**. Run the same fresh propagation with the original meta
   instruction as a control. Both child passes start from the original ordinary
   instruction and share an unchanged control pool, with fresh development data.
5. Freeze both propagated ordinary instructions. Run 32 independent native
   scheduler optimizations for each of three final arms: the original ordinary
   instruction, the original-meta cascade, and the retained-meta-meta cascade.
   Independently score every frozen retained scheduler on the same 512 new test
   workloads. The unchanged base is the zero-improvement reference.

An additional **forced-cascade diagnostic** gets 32 final native runs. It uses
the proposed meta instruction with the best meta-meta training score, then the
ordinary-instruction proposal with the best child training score. Both selections
exclude shadow, verification and final-test scores. This deliberately bypasses
upper-level adoption and is reported separately from the primary cascade.

The primary contrast is retained-meta-meta cascade minus original-meta cascade.
Use 10,000 crossed-bootstrap draws: independent model draws by arm and shared
workloads resampled within each of four workload families. Report a 95% interval.
Other contrasts and the forced cascade are exploratory. This is conditional on
one meta-meta development round and one subsequent propagation per arm; 32 final
draws do not estimate variation across repeated complete meta-meta training runs.
There is no equal-total-compute control or promise of improvement.

## Bounds and accounting

At most 512 new native scheduler runs are needed: 168 for initial child meta
passes, 96 for independent meta-meta evaluation, 120 for fresh propagation, and
128 for final evaluation including the diagnostic. Identical retained ordinary
instructions share their already-frozen development pool within a phase; final
arms always retain their separate 32 model draws. There are also five child meta
passes and one meta-meta pass, all with native review and adoption.

At most **518 logical Astra calls**: the 512 inner proposals, one meta-meta
proposal and five meta proposals. A request that times out without an answer may
be retried once with the identical request, with at most eight extra attempts
across the study (526 attempts maximum). Retain failed receipts and unknown usage.
Invalid completed outputs consume their slots. No outcome-based retries, sample
replacement, optional stopping, or gate relaxation are allowed.

Use the unchanged library runtime and complete durable native stores. Retain
prompts, responses, source hashes, stage adoption records, original roots, costs,
and run-level final scores. Validate completed checkpoints before resuming an
interruption. Two model requests and two native workers may run concurrently.

Reserve **20 GiB of new working space above the host's hard reserve**, based on
the previous run's roughly 31 MiB per durable inner workflow plus conservative
overhead. Check capacity before model calls and between batches. This capacity
requirement does not authorize deleting or compressing retained evidence or
increasing a paid disk without approval.

## Run and audit

On the configured benchmark host, with the required working space available:

```sh
export TMPDIR=/srv/patent-studio/private/tmp
export MPLCONFIGDIR=/srv/patent-studio/private/cache/matplotlib
export UV_CACHE_DIR=/srv/patent-studio/private/cache/uv
/srv/patent-studio/tooling/bin/patent-storage-preflight
.venv/bin/python -u examples/benchmark_meta_meta_sequence.py \
  --output /srv/patent-studio/private/librsi-benchmarks/astra-meta-meta-20261113-run1
```

The runner also checks its 20 GiB requirement before the first model call.
Rerunning the same command resumes validated checkpoints without replacing
completed samples. A failed provider request other than the registered timeout
retry requires diagnosis; a completed report must be audited instead of rerun.

After successful completion, produce the evidence package, CSV, outcome graph
and effort graph without further model calls:

```sh
.venv/bin/python examples/publish_meta_meta_sequence.py \
  --source /srv/patent-studio/private/librsi-benchmarks/astra-meta-meta-20261113-run1 \
  --output /srv/patent-studio/private/librsi-benchmarks/meta-meta-publication-20261113-1
```

The audit replays development and final scores, checks retained native states and
downward instruction bindings, and verifies model receipts and source hashes.
Only audited results should replace this status or enter the README. The optional
forced-cascade arm remains an explicitly labeled diagnostic. Preserve the raw
run and durable stores when copying the compact publication package into the
repository; the compiled `oracle` is a local audit tool, not a publication asset.
