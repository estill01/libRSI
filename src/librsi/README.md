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
- one pure replayable Run/Event/State/Action transition engine with explicit budgets,
  structured failures, terminal outcomes, and duplicate-result protection; and
- an independent replaceable runtime-store contract with a transactional,
  replay-validated SQLite reference backend.
- eight granular structural capability protocols with explicit automatic, external,
  human-reserved, and unavailable routing; and
- deterministic managed/external/hybrid dispatch through the same runtime transitions.
- strict provider-neutral reasoning requests/results for reflection, hypothesis
  generation, experiment design, explanation, intervention generation, problem
  decomposition, and approach revision; and
- pre-transition schema/currentness validation plus proposal-to-decision lineage guards.

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
- `runtime/records.py` — canonical runs, budgets, events, actions, results, and states;
- `runtime/engine.py` — pure transitions, step projection, replay, and terminal policy;
- `runtime/store.py` — backend-neutral append/resume persistence contract;
- `runtime/sqlite_schema.py` and `runtime/sqlite.py` — isolated exact-schema SQLite
  runtime durability with append-only events and replay-checked materialized state;
- `capabilities/protocols.py` — Inspector, Retriever, Reasoner, Experimenter,
  Implementer, Reviewer, Applier, and Verifier host contracts;
- `capabilities/records.py` — explicit routes, resolutions, plans, and dispatch batches;
- `capabilities/registry.py` — deterministic action-kind resolution and implementation
  lookup without semantic authority;
- `capabilities/dispatcher.py` — optional automatic-frontier execution and external
  `next`/`submit` equivalence through the Block 7 runtime engine;
- `reasoning/records.py` and `reasoning/schemas.py` — canonical cognitive requests and
  closed structured proposal schemas with exact input/currentness lineage;
- `reasoning/actions.py` — lossless request/result codecs for the runtime `reason` action;
- `reasoning/adapters.py` — zero-provider backend protocol and managed Reasoner adapter;
- `reasoning/validation.py` — pre-transition response validation and downstream
  Evidence/Intervention lineage guards;
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

The **current** implementation owns two independent replaceable persistence
contracts: reusable canonical knowledge and authoritative runtime history. Their thin
SQLite reference backends use separate owned schemas and versioning, although a host
may place both in one file. Runtime records never enter the knowledge store, and
knowledge projections never determine runtime lifecycle state. Every runtime resume
reconstructs the complete event prefix and verifies the materialized transitions
against the pure engine before returning state.

The runtime emits exact pending `Action` records. The optional capability dispatcher
may invoke a host-supplied object only when the exact action kind is configured for
automatic authority; external and hybrid hosts submit the same `ActionResult` through
the same runtime transition. Human-reserved and unavailable actions remain structured
and pending. A successful capability result cannot itself create an Outcome, promote
knowledge, select a candidate, or authorize application.

Structured reasoning is a replaceable implementation of the same `Reasoner` capability,
not a new runtime. Managed backends and external agents consume one canonical
`ReasoningRequest`, produce one validated `ReasoningResult`, and submit the same exact
`ActionResult`. Closed per-kind schemas reject free-form substitutions and authority-
bearing fields; the dispatcher always applies its nonreplaceable canonical validator
 before any optional host validator on the reserved `reason` path. A successful result
 references only its proposal record: narration may
explain a proposal but cannot become evidence or validated knowledge merely by saying so.

The base distribution does not open a database from the composition root, mutate
targets or files, run Git/subprocess operations, call a model/provider, schedule
workers, or send messages. Hosts choose whether and where to construct stores and
which explicit capability objects may perform effects. These reference components do
not make libRSI a generic workflow, MLOps, storage, coding-agent, or server
infrastructure platform.

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
