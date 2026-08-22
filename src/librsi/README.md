# libRSI module map

`librsi` is the reusable, host-agnostic semantic core extracted from Software
Factory's recursive program evolution, hypothesis-testing, and selection-quality
loops. The current package is still a low-level deterministic policy/record library;
the maintained architecture expands it toward evidence-driven validation,
investigation, improvement, and governed recursive self-improvement.

The long-term product boundary is semantic rather than infrastructural: libRSI owns
how targets, claims, evidence, experiments, interventions, candidates, decisions,
applications, verification, and self-change governance relate. Models, coding agents,
sandboxes, schedulers, experiment platforms, storage systems, and transports remain
replaceable capabilities/backends except for thin reference implementations needed to
make the library useful out of the box.

The current implementation owns portable primitives including:

- exact-state checkpoint materiality;
- stable program-change and review identities;
- currentness and independent-review guards;
- sequential and parallel improvement portfolios;
- reviewed candidate selection and outcome confidence validation; and
- historical, forward-shadow, independent-review, activation, and rollback gates
  for changes to the selector itself;
- complete immutable semantic records and exact content-addressed references;
- opaque, composite, and non-software target snapshots with atomic currentness;
- evidence-bound reflection and falsifiable hypothesis identities;
- exact hypothesis-to-evidence subject binding for canonical updates;
- configurable support, counterexample, boundary, confounder, and null-evidence
  updates; and
- generic metrics, validity-aware repeated trials, deterministic decision rules,
  and replay-bound evidence projection; and
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
- `targets.py` — generic target composition, capabilities, snapshots, and currentness;
- `epistemics.py` — typed belief state and replaceable evidence aggregation;
- `evaluation.py` — generic trials, metric rules, evaluation, and evidence projection;
- `knowledge.py` — backend-neutral reusable-knowledge, query, and currentness contracts;
- `sqlite_schema.py` — exact local schema and rollback-safe migration contract;
- `sqlite_knowledge.py` — minimal transactional SQLite reference persistence;
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

The **current** implementation owns one thin, replaceable SQLite schema for canonical
knowledge and per-run provenance. It intentionally does not store runtime Run/Event/
Action state, open a database from the composition root, mutate targets or files, run
Git/subprocess operations, or call a model/provider. Hosts choose whether and where to
construct a `KnowledgeStore` and execute experiments and effects through governed
adapters. The reference backend does not make libRSI a generic workflow, MLOps,
storage, coding-agent, or server infrastructure platform.

A canonical command runner should copy
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

Software Factory is a reference consumer, not a dependency of libRSI. As generic
Target/Capability/Intervention/Outcome contracts stabilize, Software Factory should
incrementally map its mission state, candidate worktrees/effects, experiments, and
application/verification machinery onto those libRSI contracts. The required
dependency direction remains Software Factory → libRSI, never the reverse.

Other hosts may provide local processes, containers, remote jobs, simulators,
physical-system adapters, numerical optimizers, LLM-program optimizers, or other
capabilities while libRSI retains the semantic/evidence/selection authority defined by
its contracts.
