![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

`libRSI` is a zero-dependency Python library for bounded recursive
self-improvement. It supplies pure policies for reflection, hypothesis testing,
experiment interpretation, program evolution, reviewed selection, and safe changes
to the selector itself, plus typed ports for host-owned effects.

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
experiment criteria, and resulting evidence by exact immutable record identity:

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

# A host-owned runner executes `command` and returns its observation.
evidence = rsi.experiments.evaluate_command(
    spec=spec,
    observation=CommandObservation(exit_code=0, stdout="IMPROVED\n", stderr=""),
)
updated = rsi.hypotheses.apply(hypothesis=hypothesis, evidence=evidence)
```

`evaluate_command()` reads its decision criteria from the immutable `ExperimentSpec`;
callers cannot replace them after execution. Evidence names the exact hypothesis and
target snapshot it bears on, and a stale or different hypothesis rejects that evidence.
The `0.2.0` scalar APIs remain available as deprecated compatibility wrappers.

The library performs no persistence or external effects. See
[`src/librsi/README.md`](src/librsi/README.md) for the module map and complete
integration boundary.

## Development guarantees

- Python 3.11 or newer;
- no runtime dependencies;
- typed public API (`py.typed`);
- deterministic policy decisions for identical inputs; and
- at least 90% branch coverage in CI.
