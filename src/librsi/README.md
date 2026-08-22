# libRSI module map

`librsi` is the reusable, host-agnostic policy library extracted from Software
Factory's recursive program evolution, hypothesis-testing, and selection-quality
loops.

It owns the portable part of recursive self-improvement:

- exact-state checkpoint materiality;
- stable program-change and review identities;
- currentness and independent-review guards;
- sequential and parallel improvement portfolios;
- reviewed candidate selection and outcome confidence validation; and
- historical, forward-shadow, independent-review, activation, and rollback gates
  for changes to the selector itself;
- complete immutable semantic records and exact content-addressed references;
- evidence-bound reflection and falsifiable hypothesis identities;
- exact hypothesis-to-evidence subject binding for canonical updates;
- configurable support, counterexample, boundary, confounder, and null-evidence
  updates; and
- immutable command experiment specifications whose design, criteria, target,
  inputs, environment, measurements, and hypothesis reference are all identity-bound.

## Package structure

- `checkpoints.py` — material-change detection;
- `programs.py` — program-change identities and effect gates;
- `portfolios.py` — sequential/parallel lane transitions;
- `reviews.py` — independent-actor rules;
- `selections.py` — candidate selection and outcome confidence;
- `selector_policies.py` — evaluation and rollback of selector self-changes;
- `records.py` — canonical semantic records, exact references, and durable serialization;
- `hypotheses.py` — canonical hypothesis creation/evidence updates plus legacy wrappers;
- `experiments.py` — immutable command specs, host execution inputs, and evidence interpretation;
- `ports.py` — typed host interfaces such as `ExperimentRunner`;
- `identity.py`, `models.py`, and `errors.py` — shared primitives and compatibility models; and
- `kernel.py` — a small composition root, not a second implementation.

The canonical hypothesis/command-experiment path is:

```text
TargetRef + TargetSnapshot
        ↓
HypothesisPolicy.create(...)
        ↓ exact Hypothesis
ExperimentPolicy.design_command(...)
        ↓ immutable ExperimentSpec
ExperimentPolicy.prepare_command(...)
        ↓ CommandExperimentInput(exact_input_root=spec.root)
        ↓ host-owned execution
        ↓ CommandObservation(exact_input_root=executed_input_root)
ExperimentPolicy.evaluate_command(spec=..., observation=...)
        ↓ exact Evidence
HypothesisPolicy.apply(hypothesis=..., evidence=...)
        ↓ new Hypothesis version
```

`evaluate_command()` has no evaluation-time criteria argument. The exact criteria are
read from the immutable `ExperimentSpec`, so the historical “criterion A at design /
criterion B at evaluation” integrity failure is not representable on the canonical
path. The command observation must also echo the exact input root it executed; an
observation from another spec is rejected before interpretation. Resulting evidence
names the exact hypothesis version, experiment spec, and target snapshot; attempting
to apply it to another or stale hypothesis version fails closed.

The historical `propose()`, `apply_evidence()`, `command_input()`, and
`evaluate_command_result()` methods remain available as deprecated `0.2.0`
compatibility wrappers. They preserve legacy hashes and behavior but should not be
used by new orchestration code when exact referential integrity matters.

It intentionally owns no database schema, filesystem mutation, Git operation,
subprocess, model/provider call, or product-specific ontology. A host records policy
decisions in its existing authoritative store and executes experiments and effects
through governed adapters. A canonical command runner should copy
`CommandExperimentInput.exact_input_root` into the returned
`CommandObservation.exact_input_root`. Invalid experiment execution is classified as
zero-weight null evidence; infrastructure failure is never treated as falsification on
the canonical command path.

```python
from librsi import RSIKernel

kernel = RSIKernel()
decision = kernel.checkpoints.evaluate(
    state={"quality": 0.82, "revision": "candidate-7"},
    evidence_ids=["eval-19"],
    previous_fingerprint=None,
)

if decision.material:
    # Persist the decision and schedule host-specific evaluation work.
    record_checkpoint(decision)
```

Software Factory's `EvolutionService` is one reference adapter. It persists RSI
records in the existing factory database and retains ownership of tracker changes,
validation, commits, and other effects. `LearningService` is the reference hypothesis
and experiment adapter: it persists hypotheses and invokes commands, while `librsi`
interprets their epistemic result. Its default command port is
`software_factory.experiment_runner.SubprocessExperimentRunner`; other hosts can
inject a container, remote-job, simulator, or shadow-traffic runner.
