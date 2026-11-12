# Why the first meta passes did not help

The search revisions failed to generalize. A separate follow-up also exposed a
library limitation: the adaptive facade can discard useful average improvements
before statistical comparison because it treats tied cases as counterexamples.
These are distinct findings; fixing that gate would not make the six losing
search revisions beneficial.

[Replay data, native controls, pilot receipts and source snapshots](benchmarks/meta-diagnosis/)
are retained with a [SHA-256 manifest](benchmarks/meta-diagnosis/evidence-manifest.json).

## What happened in search

Every original reasoning call used **OpenAI `gpt-6-astra`, high reasoning**. The
baseline proposer already generated familiar, effective lexical ranking formulas.
The meta prompts mostly turned a promising development formula into a rigid recipe.
Several recipes returned the same selected formula in all five samples. Repeating
a recipe consistently did not make it generalize.

The replay below executes the saved formulas on the original scoring, shadow and
previously reserved verification partitions. It makes **no new model calls**.
Effects are MRR@5 × 100 points relative to the default proposer at that depth.

| Candidate policy | Source model | Development effect | Shadow effect | Verification effect |
| --- | --- | ---: | ---: | ---: |
| Meta, candidate 1 | `gpt-6-astra`, high | −0.72 | −1.56 | −1.23 |
| Meta, candidate 2 | `gpt-6-astra`, high | −1.08 | −0.91 | −0.88 |
| Meta-meta, candidate 1 | `gpt-6-astra`, high | +1.07 | −1.30 | −0.99 |
| Meta-meta, candidate 2 | `gpt-6-astra`, high | +1.29 | −2.05 | −2.14 |
| Meta-meta-meta, candidate 1 | `gpt-6-astra`, high | +0.71 | −1.58 | −1.24 |
| Meta-meta-meta, candidate 2 | `gpt-6-astra`, high | +1.21 | −1.27 | −2.63 |

All six candidates have negative mean effects on both held-out partitions.
The meta-meta candidate that reached shadow was rejected there. The strongest
meta-meta-meta training candidate was stopped earlier by the uncertainty bound;
this replay shows that allowing it through would not have repaired its transfer.
Increasing repetitions or lowering the threshold alone would not establish a
useful improvement on these workloads.

The default policies selected 4, 5 and 5 distinct formula strings at the three
depths. Five of the six revised policies selected one string across all five
samples; the other selected two strings but had identical mean scores in all
five samples. Different strings can still describe equivalent rankings, so these
are diversity diagnostics, not a count of distinct algorithms.

The problem was narrower than “improve an improver” in general: one corpus,
four lexical variables, two formula slots, a single instruction revision per
level, and repeated feedback from the same development partitions. There was
little scope to change data collection, the experimental budget, or the search
procedure itself. Adding prompt-writing layers did not add useful feedback.

## What libRSI did

For candidates that reach comparative evaluation, the saved effects agree with
the native calculation. The adaptive self-change policy uses mean ± **one standard error**, then compares the conservative effect
bound with the configured minimum effect. Its `student-standard-error` record
name is not a claim of a 95% confidence interval. The five observations in the
old harness represented model draws on a fixed query set; they did not measure
uncertainty from sampling a new query population.

For example, the best third-level training effect was +1.21 points with a
conservative bound of +0.86, below the required +1.00. The second-level selected
candidate's shadow effect was −2.05 points. These are expected rejections under
the configured policy, not evidence that a supported positive result was lost.

Four controls also exercised the actual `AdaptiveLoop`, persisted state,
subsequent task consumption, and reopening the store. They used measured join-plan
costs with an exact dynamic-programming reference. **No model was used for these
controls**; their purpose was to isolate the library's mechanics.

| Controlled case | Model | Native result | Saved state and next task |
| --- | --- | --- | --- |
| Known improvement on all partitions | None | `verified` | Uses the improved strategy |
| Known worse strategy | None | `no-supported-revision` | Keeps the prior strategy |
| Gain appears only on training | None | `governance-rejected` | Keeps the prior strategy |
| Gain disappears at verification | None | `rolled-back` | Restores the prior strategy |

The first control-harness attempt supplied one hypothesis; the adaptive facade
requires at least two. It failed before an experiment. The corrected harness
supplies a second distinct reference configuration. That setup failure is retained
separately; it was not a failure of the earlier search experiment.

## The additional investigation gate matters

The four controls above have unambiguous gains or losses. They did not test sparse
improvement with many ties. The new scheduling study revealed that missing case.
Its first ordinary proposal improved seven of 16 scoring workloads, tied nine,
and worsened none. Mean setup-cost reduction was **5.06%**, with a native-style
one-standard-error lower bound of **3.38%**, above the agreed 2% minimum.
Nevertheless, it received `no-supported-revision` before comparative evaluation.
The other proposal also had seven wins and nine ties, averaging 3.93% with a 2.60%
lower bound, and stopped at the same earlier stage.

In [`LearningHost.experiment()`](../src/librsi/facade/learning_host.py), every
strictly positive case becomes `support`; every other case, including exact
equality, becomes `counterexample`. The investigation policy applies bounded
linear confidence updates to those signs in evidence-root order. Effect magnitude
does not enter that gate. Only supported branches reach comparison of the mean.
Consequently, this gate is not equivalent to the configured average-effect
objective, and more tied cases can make acceptance harder.

There is also order sensitivity. For the observed seven supports and nine
counterexamples, replaying all 11,440 distinct sign orderings through the unchanged
linear aggregator yields 544 `supported` outcomes; the others are rejected or
remain unresolved. Final confidence ranges from zero to one, despite identical
mean improvement. These counts describe possible orderings, not probabilities
for actual evidence hashes. The native policy sorts by evidence root, while the
linear update clips after each item. That combination can make record identity
affect the early decision. The saved ordinary-pass records and
[`audit_setup_sequence.py`](../examples/audit_setup_sequence.py) preserve this
post-hoc calculation separately from the confirmatory comparison.

A [model-free diagnostic](../examples/check_sparse_adoption.py) isolates that
behavior with measured join costs: four improvements, 12 ties, no regressions.
The mean gain is 25%, with a one-standard-error lower bound of 13.82%, versus a
1% minimum. The current facade still returns `no-supported-revision`. The
diagnostic also tests an isolated treatment that labels exact ties as neutral,
with the required zero evidence weight. That treatment reaches **`verified`**
and adopts the same sparse improvement. Unchanged and worsening controls are
also included and remain unadopted.

| Control | Model | Training outcomes | Native result |
| --- | --- | --- | --- |
| Current tie handling | None | 4 wins, 12 ties, 0 losses | `no-supported-revision` |
| Neutral ties, zero weight | None | 4 wins, 12 ties, 0 losses | `verified` |
| Neutral ties, worse candidate | None | 0 wins, 0 ties, 16 losses | `no-supported-revision` |
| Neutral ties, unchanged candidate | None | 0 wins, 16 ties, 0 losses | `no-supported-revision` |

[Control results](benchmarks/meta-diagnosis/sparse-tie-controls.json) and
[ordinary-pass order diagnostic](benchmarks/meta-diagnosis/ordinary-gate-diagnosis.json)
include the measured values and native record identities.
The first diagnostic treatment accidentally retained weight one
for neutral evidence and failed validation; that setup error is retained separately.
The corrected diagnostic does not alter library source or the
registered Astra experiment. This is a targeted facade limitation, not evidence
that every native adoption or rollback path is broken.

The two actual native scheduling passes also proposed identical program
configurations with identical scores, but different hypothesis text and record
identities. The first pass stopped at investigation. In the later pass, the
3.93% candidate reached selection, then failed forward governance; the 5.06%
candidate again stopped earlier. The later pass therefore still kept the original
planner. This is not a successful meta improvement. It demonstrates why model
variability and native decision variability must be diagnosed separately.

Neutral ties are a useful isolated correction, but not a complete solution for
mixed wins and losses: the sign-based gate still ignores effect magnitude and
uses order-sensitive clipping. A production change needs explicit, replay-safe
semantics for that gate and regression coverage for pending and historical passes.
This investigation leaves those library semantics unchanged.

## What the follow-up changes

The [production-sequencing study](setup-sequence-benchmark.md) gives Astra a larger
decision space: assemble bounded search programs, including move operators,
sampling, acceptance, restarts and allocation of a fixed evaluation budget. Every
reasoning role in the main study uses **`gpt-6-astra`, high reasoning**.

It begins with a broad goal. Astra proposes a measurable interpretation, a
minimum worthwhile effect, a no-worthwhile-improvement comparison and competing
experimental hypotheses. The host validates the proposal, supplies the measurable
workload and constrained execution language, and records a native operationalization
proposal/result. Those agreed criteria drive the experiments.

Confirmation separates 32 independent model-generation draws from 128 independent
workloads. It tests the frozen proposed policy even if native governance declined
to adopt it, so rejection is not confused with zero candidate benefit. A second
comparison spends the same total number of Astra calls using the original
improver. Both model-draw and workload variation enter the reported uncertainty.

These are benchmark-level methods. libRSI does not automatically supply a complete
null-hypothesis testing system, multiplicity correction, representative datasets,
or useful hypotheses merely because the package is installed.

## Replay

```bash
python examples/diagnose_meta_search.py --dataset ./scifact.zip --output ./diagnosis.json
python examples/check_meta_adoption.py --output ./native-controls
python examples/check_sparse_adoption.py --output ./sparse-controls
```

The query-bootstrap intervals in the diagnostic JSON are post-hoc, condition on
the five saved model draws, and resample queries. They are not independent
confirmation of a policy chosen using this replay. The new scheduling study does
not use these search judgments as training or test data.

Task-selection pilots consumed 32 attempted model calls: 24 Astra/high and eight
Luna/low. There were 31 completed calls with 335,601 reported input/output tokens;
the one Astra timeout has no final usage receipt. These costs are additional to
the search runs and scheduling confirmation. The
[pilot ledger](benchmarks/meta-diagnosis/pilot-ledger.json) retains unsuccessful
and saturated tasks as well as useful ones. Luna appears only in that discarded
calibration, not in the main study.
