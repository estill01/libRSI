# Base, libRSI, and a meta-optimized libRSI improver

This experiment evaluates the **systems retained by completed native libRSI
workflows**. Candidate quality is not substituted for an adopted result.

The three primary cases are:

1. Run the original scheduler.
2. Use the original LLM improver to optimize that scheduler through libRSI.
3. Use an LLM to revise the improver through libRSI, reopen the retained improver,
   then use it to optimize a fresh copy of the **same original scheduler**.

Case 3 never starts from case 2's optimized scheduler. If the outer meta pass
rejects its proposed revision, case 3 uses the retained original improver.

## Model and task

**OpenAI `gpt-6-astra`, high reasoning, via Codex CLI** generates both scheduler
programs and proposed improver instructions. The same model and reasoning setting
are used before and after the meta pass. The native comparison, reviewer and
scheduler execution are deterministic and use no model. libRSI does not select a
default model; the example backend explicitly supplies it. The model identifier is
an alias, not an immutable weight snapshot.

The task is to reduce setup costs in a repeating 14-job production cycle. Costs
are synthetic directed matrices, evenly divided among independent, clustered,
noisy spatial and sparse-cheap-transition families. Each job appears exactly once
and the return transition counts. Cost reduction is `1 - cost / original_cost`,
averaged over workloads and optimization runs.

The original scheduler follows nearest neighbors starting at job 0. This leaves
more room for improvement than the earlier study's best-of-all-starts baseline.
Astra assembles JSON programs using swap, relocation and reversal, different
sampling strategies, acceptance rules and restarts. Each proposed program gets
exactly **256 cost evaluations per workload** and retains its best valid cycle.
The host interprets these primitives; it never executes model-generated source.
An exact dynamic-programming solver supplies an audit reference, not model input.

These are improvements in **synthetic setup cost**, not measured factory
throughput or claims about production scheduling performance.

## Registered comparison

Each inner run begins from the original scheduler, obtains two Astra proposals,
and executes `AdaptiveLoop.learn(..., activate=True)` with native investigation,
comparison, forward-shadow evaluation, review, adoption and verification. It
reopens the durable store and checks the active strategy. Rejected, invalid or
rolled-back proposals leave the original system in the reported outcome.

The two proposals come from one model call. The 32 final runs per arm are
independent repetitions to measure variability, not 32 successive improvement
steps on one scheduler. Meta development is an additional upfront expense.

Training, shadow and verification each contain 32 distinct workloads, grouped
into two native cases of 16. Each group is balanced across the four families.
The inner minimum effect is **0.02**: two percentage points of setup-cost
reduction. These batches make the native workflow affordable; the final analysis
uses individual workloads and independent model draws, not just two case means.

The outer meta pass optimizes an instruction string. Its adapter runs the entire
inner libRSI workflow and measures the retained scheduler. Each outer stage uses
eight independent model draws on distinct evaluation workloads, grouped into two
native cases of four draws. The outer minimum effect is **0.005**: half a
percentage point of additional retained-system cost reduction.

Astra sees only the first eight original-improver development runs when writing
two proposed instruction revisions. Both revisions are evaluated through 24 new
complete native optimizations. The outer pass chooses whether to adopt a revision
using separate training, shadow and verification draws. That is **73 development
calls**: 24 original-improver draws, one instruction-revision call, and 48
revised-improver draws. Neither model nor evaluator receives the final test set
as proposal feedback.

The meta prompt requested instructions no longer than 2,400 characters; the
existing host validator permits up to 3,000. Astra returned 2,601- and
2,841-character instructions. Both passed the frozen host validator and were
used unchanged. This prompt-length shortfall is retained in the transcripts;
neither response was shortened or regenerated.

After the active improver is frozen and reopened, each primary optimization arm
receives **32 independent model draws** on fresh inner training/shadow/verification
partitions. Both arms start from the same original scheduler. All native outcomes
are frozen before evaluation on unseen workloads. The runner initially reserved
128 workloads. Before the meta policy or any final systems were frozen, we
registered an expansion to **512 workloads** (the original 128 plus 384 new
workloads), without adding model calls or optimization runs. The original
128-workload result is also retained. The published comparison uses this
prospectively expanded panel.

If the meta revision is rejected, a prespecified diagnostic additionally runs 32
native optimizations using the proposed instruction with the better outer-training
mean. This is a **forced-instruction diagnostic**, not native meta adoption. It
cannot replace case 3 in the primary comparison.

The primary contrast is after-meta minus ordinary. Its 95% interval uses 10,000
crossed-bootstrap resamples: independent model-draw indices in each arm and
shared workload indices resampled within family. It is conditional on one meta
training run; it does not estimate variability across repeated meta training.
The protocol does not stop early after a favorable outcome or add samples until
significance. There is no equal-total-compute control in this study.

Effort totals cover this experiment's recorded provider calls. Coding and review
work are not metered in those totals, and earlier experiments retain their own
cost ledgers. Dollar billing is unavailable; reported input tokens include cached
input. Setup failures are itemized separately from the main comparison.

## Library correction

This run uses facade evidence mapping version 3. Exact ties have zero weight;
nonzero evidence is weighted by effect magnitude and the total confidence
movement is bounded. Older persisted passes retain their original behavior.
The canonical policies and subsequent acceptance gates are unchanged.
[Full diagnosis and regression details](meta-diagnosis.md#follow-up-versioned-facade-correction).

## Reproduction

From this source checkout, with an authenticated Codex CLI that can access Astra:

```bash
python -m pip install . numpy matplotlib
python examples/run_native_sequence_study.py --output ./native-sequence-run
```

The wrapper registers the 512-workload confirmation before meta development,
runs the native experiment, audits its evidence and creates both graphs. The
individual runner, auditor, confirmation evaluator and plotter are also available
in `examples/`.

A C++17 compiler is required for the exact reference solver. Use a fresh output
directory. The runner bounds model calls to 169, uses two concurrent requests,
and allows 600 seconds per request without automatic retries. Transport failures
retain receipts and stop the run; malformed model outputs consume their slots.
Repeated model requests need not reproduce identical proposals. The offline audit
replays retained-system scores from the recorded proposals and configurations.

If the host interrupts a worker, `python examples/resume_native_sequence.py
--source ./native-sequence-run/raw` validates completed results against their
durable stores and resumes pending native passes with the original samples.
It verifies the original runtime and experiment source hashes and counts saved
model responses once. An unfinished provider request stops recovery for diagnosis.
After recovery, run the auditor, confirmation evaluator and plotter against the
completed raw output, using fresh directories for their artifacts:

```bash
python examples/audit_native_sequence.py --source ./native-sequence-run/raw --output ./native-sequence-run/audit
python examples/extend_native_confirmation.py --source ./native-sequence-run/raw --output ./native-sequence-run/confirmation
python examples/plot_native_sequence.py --report ./native-sequence-run/confirmation/confirmed-report.json.gz --receipts ./native-sequence-run/raw/receipts.json --output ./native-sequence-run/plots
```

The earlier [candidate study](setup-sequence-benchmark.md) and
[recursive scientific-search study](recursive-search-benchmark.md) remain
available with their original evidence. Their results are separate experiments.
