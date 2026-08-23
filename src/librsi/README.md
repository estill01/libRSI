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
- a first-class claim-only validation workflow with current-knowledge reuse, bounded
  evidence-gap actions, four distinct result dispositions, and complete provenance.
- a bounded competing-hypothesis investigation workflow with exact branch rosters,
  observation-only experiment design, and evidence-bound findings; and
- a generic intervention-to-candidate lifecycle with exact rationale/currentness,
  complete absent-Implementer handoffs, and no authoritative application operation.
- a structured intent layer that separates declarative Goals from Claims/Evidence,
  operationalizes natural-language or typed intent into exact objectives, baselines,
  constraints, guardrails, and stopping rules, and returns named information gaps
  instead of fabricating evaluation criteria;
- a bounded restartable improvement workflow that carries exact hypothesis, experiment,
  intervention, candidate, trial, selection, budget, and application-handoff history; and
- an application lifecycle with explicit currentness and capability authority, actual
  produced-state capture, exact-state verification, and rollback without converting
  operational failures into epistemic evidence; and
- a structured RSI governance layer with explicit meta-target classes, configured risk,
  distinct historical and forward-shadow evidence, independent-actor review,
  approval-bound activation, and ordinary application/verification/rollback reuse.
- stable v1 outcome and runtime-event projection envelopes with complete canonical
  result reconstruction, metadata-neutral semantic roots, published JSON Schemas, and
  a replaceable exact-byte persistence contract.

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
- `runtime/records.py` — canonical runs, budgets, events, actions, results, states, and
  optional identity-bound same-target transition authority;
- `runtime/engine.py` — pure transitions, step projection, replay, and terminal policy;
- `facade/client.py` — high-level `LibRSI` composition and workflow methods;
- `facade/run.py` — stepped/managed handle over canonical workflow frontiers;
- `facade/records.py` — exact local hypothesis-test convenience result;
- `local/protocols.py` — independently replaceable artifact, transition, and workspace
  contracts;
- `local/commands.py` — argv-only command experiments within configured roots;
- `local/filesystem.py` — read-only deterministic directory snapshots;
- `local/artifacts.py` — immutable content-checked artifact directory;
- `local/logging.py` — structured Python logging of canonical transitions;
- `local/layout.py` — explicit per-instance workspace/data paths;
- `expert/__init__.py` — retained low-level kernel, engine, workflow, and policy surface;
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
- `validation/records.py` — claim-only request, evidence-gap, batch, and result records;
- `validation/actions.py` — exact runtime codecs and nonreplaceable evidence-result
  validation for the reserved `validation-evidence` action;
- `validation/policy.py` — deterministic evidence sufficiency and public disposition;
- `validation/workflow.py` — low-level stepped and convenience validation over the
  authoritative runtime, current knowledge, and existing Experimenter capability;
- `investigation/records.py`, `investigation/actions.py`, `investigation/policy.py`, and
  `investigation/workflow.py` — typed competing-hypothesis search, complete-frontier
  codecs, deterministic branch policy, and restartable specialized execution;
- `interventions/records.py` — the universal intervention envelope, exact candidate-only
  request/result/handoff records, and compatibility projections;
- `interventions/actions.py` — exact Implementer codecs and nonreplaceable pre-transition
  result validation for `implement-intervention`;
- `interventions/policy.py` — currentness and prospective-candidate construction with no
  application authority;
- `interventions/workflow.py` — restartable absent, managed, and external Implementer
  paths over the canonical runtime;
- `intent/records.py`, `intent/policy.py`, `intent/actions.py`, and `intent/workflow.py`
  — measurable evaluation contracts, consistency checks, proposal-only Reasoner
  handoffs, and typed/natural-language operationalization;
- `improvement/records.py`, `improvement/actions.py`, `improvement/policy.py`,
  `improvement/replay.py`, and `improvement/workflow.py` — bounded iteration, exact budget
  accounting, failure-driven search direction, accepted-candidate handoff, canonical
  replay, and declarative or stepped improvement;
- `application/records.py`, `application/actions.py`, `application/policy.py`,
  `application/replay.py`, and `application/workflow.py` — portable application commands,
  Applier/Verifier codecs, apply-default-off policy, actual-state verification, exact
  rollback, and restartable managed/external execution;
- `governance/records.py` — target-bound application requirements and the authority
  contract that makes classified handoffs fail closed before provider effects;
- `rsi/records.py`, `rsi/actions.py`, `rsi/policy.py`, `rsi/replay.py`, and
  `rsi/workflow.py` — explicit meta-target declarations, configured self-change classes
  and risk tiers, typed historical/shadow/review gates, canonical replay, an
  identity-bound activation approval, and `RSIResult` composition over the ordinary
  application lifecycle;
- `projections/records.py`, `projections/outcomes.py`, and `projections/events.py` —
  typed v1 external envelopes, exact workflow-result-to-Outcome derivation, and
  canonical runtime-event projection;
- `projections/codec.py`, `projections/schemas.py`, and `projections/store.py` — closed
  deterministic JSON/reconstruction, published envelope schemas, and metadata-free
  exact-byte persistence behind a replaceable protocol;
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
Runtime outcomes are fixed to a Run's initial target snapshot unless the Run explicitly
names a target-transition authority in identity and lineage. Even then, the terminal
snapshot must describe the same target and the Outcome must retain the authority reference.
Application Runs use their exact `ApplicationRequest`; ordinary validation,
investigation, and improvement Runs remain snapshot-fixed.

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

The validation workflow composes, but does not replace, those lower layers. Its Run
intent is the exact `Claim` rather than a synthetic goal; current stored evidence can
complete the run without an action, while an evidence gap becomes one bounded canonical
action. Managed and external hosts return the same evidence-batch `ActionResult`.
Supported, contradicted, bounded, and inconclusive results cite the exact belief,
evidence, target snapshot, runtime, and reused-versus-gathered provenance. Stale evidence,
free-form success narration, duplicate actions, and infrastructure failures cannot be
silently converted into support or counterevidence. `ValidationWorkflow.resume()`
reconstructs that projection only from an exact persisted run and exact-root reused
knowledge, returning any deterministic reconciliation transitions in a
`ValidationUpdate`; drifted requests, evidence frontiers, actions, and outcomes fail
closed. Direct and managed submission perform that same reconciliation before runtime
mutation; any reused evidence must still resolve through the supplied `KnowledgeStore`.
The initial validation contract uses the canonical built-in epistemic policy;
alternate sufficiency policies require an explicit versioned semantic policy contract.

`investigation/records.py` owns bounded question requests, hypothesis branches, a typed
complete-roster `InvestigationFrontier`, exact experiment-evidence batches, evidence-bound
findings, and `InvestigationResult`.
`investigation/policy.py` owns neutral-prior belief aggregation, sequential/parallel lane
activation, deterministic prioritization, redesign/experiment budgets, branch retirement,
and stopping. `investigation/actions.py` owns dedicated reserved reasoner/experimenter
codecs and nonreplaceable pre-transition validators. `investigation/workflow.py` composes
those owners with the Block 7 runtime; it exposes one restartable action frontier and
reconstructs every branch from the persisted action/result log before mutation or a
managed host effect. Each action carries the complete ordered branch roster plus the one
policy-selected active branch. Generic `CapabilityDispatcher` configuration and
submission fail closed for these specialized action kinds; only
`InvestigationWorkflow.submit()` can advance them. `derive_investigation_action()` is the
single owner for branch choice, phase, experiment sequence, and budget eligibility; action
builders, decoders, replay, and failure-result validation all require its exact output.

Reasoner hypothesis confidence remains proposal metadata: each branch starts from a
neutral canonical belief and changes only through exact Evidence. Sequential portfolios
finish a lane before advancing; parallel portfolios keep every viable lane active and
round-robin the least-tested branch. Experiment-design proposals can describe only
epistemic work through a closed observation-only schema: `measure`, `observe`, or
`retrieve`, bounded measurement identifiers, and canonical evidence criteria. There is no
open procedure/operation mapping in which intervention, candidate, implementation,
mutation, application, or target-change authority can hide. A dedicated
`investigation-reason` validator applies that schema before any runtime transition.
`InvestigationFinding` cannot synthesize text beyond a supported hypothesis
statement, and terminal stop causes are derived from branches plus exact failed-result
lineage. Investigation never proposes or applies a target change.

The intervention package begins only after that epistemic boundary. An
`InterventionSpec` binds one exact baseline, rationale references, current supporting
Evidence, expected effects, risks, constraints, validation plan, rollback expectations,
and a domain-owned `specification` mapping. Its canonical Run has one bounded
`implement-intervention` action. If no Implementer is connected, the waiting projection
contains a complete serializable `ImplementationHandoff`; the generic capability
dispatcher can alternatively route the same action through an exact Implementer route.
Both managed and external results pass libRSI's nonreplaceable validator before runtime
mutation. Generic dispatcher `advance()` and `submit()` calls for this reserved action
must also receive an explicit current target snapshot; currentness is checked before an
automatic Implementer is called and again before submission.

Successful preparation yields a `CandidateSnapshot` whose prospective state must differ
from the baseline and whose evidence/artifact lineage is exact. It also yields an
`ImplementationResult` and `Outcome` whose authoritative target snapshot is still the
baseline. Only the preparation status `prepared` exists here. There is deliberately no
`apply` method, applied status, comparison/acceptance decision, or domain-specific
implementation engine in this package. Hosts may place software patches, laboratory
plans, physical-process settings, document edits, or other domain payloads inside the
generic specification and artifact boundaries without adding identity-bearing core
fields. The original low-level `Intervention` and `Candidate` records remain compatible
through explicit projections rather than a second lifecycle.

`librsi.comparison` is the next semantic layer. `CandidateTrialBatch` binds one
prospective candidate to one exact `EvaluationContract`, baseline/candidate
`ExperimentSpec`, complete `TrialResult` set, and recomputed generic `Evaluation`.
`ComparativeSelectionPolicy` derives per-metric uncertainty intervals, applies minimum
meaningful effects and every guardrail conservatively, and then reports one candidate,
a transparent non-dominated Pareto set, or `none-accepted`. Rankings contain pairwise
dominance references rather than an opaque aggregate score. Invalid or insufficient
trials, mismatched baselines, divergent metric definitions, and required-but-missing
typed accepting review make a candidate ineligible before ranking. Configured review
governance uses an exact `CandidateReview` over the candidate, experiment, and evaluation;
an arbitrary reference or rejected review cannot satisfy it.

Replaceable optimizers connect only through `CandidateProposer`, `SearchRequest`, and
`SearchProposal`. A proposal can name bounded prospective candidates and rationale, but
its fixed `proposal-only` authority cannot accept, rank, apply, or mutate anything.
Selection always recomputes from exact trial evidence under the library-owned contract
and risk policy.

`librsi.improvement` owns the bounded loop from an operationalized goal through competing
hypotheses, evidence, an intervention candidate, repeated comparative trials, and exact
selection. It emits an `ApplicationHandoff` only for one accepted candidate and sets its
authority to `proposal-only`; provider completion, successful implementation, or
favorable narration cannot select or apply a candidate. Iteration, experiment, retry,
resource, and diminishing-return budgets are replay-derived from the canonical action
history.

`librsi.application` consumes that handoff without reopening the epistemic decision. Its
default-disabled result is complete and portable without a host effect. An enabled
request emits a bounded `ApplicationCommand` rather than recursively nesting the complete
hypothesis history inside every host envelope. Configured Applier and Verifier routes may
run automatically, or the same exact actions/results may be submitted by an external or
human-reserved owner. Application captures the host-reported produced snapshot. The
Verifier supplies a `CandidateTrialBatch` whose candidate is that exact state; the library
recomputes its `CandidateAssessment` under the original improvement contract, guardrails,
and risk policy. No host boolean or free-form reason can create a verified disposition. A
rejected/inconclusive assessment or typed verifier infrastructure failure leads to rollback
of the exact prior snapshot. Application and rollback failures remain operational failures,
and a failed rollback deliberately has no authoritative-state claim. Replay and currentness
checks prevent duplicate effects, substituted results, stale application, assumed output
state, and verification of a different snapshot.

The base distribution does not open a database from the composition root, mutate
targets or files, run Git/subprocess operations, call a model/provider, schedule
workers, or send messages. Hosts choose whether and where to construct stores and
which explicit capability objects may perform effects. These reference components do
not make libRSI a generic workflow, MLOps, storage, coding-agent, or server
infrastructure platform.

`librsi.projections` is the external semantic boundary over those owners, not another
lifecycle. `project_result()` accepts only exact `ValidationResult`,
`InvestigationResult`, `ImprovementResult`, or `RSIResult` values and derives the one
complete public `Outcome` from them. Its v1 JSON contains both root-checked canonical
records plus stable workflow/result/outcome fields. Reconstruction delegates to the
registered semantic record decoder, so an external projection cannot relax lineage,
currentness, policy-derived disposition, application authority, or self-change
governance. Validation and investigation failures retain their exact terminal status,
`ActionResult`, and `RuntimeFailure`; projection delegates to the same workflow-owned
outcome derivation used to reconcile runtime state, so operational failure cannot be
relabeled as ordinary epistemic inconclusiveness. Runtime event projections similarly
retain the exact canonical `Event` and
derive every summary field from it. Transport metadata is serialized for correlation
but excluded from `projection_root`; persistence deliberately strips it. CLI, HTTP, MCP,
notifications, and dashboards remain later interface projections over this same
contract.

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
