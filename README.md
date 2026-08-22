![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

`libRSI` is a zero-dependency Python library of evidence-bound primitives for
validation, investigation, improvement, and governed recursive self-improvement.
The current package supplies deterministic policies and canonical records for
reflection, hypothesis testing, experiment interpretation, program evolution,
reviewed selection, and safe changes to the selector itself, plus typed ports for
host-owned effects. Targets may be opaque or multi-component, and generic currentness
checks keep stale target-bound evidence distinguishable from current evidence without
requiring repository or Git concepts.
Canonical knowledge can be persisted through a replaceable `KnowledgeStore` contract;
the included transactional SQLite backend needs no service and labels retrieved
target-bound records as current, stale, unbound, or incomparable.
An independent `librsi.runtime` package provides canonical Run/Event/State/Action
records, a pure deterministic transition engine, and an opt-in `RuntimeStore` with a
replay-checked SQLite implementation. It emits exact actions but does not resolve or
execute capabilities.

## Install

From GitHub:

```bash
python -m pip install "librsi @ git+https://github.com/estill01/libRSI.git@v0.2.0"
```

For development:

```bash
git clone https://github.com/estill01/libRSI.git
cd libRSI
python -m pip install -e '.[dev]'
python -m pytest
```

## Example

The canonical hypothesis/experiment path binds the proposition, target snapshot,
experiment criteria, execution input, observation, and resulting evidence by exact
immutable record identity:

```python
from librsi import CommandObservation, RSIKernel, TargetRef, TargetSnapshot

rsi = RSIKernel()
target = TargetRef(target_id="my-system", kind="software")
baseline = TargetSnapshot(
    target=target,
    revision="abc123",
    state={"revision": "abc123"},
)

hypothesis = rsi.hypotheses.create(
    target=target,
    statement="The new scheduler reduces queue latency",
    causal_model={"change": "fair scheduling"},
    predictions=({"p95_latency_delta": "< 0"},),
)
spec = rsi.experiments.design_command(
    experiment_id="latency-comparison-1",
    hypothesis=hypothesis,
    target_snapshot=baseline,
    design={"kind": "isolated comparison"},
    success_criteria={"accepted_exit_codes": [0], "stdout_contains": ["IMPROVED"]},
    command=["python", "compare_latency.py"],
    cwd="/workspace",
)
command = rsi.experiments.prepare_command(spec)

# A host-owned runner executes `command` and echoes its exact input root.
observation = CommandObservation(
    exit_code=0,
    stdout="IMPROVED\n",
    stderr="",
    exact_input_root=command.exact_input_root,
)
evidence = rsi.experiments.evaluate_command(spec=spec, observation=observation)
updated = rsi.hypotheses.apply(hypothesis=hypothesis, evidence=evidence)
```

`evaluate_command()` reads its decision criteria from the immutable `ExperimentSpec`;
callers cannot replace them after execution. It also rejects observations that do not
echo the exact spec/input root. Evidence names the exact hypothesis, experiment, and
target snapshot it bears on, and a stale or different hypothesis rejects that evidence.
The `0.2.0` scalar APIs remain available as deprecated compatibility wrappers.

A host can durably record the same semantic run after each pure transition:

```python
from librsi import Action, Goal, Run, RuntimeEngine, SQLiteRuntimeStore

run = Run(run_id="validation-1", intent=Goal(statement="Validate candidate").ref)
started = RuntimeEngine.start(run)
requested = RuntimeEngine.request(
    started.state,
    Action(run=run.ref, action_id="evaluate", kind="evaluate"),
)
assert started.transition is not None
assert requested.transition is not None

with SQLiteRuntimeStore("runtime.sqlite") as store:
    store.append(started.transition)
    store.append(requested.transition)
    continuation = store.resume(run.run_id)

assert continuation is not None
# The host executes continuation.pending_actions through its own governed adapter.
```

`RuntimeEngine` performs no I/O. Exact duplicate transitions are no-ops, while every
load validates the append-only chain, materialized state, and deterministic replay.
The runtime and knowledge stores remain distinct authorities and may optionally share
one SQLite file without sharing schema versioning or record types.

The library performs no target, provider, subprocess, filesystem, or dispatch effects.
Persistence is opt-in through explicitly constructed stores; `RSIKernel` does not open
a database or infer a storage location. See
[`src/librsi/README.md`](src/librsi/README.md) for the module map and complete
integration boundary. The maintained implementation plan evolves this deterministic
core toward higher-level validation, investigation, improvement, and RSI workflows
without making libRSI a general-purpose agent/orchestration infrastructure platform.
Maintainers should begin with the canonical [`docs/tracker.md`](docs/tracker.md).

## Development guarantees

- Python 3.11 or newer;
- no runtime dependencies;
- typed public API (`py.typed`);
- deterministic policy decisions for identical inputs; and
- at least 90% branch coverage in CI.
