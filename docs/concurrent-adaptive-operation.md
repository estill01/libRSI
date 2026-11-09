# Concurrent serving and adaptive learning

`ConcurrentAdaptiveLoop` runs ordinary tasks while one native learning pass executes
in another host thread. Each task keeps its admitted strategy revision. The host
continues serving the baseline until a verified replacement is published.

This opt-in API uses the same proposals, measurements, independent review,
verification and rollback as [adaptive operation](adaptive-operation.md).
`AdaptiveLoop` and `LearningStore` retain their serialized contracts.

## Use an existing host executor

The following integration fragment assumes the host already supplies `adapter`,
`proposer`, `reviewer`, `policy`, initial configuration, task inputs and held-out
cases as described in the [adapter contract](adaptive-operation.md#consumer-owned-pieces).
The adapter must evaluate each supplied configuration in isolation and support
concurrent calls. The library does not start a background thread or scheduler.

```python
from concurrent.futures import ThreadPoolExecutor

from librsi import ConcurrentAdaptiveLoop, LearningCase, LocalConcurrentLearningStore

with LocalConcurrentLearningStore(
    "./consumer-concurrent-v1",
    profile_id="consumer-v1",
    initial_configuration=initial_configuration,
) as store:
    engine = ConcurrentAdaptiveLoop(
        store,
        adapter=adapter,
        proposer=proposer,
        proposer_id="proposer-v1",
        reviewer=reviewer,
        reviewer_id="reviewer-v1",
        policy=policy,
    )
    for case in initial_tasks:
        engine.run_task(case)

    with ThreadPoolExecutor(max_workers=1) as learner:
        pending = learner.submit(
            engine.learn,
            "pass-001",
            shadow_cases=held_out_cases,
            activate=True,
        )
        feedback = engine.run_task(LearningCase("request-001", request_payload))
        output = feedback.value["output"]
        result = pending.result()
    # The executor has drained before the store closes.
```

`learn()` returns `None` when insufficient unused feedback is available. Its case
bounds, fresh held-out requirements, reflection, follow-ups and activation default
remain unchanged. Use a new task ID for new execution and a new pass ID for a new
learning round. The host decides when to schedule another round and supplies call
timeouts, cancellation, resource limits and exception handling.

An optional `task_adapter=serving_adapter` gives serving separate model/client
resources from learning. It must implement `LearningAdapter`, expose the same
`adapter_id`, and preserve the same execution and scoring semantics. Matching an
ID does not independently establish that two implementations behave identically.

## Serving and publication

| State | `active` | `serving_snapshot` |
| --- | --- | --- |
| Before learning | Current strategy | Same strategy |
| Candidate applied, verification pending | Candidate | Frozen baseline |
| Verified terminal result committed | Verified replacement | Verified replacement |
| Rollback completed | Restored baseline | Baseline |
| Interrupted or unresolved pass | Native observed state | Frozen baseline |

The initial serving revision is the host-supplied starting configuration. Thereafter,
only a verified native result can publish a different revision. An interrupted pass
does not make its candidate available to ordinary tasks. Resume it with the same
pass ID, policy, actors, activation choice and evaluation cases; native workflows
retain application, verification and rollback authority.

Admission pins a task's revision before execution. If publication occurs while that
task runs, its feedback still identifies the original producing revision. A newly
admitted task uses the published revision. Feedback arriving during a pass is
retained for subsequent admission, subject to the existing batch limits and held-out
checks; it cannot change that pass's frozen inputs.

## Split task execution through the machine API

`ConcurrentLearningStore` extends `LearningStore` with `serving_snapshot`,
`learning_owner()`, `admit_task()` and `complete_task()`. A host may dispatch an
admitted task to its own executor and return the measurement to the owning process:

```python
admission = store.admit_task(case, adapter_id=adapter.adapter_id, metric=policy.metric)
cached = store.feedback(case.case_id)
if cached:
    feedback = cached[0]
else:
    snapshot = admission.target_snapshot
    assert snapshot is not None
    measured = adapter.evaluate(snapshot.state, case)
    feedback = store.complete_task(admission, measured)
```

These are typed Python interfaces; no UI is required. The host supplies any remote
transport. Admission durably binds the task ID, exact case, adapter/scoring identities
and serving snapshot. Reusing that ID retains the original admission across restart
or publication; changed inputs or scoring reject. Completion requires the exact
stored admission and a `TaskMeasurement`. Identical completion is idempotent and
conflicting completion rejects. `record_feedback()` keeps its legacy restrictions;
use `complete_task()` for admitted work.

Concurrent duplicate submissions, or a crash before completion is saved, can repeat
external execution. The host must provide external idempotency when needed. A cached
completion returns its original result; it does not rerun against a newer revision.

## Ownership, persistence and limits

`LocalConcurrentLearningStore` supports one owning process with many serving threads
and one learning operation. All calls share one store instance. Short state locks
protect storage operations; model calls execute outside them. The separate
`learning_owner()` fence covers the entire learning/history operation. Overlapping
`learn()` or `history()` calls raise `RuntimeError`; the host may queue them.

The local backend holds a SQLite ownership fence for its lifetime, rejecting another
store instance or process for the same directory. This excludes a second owner;
it does not provide a distributed queue or multiple cooperating writers. Direct
runtime-history access must obey the same owner boundary.

Use a dedicated profile directory on an unsynchronized local filesystem supporting
file and directory `fsync`. This backend uses schema 2. It rejects existing schema-1
profiles, and `LocalLearningStore` rejects schema 2; there is no implicit migration.
Reopen with the same profile ID and original initial configuration, or omit the
initial configuration when reopening. Admissions, feedback, frozen pass inputs and
native runtime history remain available after restart.

Drain ordinary executions and finish or interrupt the learning call before closing.
`close()` rejects an actively owned learning operation; it does not track or drain
task evaluations for the host. Persistence, history validation and finalization can
consume CPU and I/O, so concurrent execution does not promise bounded request latency.
Keep immutable configurations and their referenced resources usable for admitted
tasks until those tasks finish.

Custom backends must implement the complete [concurrency contract](../src/librsi/facade/concurrent_store.py),
including linearizable admission/completion, durable writes and whole-operation
learning ownership. Structural protocol compatibility alone does not qualify these
guarantees. The local behavior is exercised in
[store tests](../tests/test_concurrent_learning_store.py),
[durability fault-injection tests](../tests/test_concurrent_learning_durability.py)
and [native workflow tests](../tests/test_concurrent_adaptive_loop.py).
