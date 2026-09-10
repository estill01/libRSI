# Adaptive strategy operation

`AdaptiveLoop` connects ordinary consumer work to measured strategy improvement.
`run_task()` loads the active strategy, executes the consumer adapter, and records
its output and score with the exact producing revision. `learn()` uses unused
feedback to request competing revisions, measures them, and runs native
investigation, selection, self-change review, application, verification and rollback.
A verified revision becomes the strategy used by the next ordinary task.

Run the complete offline template after installing libRSI:

```bash
python examples/adaptive_strategy.py --data-dir ./adaptive-demo
```

The [executable template](../examples/adaptive_strategy.py) generates numeric ideas,
measures their distance from a target, derives revisions from the observed failures,
interrupts at a persisted proposal action, resumes, and adopts a verified revision.
It closes and reopens storage again before running a new task. Its JSON output
includes native result and strategy roots, actual initial errors, and the next
result. Running it again reuses the completed work. It needs no optional packages,
credentials, or network access. The deterministic proposer demonstrates the mechanism;
it is not evidence of improved model quality on a production workload.

## Consumer-owned pieces

Use these public imports:

```python
from librsi import (
    AdaptiveLoop, LearningAdapter, LearningCase, LearningPolicy,
    LearningResult, LocalLearningStore, Metric, TaskMeasurement,
)
```

Adapt the template's three small classes:

| Piece | Consumer implementation |
|---|---|
| `LearningAdapter.adapter_id` | Versioned identity of execution and scoring semantics. |
| `validate_configuration(configuration)` | Pure validation of a complete strategy JSON object, including allowed changes. |
| `evaluate(configuration, case)` | Execute that strategy in isolation and return `TaskMeasurement(output={...}, value=score)` from actual output. The same implementation serves ordinary tasks and candidate experiments. |
| `ReasoningBackend.respond(request)` | Return `ReasoningResult.propose(...)` with 2–`max_candidates` hypotheses. Each `causal_model` contains only `{"configuration": complete_replacement}`. Configurations must differ from each other and the baseline. |
| `Reviewer.review(action)` | Review the exact native forward-shadow command and return `make_review_result(...)` or an explicit failed ActionResult. Its actual `reviewer_id` must equal the configured identity and differ from the proposer. |

Use the existing provider-neutral `ReasoningBackend` contract for a model-backed
proposer. Its request includes the active configuration, objective/metric, bounds,
actual task inputs, outputs, scores, and producing strategy identities. Held-out
cases and their observations are absent. Supply domain-specific proposal guidance
in the configured backend; the consumer defines what its strategy fields mean.

An idea-generation application could use a strategy containing a generation prompt
and search settings; its adapter would generate ideas using those fields and score
actual results. A document-authoring application could use its own drafting/search
strategy and independently defined quality measure. Give each consumer separate
profile directories and IDs. This template does not install production integrations
or pool consumers' feedback.

A model or process call belongs inside the adapter/backend, with its own timeout,
token/cost limits and effect isolation. A candidate trial must not mutate the live
consumer or send externally visible messages. Choose a score that captures the
intended improvement; the library cannot infer whether a convenient proxy measures
what the consumer actually values. Change the adapter identity and start a separate
profile when execution or scoring semantics change.

## Ordinary use and scheduling

Construct `AdaptiveLoop(store, adapter=..., proposer=..., proposer_id=...,
reviewer=..., reviewer_id=..., policy=...)`. Keep a stable, versioned proposer and
reviewer identity across restart. The strategy is a nonempty JSON object whose
revision is content-addressed; no new database schema or model training service is
needed.

```python
# Within the host's existing job execution:
feedback = engine.run_task(LearningCase(job_id, task_input))
actual_output = feedback.value["output"]

# From the host's existing periodic/batch job, under the same serialized owner:
result = engine.learn(
    batch_id,
    shadow_cases=held_out_cases,
    activate=True,
)
if result is not None:
    print(result.disposition, result.strategy_after.root)
```

`learn()` returns `None` when fewer than `min_new_feedback` unused observations
exist. Defaults allow one proposal call, two candidates, and at most eight feedback
and evaluation cases per set. An enabled reflection adds at most one reasoning
call per pass. For training count N, shadow count S, verification
count V and candidate limit K, a complete pass makes at most
`(K + 3) * N + 2 * S + 2 * V` adapter evaluations and one independent review.
The default ceiling is 72 adapter evaluations. Ordinary tasks each make one call;
recorded work is reused on resume. These are call-count allowances, not dollar or
wall-clock limits. Native history validation has noticeable CPU/storage cost, so
run learning as a small background batch, outside ordinary request latency.

Provide at least two distinct cases per evaluation set, up to `max_cases`.
Forward-shadow case IDs **and payloads** must differ from training inputs; renaming
training data does not make it held out. Optional `verification_cases` run after
application; otherwise verification executes the shadow cases again with fresh
measurements. Every new pass requires evaluation IDs and payloads disjoint from
all earlier training/evaluation sets. Earlier held-out cases also cannot become
later proposal training, including through selected legacy history. These checks
apply even when history is disabled; exact replay of a saved pass is unchanged.
One scalar objective
and a positive minimum effect are supported by this convenience layer; use the
expert contracts for multiple objectives or additional guardrails.

`activate` defaults to `False`. Native disposition `activation-disabled` reports
completed evaluation with the original active strategy. Only `verified` makes
`LearningResult.adopted` true. Rejected/inconclusive revisions preserve the baseline;
failed post-application verification attempts native rollback. A result with
unresolved strategy authority leaves the pass pending and ordinary work blocked.
Inspect and reconcile the native result/actual target before resuming that profile.

## Restart, history and boundaries

When the host only needs to compare completed trials, use the
[stateless comparison boundary](stateless-comparison.md). It consumes exact
canonical records and emits an advisory selection without constructing a profile
or a runtime store. This keeps host-owned graph state out of per-worker stores.

`AdaptiveLoop` accepts the public, runtime-checkable `LearningStore` protocol.
`LocalLearningStore` is the included filesystem/SQLite implementation; consumers
can supply another implementation without subclassing it. Import the protocol
from `librsi` or `librsi.facade`. The loop uses no directory or artifact-store API
and does not own or close the supplied store's connections.

The [persistence contract](../src/librsi/facade/learning_store.py) covers current
strategy snapshots, ordered feedback, immutable pass inputs and completed work,
the pending pass, and application/rollback compare-and-swap. Its `runtime` property
must implement the existing `RuntimeStore` contract, including canonical history
validation and replay. A backend must preserve exact profile and record identities,
reject stale or conflicting writes, and durably save completed work before returning.
Application must commit the active strategy and exact action identity together so
the same effect can recover after an interruption without accepting a stale effect.
Passing the structural protocol check does not certify those backend semantics.

This extension supplies a persistence boundary, not distributed coordination.
The host must serialize and, across processes, fence **all** use of one profile,
including ordinary tasks, learning, effects, and recovery. Per-method locking alone
does not protect a complete operation. Reopening must recover the same strategy,
pending input, completed records, and runtime history; independent per-worker
stores are separate profiles, not replicas of a shared authority. Native workflows
still decide acceptance and application eligibility. Consumers must additionally
enforce their own authority at the actual effect boundary.

The consumer-adapter restart and rollback cases in
[`tests/test_adaptive_loop.py`](../tests/test_adaptive_loop.py) exercise the same
workflow assertions through a non-subclass adapter. That adapter delegates durable
storage to the included local backend; it proves substitutability, not a remote
backend's atomicity or fencing. Qualify those guarantees against the actual backend
before shared use.

Use one serialized owner per directory. On restart, reopen `LocalLearningStore`
with the same profile ID and construct the same adapters/policy. Resume the pending
pass with the same pass ID, activation choice and evaluation cases. Its inputs are
frozen; changing any of them rejects. A completed pass ID returns its historical
native result, which need not be the currently active strategy after later passes.
Use a new pass ID and fresh unused feedback for another learning round. Failed
passes also consume their batch. An explicit bounded follow-up can reuse that
training batch as described below; the loop does not schedule or retry itself.

A repeated task ID with identical input/scoring returns the original feedback, even
if the active strategy later changes. Different input under that ID rejects. Use a
new task ID for a new execution. The profile retains old revisions, feedback and
pass artifacts; native runtime history remains in `runtime.sqlite`, and immutable
records live in `artifacts/`. Histories are intended to stay small; no retention or
cross-process coordination service is included.

Native actions are persisted before execution and completed host results before
submission. Local strategy application is an idempotent compare-and-swap tied to
its exact native action, including recovery after the pointer changed but its
receipt was not recorded. Arbitrary external calls can repeat after a crash before
their result is saved; consumers should make those operations idempotent where
needed. Cached results do not grant approval: native workflows own acceptance,
currentness and rollback decisions throughout.

This operation improves host-supplied strategy configurations/prompts used by
ordinary tasks. It does not train model weights, rewrite libRSI's fixed evaluation
or governance rules, schedule itself, or deploy a consumer. Improving the proposal
strategy can improve future ideas; whether it does so must be established by the
consumer's real measurements across learning rounds.

## Inspecting failures and improving proposals

This functionality belongs to libRSI and works with any compatible consumer.
It requires no Graphy Capability, graph database or host-specific service.

`engine.history(limit=2)` returns `LearningAttempt` values. An attempt exposes its
exact frozen inputs, proposal, optional reflection, native `LearningResult`,
submitted operations and training measurements. `disposition` distinguishes a
pending attempt, provider failure, unsupported revision, rejected governance,
disabled activation, rollback and verified adoption. A historical verified result
does not assert that its revision is still active. New inputs carry a logical
sequence; old inputs have unknown chronology and deterministic identity ordering.

`attempt.feedback` is a separate training-only projection: configurations,
hypotheses, actual training outputs/scores, safe disposition/failure classes and
source references. It excludes nested native result trees, held-out records and
free-form failure/reviewer text. New-pass admission additionally checks that the
selected historical training never overlaps retained evaluation sets. If legacy
training was mixed with evaluation data, omit that history or use a separate
profile; old exact replay does not rewrite those records. The full operator view
is unsuitable for direct model context. A failure classification or rejection is
an observation, not a proven causal explanation.

`LearningPolicy` provides three settings:

| Setting | Default | Meaning |
|---|---:|---|
| `history_limit` | 2 | Maximum compatible earlier attempts frozen into a new proposal's context; zero disables automatic history context. |
| `reflect_on_failure` | `False` | Request one typed reflection before proposing when retained history includes an unsuccessful attempt. |
| `max_followups` | 1 | Maximum inherited follow-up depth; zero disallows follow-ups. Each predecessor can have only one successor. |

History compatibility requires the same current baseline, adapter, objective,
metric and minimum effect. Reflection uses the configured `ReasoningBackend` with
the existing `reflection` kind; that backend must support both reflection and
hypothesis generation when enabled. The reflected explanation remains a proposal,
with no evidence or activation authority. A failed/malformed reflection ends the
pass before another proposal call. Exact completed calls are reused after restart.

After configuring the policy, the host can request:

```python
result = engine.learn(
    "follow-up-1",
    follow_up_to="unsuccessful-pass",
    shadow_cases=fresh_held_out_cases,
    activate=False,
)
```

The predecessor must be completed and unsuccessful, still share the current
baseline/scoring, retain an available follow-up allowance, and have no successor.
Adoption and activation-disabled success are not failed-predecessor retries.
Training is reused explicitly, while shadow/verification cases must be fresh.
Changing any frozen options, identities or cases under the same pass ID rejects.
Old persisted passes recover with their old request/policy shape when the new
options have default values; finish their replay before enabling different options.

New learning-pass host calls retain wall and process CPU durations. Action timing
is inclusive `host-action-inclusive` metadata; adapter measurement/failure timing
has `adapter-call` scope. These durations overlap and must not be added together.
Provider usage and child-process CPU remain unknown unless supplied elsewhere by
the host. Full record bytes retain action metadata, which is not part of semantic
identity. Old missing timing is unknown, not zero. Only submitted actions appear in
the native operation view; a crash before submission does not prove a host effect
was absent. Ordinary task exceptions retain their existing propagating behavior.

## Improving a proposal generator itself

Run the standalone [failure-informed example](../examples/failure_informed_proposals.py):

```bash
python -I examples/failure_informed_proposals.py --data-dir ./proposal-demo
```

Its adaptive target is the configuration of a repair-proposal generator. The
adapter executes each generated program against frozen scoring probes and measures
the fraction of distinct proposals that improve correctness, under an equal
two-proposal budget. The first attempt varies offset estimators and is rejected.
Reflection inspects the actual failed measurements for nonconstant residuals,
then proposes a different model family. Fresh outer held-out problems, native
independent review, explicit adoption, restart and new ordinary work must establish
the benefit. A valid control removes historical failure feedback/reflection and
measures the resulting proposals separately. It grants no native acceptance.

The example saves complete evidence in its data directory and reports partial
operation timing plus whole-invocation wall/process CPU, including admission,
history inspection and control execution. Equal proposal budgets do not imply
equal CPU cost. It uses deterministic input-driven reasoning on a synthetic affine
program domain; it does not establish better LLM ideas or production performance.
To use a real model, replace the backend/adapter and qualify the generator against
the consumer's actual downstream outcomes. No model weights or fixed library
evaluation/governance rules are trained or changed.
