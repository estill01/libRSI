# libRSI Architecture Expansion & Implementation Tracker

**Baseline:** `main` at `d96cc666c7800681dfdde2f991f841b09155dfe8`  
**Current version:** `0.2.0`  
**Program objective:** Evolve libRSI from a small collection of deterministic RSI-related policies into a batteries-included but composable framework for evidence-driven validation, investigation, problem solving, improvement, and recursive self-improvement.

---

## 1. Current-state assessment

At the current HEAD, libRSI is still fundamentally a **deterministic policy kernel**:

- `RSIKernel` is a frozen composition of independent checkpoint, review, program, portfolio, selection, selector, reflection, hypothesis, and experiment policies. It does not own a run lifecycle or state machine.
- The public package explicitly says that database, process, filesystem, and provider effects belong outside libRSI. That boundary is no longer a desired product constraint; only the deterministic core needs to retain that property.
- The public models are small transitional records rather than complete domain objects. For example, a `HypothesisProposal` retains only statement, confidence, and root; the scope, causal model, prediction, and reflection linkage used to create the root disappear.
- Experiments are currently command-specific. `command_input()` hashes the design and success criteria but does not carry them in the returned immutable object, while `evaluate_command_result()` accepts success criteria separately. This permits an experiment to be evaluated under criteria different from those bound into its identity.
- The only execution port is `ExperimentRunner`, specifically `CommandExperimentInput -> CommandObservation`.
- `SelectionPolicy` currently enforces review/eligibility invariants but does not actually compare or rank candidates.
- `PortfolioPolicy` already supplies useful sequential/parallel lane mechanics that can become part of a broader search system.
- The current selector self-change policy already has historical, forward-shadow, independent-review, activation, and rollback concepts worth retaining as the seed of generalized RSI self-change governance.
- The current test suite largely verifies individual policies; even the composition test only verifies that `RSIKernel` contains the expected policy objects.
- CI is a good base: Python 3.11–3.13, Ruff, formatting, mypy, branch coverage, package build, and wheel smoke test. Preserve this discipline as the system expands.

The existing README therefore accurately describes the current implementation, but no longer describes the product we want to build.

---

# 2. Target architecture

The core semantic primitives should be:

```text
Target
    What the work concerns.

TargetSnapshot
    Exact/current state of that target.

Claim
    Something that may be true.

Question
    Something we want to understand.

Goal
    Something we want to make true.

Constraint
    Something that must remain true.

Evidence
    Information bearing on claims.

Knowledge
    Persisted claims, evidence, relationships,
    observations and prior outcomes.

Experiment
    Deliberate generation of discriminating evidence.

Intervention
    A proposed change to a target.

Candidate
    A concrete prospective target state produced from an intervention.

Outcome
    What was learned, validated, recommended or achieved.
```

The major workflows should then be compositions:

```text
Claim
    ↓
VALIDATION
    ↓
ValidationResult


Question
    ↓
INVESTIGATION
    ↓
claims / hypotheses / experiments / evidence
    ↓
InvestigationResult


Goal + Constraints
    ↓
IMPROVEMENT
    ↓
investigation → interventions → candidates
→ experiments → selection → verification
    ↓
ImprovementResult


Improvement
    +
target includes improvement machinery itself
    +
stronger self-change governance
    ↓
RSI
```

Two architectural requirements apply across all of them:

## Control-plane neutrality

The same run must work either:

```text
external host
    → run.next()
    → perform action
    → run.submit(result)
```

or:

```text
libRSI
    → dispatch action through configured capability
    → receive result
    → continue
```

The underlying state transitions, evidence semantics, identities, and outcomes must be the same.

## Domain neutrality

libRSI must not assume that a target is a Git repository. Software repositories should be an excellent supported target type, but the same framework must support models, documents, datasets, processes, physical systems, and other externally implemented targets.

---

# 3. Implementation program

## Block 0 — Architecture contract, namespace plan, and legacy baseline

**Outcome:** Establish the new architecture as an explicit implementation contract before changing semantics.

**Depends on:** Current `main`.

**Implement:**

- Add maintained architecture documentation defining:
  - epistemics;
  - knowledge;
  - targets;
  - experiments;
  - runtime;
  - interventions;
  - validation;
  - investigation;
  - improvement;
  - RSI/meta-improvement.
- Define control-plane neutrality as an invariant.
- Define `Target != Knowledge != Intent`.
- Define the candidate/application distinction.
- Define libRSI-driven, externally driven, and hybrid execution as equally supported modes.
- Decide that current policy classes remain available as low-level/core APIs during migration.
- Create regression fixtures around current `0.2.0` behavior before refactoring.

**Acceptance:**

- Every current test remains green.
- Architecture documentation identifies the eventual ownership of every current module.
- No new workflow semantics are implemented yet.
- No dependency from libRSI to Software Factory or another high-level consumer is introduced.

---

## Block 1 — Canonical immutable domain records and identity model

**Outcome:** Replace dictionary-and-hash-centric API design with complete immutable semantic records.

**Depends on:** Block 0.

**Introduce canonical records approximately covering:**

```text
TargetRef
TargetSnapshot
Claim
Question
Goal
Constraint
Hypothesis
Evidence
EvidenceRef
ExperimentSpec
Trial
Observation
Measurement
Evaluation
Intervention
Candidate
Outcome
ArtifactRef
```

Every important record should:

- retain all semantically material fields;
- have a stable identity/root;
- preserve lineage;
- carry schema/version information where serialized;
- distinguish identity-bearing data from presentation metadata;
- be serializable without losing semantics.

**Important rule:** hashes identify records; they do not substitute for the records.

**Acceptance:**

- Round-trip serialization is deterministic.
- Identity changes exactly when identity-bearing content changes.
- References cannot silently point to a different semantic object.
- Complete objects can be reconstructed from persistent state without an external synchronized dictionary.

---

## Block 2 — Repair current hypothesis and experiment referential integrity

**Outcome:** Eliminate the concrete epistemic-integrity problems in the current APIs before building orchestration on them.

**Depends on:** Block 1.

### Hypotheses

Replace the effective:

```text
statement + confidence + hash
```

record with a complete hypothesis carrying:

- scope/target reference;
- statement;
- causal model where applicable;
- predictions;
- originating question/reflection;
- confidence/belief state;
- current status;
- identity.

Evidence updates must identify the exact hypothesis they update.

### Experiments

The immutable experiment specification must contain:

- exact design;
- decision/evaluation criteria;
- target/baseline identity;
- inputs;
- environment requirements;
- measurements requested.

Evaluation must consume the exact `ExperimentSpec`; callers must not be able to replace its criteria after execution.

### Compatibility

Retain deprecated wrappers for the current `propose()`, `command_input()`, and related API where practical.

**Acceptance:**

- The current “criterion A at design / criterion B at evaluation” condition is impossible.
- A `Hypothesis` can always explain what proposition it represents.
- Evidence updates maintain exact hypothesis identity.
- Existing current behavior is reproducible through compatibility wrappers.

---

## Block 3 — General epistemic model and pluggable belief/evidence aggregation

**Outcome:** Make hypotheses useful outside improvement loops.

**Depends on:** Blocks 1–2.

**Implement:**

- `Claim` as the generic truth-bearing proposition.
- `Hypothesis` as a provisional/testable form of claim rather than the universal entry point.
- Claim kinds such as behavioral, causal, capability, invariant, observational, and assumption without overcommitting to a deep class hierarchy.
- Explicit evidence relationships:
  - support;
  - counterexample;
  - boundary;
  - confounder;
  - null/inconclusive.
- Provenance and target-currentness binding.
- `EvidenceAggregator` policy interface.

Preserve the current linear confidence update as a built-in policy, but stop hard-coding it as the only possible epistemic model.

Future policies should be able to implement Bayesian, sequential, empirical, or domain-specific evidence aggregation.

**Acceptance:**

- Claims can be validated without being part of an improvement run.
- Null/infrastructure failure cannot become negative scientific evidence.
- Conflicting evidence can coexist with explicit provenance.
- Current hypothesis-update behavior remains available as one policy.

---

## Block 4 — Generic experiment, measurement, metric, and evaluation subsystem

**Outcome:** Replace “command succeeded” as the dominant experimental abstraction.

**Depends on:** Blocks 1–3.

**`ExperimentSpec` should support:**

- claim(s) being tested;
- target snapshot;
- optional baseline and candidate snapshots;
- variables/conditions;
- measurements;
- metrics;
- repetitions/trials;
- validity requirements;
- environment identity;
- random seed where relevant;
- resource/time budget;
- decision rule.

**Introduce:**

```text
Metric
Measurement
Trial
TrialDisposition
DecisionRule
ExperimentEvaluation
```

Metrics should support at minimum:

```text
minimize
maximize
target range
must equal/satisfy
no-regression threshold
minimum meaningful effect
```

Command execution becomes one experiment adapter rather than the experiment ontology.

**Acceptance:**

- A claim can be experimentally tested without any candidate change.
- Baseline-vs-candidate experiments are first-class.
- Invalid trials are separate from negative results.
- Repeated trials are represented individually.
- Evidence weights/dispositions can be derived by evaluation policy rather than fixed at `0.7`.
- Existing command experiments work through a `CommandExperiment` adapter.

---

## Block 5 — Target, target snapshot, multi-component target, and currentness model

**Outcome:** Give libRSI an explicit answer to “what are we working on?”

**Depends on:** Blocks 1–4.

**Implement:**

```text
Target
TargetRef
TargetSnapshot
TargetComponent
TargetCapabilities
```

Requirements:

- Targets may be opaque to the core.
- Targets may contain multiple components.
- Every evidence-bearing operation can bind to an exact target snapshot.
- Currentness can be checked independently of knowledge.
- Multi-repository software systems are representable without making repositories fundamental to libRSI.

Example:

```text
SoftwareSystem
    api repo @ revision A
    scheduler repo @ revision B
    config repo @ revision C
```

should form one exact target snapshot.

**Acceptance:**

- Evidence from an old target state cannot silently be treated as current.
- A target need not be locally mutable.
- A multi-component target can be snapshotted and compared atomically at the semantic level.
- No Git-specific field is required by core target records.

---

## Block 6 — Persistent knowledge model and `KnowledgeStore`

**Outcome:** Make accumulated understanding reusable across runs.

**Depends on:** Blocks 1–5.

**Implement a persistent knowledge layer for:**

- claims;
- hypotheses;
- evidence;
- observations;
- measurements;
- experiments;
- target snapshots;
- interventions;
- outcomes;
- causal/dependency relationships;
- lineage;
- provenance/currentness.

Provide:

```python
class KnowledgeStore(Protocol):
    ...
```

and ship SQLite as the default implementation.

Knowledge retrieval should allow filtering by:

- target;
- target version/currentness;
- claim/question/goal;
- evidence type;
- lineage;
- prior run;
- recency/validity.

**Important:** `KnowledgeStore` is not the same thing as runtime state persistence.

**Acceptance:**

- A second run can reuse valid knowledge from the first.
- Stale target-bound knowledge remains queryable but is not represented as current.
- SQLite works with no external service.
- A Postgres implementation can later satisfy the same contract.

---

## Block 7 — Durable Run / Event / State / Action engine

**Outcome:** Add the missing orchestrator and make execution resumable.

**Depends on:** Blocks 1–6.

Introduce:

```text
Run
RunState
Event
Action
ActionResult
Transition
```

The runtime should operate conceptually as:

```python
transition = engine.step(state)
```

and produce either:

```text
Action(s)
```

or:

```text
Completed Outcome
```

Persist an append-only canonical event history plus materialized current state.

Requirements:

- replay;
- resume after interruption;
- idempotent/replay-safe submission;
- exact action/result correlation;
- retry tracking;
- failure classification;
- run budgets;
- terminal states;
- no inference of authoritative state from conversational text.

**Acceptance:**

- Kill a run after any transition and resume it from SQLite.
- Replaying the same event log yields the same semantic state.
- Duplicate result submission cannot double-apply a transition.
- State-machine tests cover invalid transitions.

---

## Block 8 — Capability protocols and control-plane-neutral dispatch

**Outcome:** Support both “libRSI is embedded” and “libRSI drives supplied implementers.”

**Depends on:** Block 7.

Introduce granular capability contracts approximately covering:

```text
Inspector
Retriever
Reasoner
Experimenter
Implementer
Reviewer
Applier
Verifier
```

A single object may implement several protocols.

Capability resolution should distinguish:

```text
automatic
externally supplied
human/reserved
unavailable
```

Support all three modes:

### Managed

```python
result = rsi.improve(...)
```

### Externally driven

```python
run = rsi.start(...)

while action := run.next():
    run.submit(host.handle(action))
```

### Hybrid

libRSI handles some actions automatically and surfaces others to the consumer.

**Acceptance:**

- The same deterministic workflow can be completed through external driving or automatic dispatch.
- Semantically equivalent action results produce equivalent state regardless of who performed them.
- Missing capabilities produce a structured pending action rather than an opaque failure.
- No domain-specific capability implementation is required by the core.

---

## Block 9 — Reasoner contract and structured reasoning work

**Outcome:** Allow cognitive work without making an LLM the source of epistemic authority.

**Depends on:** Blocks 3, 7, 8.

Introduce provider-neutral reasoning requests/results for:

- reflection;
- claim/hypothesis generation;
- experimental design;
- explanation;
- intervention generation;
- problem decomposition;
- approach revision.

Reasoning outputs should be **proposals** subject to validation, identity, currentness, and evidence rules.

Support two reasoner modes:

```text
LibRSI → Reasoner implementation
```

and:

```text
external agent/Codex → consumes ReasoningAction → submits structured result
```

**Acceptance:**

- No provider-specific type leaks into the core model.
- A run can proceed with an external reasoning host and no model SDK installed.
- A bad or malformed reasoning response fails validation without corrupting state.
- Reasoner narration cannot directly promote a claim to validated knowledge.

---

# Phase II — Composed epistemic workflows

## Block 10 — First-class validation workflow

**Outcome:** Make libRSI useful as “lib validation” independently of RSI.

**Depends on:** Blocks 3–9.

Public API target:

```python
result = lib.validate(
    target=target,
    claim=Claim("The scheduler is starvation-free"),
)
```

Workflow should:

1. retrieve relevant existing knowledge;
2. determine whether sufficient current evidence already exists;
3. identify evidence gaps;
4. request observations/experiments as needed;
5. evaluate evidence;
6. update claim status;
7. return a structured `ValidationResult`.

**Acceptance:**

- Validation requires no goal or intervention.
- Existing sufficient evidence can avoid unnecessary execution.
- Supported, contradicted, bounded, and inconclusive outcomes are distinguishable.
- Complete evidence provenance is returned.

---

## Block 11 — Investigation / scientific-understanding workflow

**Outcome:** Support questions such as “What is causing this?”

**Depends on:** Block 10.

Public API target:

```python
result = lib.investigate(
    target=target,
    question=Question("What causes scheduler latency spikes?"),
)
```

Implement:

- hypothesis generation;
- alternative explanations;
- hypothesis lineage/refinement;
- experimental prioritization;
- evidence gathering;
- branching search;
- abandonment of contradicted/unproductive branches;
- unresolved-question tracking;
- answer synthesis strictly bound to accumulated evidence.

Reuse and expand `PortfolioPolicy` for sequential/parallel investigative lanes.

**Acceptance:**

- Falsifying one hypothesis does not terminate the investigation when alternatives remain.
- An inconclusive experiment can cause experiment redesign.
- Investigation can stop on confidence, evidence sufficiency, budget exhaustion, or absence of productive next actions.
- Returned conclusions cite their supporting evidence internally.

---

# Phase III — Intervention and improvement

## Block 12 — Generic intervention and candidate lifecycle

**Outcome:** Standardize what libRSI recommends changing without assuming how that change is applied.

**Depends on:** Blocks 5–11.

Introduce:

```text
Intervention
InterventionSpec
Candidate
CandidateSnapshot
ImplementationResult
```

`Intervention` should use a universal semantic envelope:

```text
target
kind
specification
rationale
supporting claims/evidence
expected effects
risks
constraints
validation plan
rollback expectations
```

but permit domain-specific `specification` payloads such as:

```text
software.objective
software.patch
document.revision
model.training_config
process.parameter_change
host.custom
```

An `Implementer` turns an intervention into a **candidate**, not necessarily an authoritative target mutation.

**Acceptance:**

- libRSI can emit a useful intervention even when no implementer exists.
- Candidate state is distinct from authoritative target state.
- Intervention payload extension does not require modifying the libRSI core.
- Candidate lineage binds back to the intervention and evidence that motivated it.

---

## Block 13 — Goals, objectives, constraints, guardrails, and operationalization

**Outcome:** Make the public improvement interface declarative rather than hypothesis-first.

**Depends on:** Blocks 5–12.

Introduce:

```text
Goal
Objective
Constraint
Guardrail
EvaluationContract
Baseline
```

Support fuzzy intent:

```python
Goal("Reduce scheduler queue latency")
```

and explicit operational intent:

```python
objectives=[
    Minimize("queue_latency.p95"),
]

constraints=[
    NoRegression("throughput", tolerance=0.02),
    MustSatisfy("all_tests_pass"),
]
```

Add an operationalization phase that can translate a high-level goal into a proposed measurable `EvaluationContract`.

Reasoners may propose the contract; the typed contract governs evaluation.

**Acceptance:**

- Goals are not represented as claims.
- A natural-language goal can be operationalized before candidate generation.
- Metrics, guardrails, baselines, and stopping conditions are explicit.
- An unmeasurable goal results in a structured need-for-information/action rather than fabricated success criteria.

---

## Block 14 — Comparative evaluation, actual candidate selection, and search policy

**Outcome:** Make “better” an explicit evidence-backed decision.

**Depends on:** Blocks 4, 12, 13.

Expand selection from eligibility gating into actual decision logic.

Support:

- baseline vs candidate;
- multiple candidates;
- primary metrics;
- guardrails;
- minimum meaningful improvement;
- repeated trials;
- uncertainty;
- invalid trials;
- candidate ranking;
- Pareto/non-dominated options where objectives conflict;
- risk-adjusted acceptance;
- “none of these candidates is good enough.”

Preserve current independent-review eligibility logic as a governance component rather than mandatory selection logic for every low-risk case.

**Acceptance:**

- A passing command alone cannot establish an improvement.
- A candidate that improves the primary metric but violates a guardrail is rejected.
- The selector can return “no candidate accepted.”
- Parallel portfolio lanes can be compared through one selection contract.

---

## Block 15 — Complete improvement workflow

**Outcome:** Provide the first actual end-to-end libRSI improvement engine.

**Depends on:** Blocks 10–14.

Public target:

```python
result = lib.improve(
    target=target,
    goal="Reduce scheduler queue latency",
)
```

Lifecycle:

```text
Goal
 ↓
operationalize
 ↓
baseline
 ↓
inspect / investigate
 ↓
hypothesize
 ↓
generate interventions
 ↓
implement candidate(s)
 ↓
experiment
 ↓
compare/select
 ↓
return or apply
 ↓
verify
 ↓
learn
 ↓
repeat / stop
```

Add:

- iteration budget;
- experiment budget;
- retry budget;
- resource budget hooks;
- diminishing-return stopping;
- “no useful improvement found” outcome;
- broadening search after repeated failure;
- narrowing investment around promising branches.

**Acceptance:**

- A complete synthetic improvement can run without the caller manually sequencing hypothesis/experiment/evidence calls.
- Failure of one candidate can return the engine to investigation.
- A falsified hypothesis can lead to a different hypothesis.
- A successful candidate returns a complete evidence-backed `ImprovementResult`.

---

## Block 16 — Application, authoritative target transition, verification, and rollback

**Outcome:** Support change application without making application mandatory or domain-specific.

**Depends on:** Block 15.

Separate:

```text
Intervention
    ↓
Implementer
    ↓
Candidate
    ↓
Evaluation
    ↓
Accepted Candidate
    ↓
Applier
    ↓
Authoritative Target
```

Implement generic lifecycle/status semantics for:

```text
proposed
implemented-as-candidate
validated
accepted
application-requested
applied
verified
failed-verification
rolled-back
```

Recommended default:

```text
apply=False
```

unless explicitly configured otherwise.

If no `Applier` exists, return a complete application handoff.

Post-application verification must use the exact target state actually produced, not assume successful execution means successful improvement.

**Acceptance:**

- `apply=False` returns a fully consumable intervention/result.
- `apply=True` works when a compatible applier exists.
- Failed post-application verification can request/perform rollback.
- Application failure is not misclassified as evidence against the underlying hypothesis.
- Target-currentness preconditions are enforced.

---

# Phase IV — Recursive self-improvement

## Block 17 — Generalized RSI/meta-targeting and self-change governance

**Outcome:** Make recursive self-improvement a special composition of the same machinery.

**Depends on:** Blocks 7–16.

A target should be allowed to include portions of the improvement system itself:

```text
hypothesis generator
experiment planner
reasoner program/prompt
candidate generator
search strategy
evidence aggregator
selector
resource allocation
libRSI policies
host implementation machinery
```

Generalize the useful current `SelectorPolicy` concepts into meta-intervention governance:

- historical replay/evaluation;
- forward shadow;
- independent evaluation;
- activation gates;
- currentness;
- rollback;
- stronger risk policies for changes affecting future decision quality.

Do not create a second epistemic or experiment system for self-improvement.

**Acceptance:**

- Self-change uses normal `Intervention`, `Candidate`, `Experiment`, `Evidence`, and `Outcome` records.
- Meta-targeting is explicit.
- Self-change cannot bypass its configured governance policy.
- Current selector-policy guarantees survive in generalized form.

---

# Phase V — Product usability and integration

## Block 18 — Batteries-included local runtime and high-level Python façade

**Outcome:** Make `pip install librsi` useful without forcing every consumer to build infrastructure.

**Depends on:** Blocks 6–17.

Ship sensible defaults:

- SQLite state/knowledge store;
- local command experiment executor;
- basic filesystem inspection;
- artifact persistence;
- local process execution;
- structured logging/events.

Expose primary façade:

```python
lib = LibRSI(...)

lib.validate(...)
lib.investigate(...)
lib.improve(...)

run = lib.start(...)
```

Provide convenience constructors such as:

```python
LibRSI.local(...)
LibRSI.for_repo(...)
```

without making repositories part of the core ontology.

Keep low-level policies accessible under an expert/core namespace.

**Acceptance:**

- A trivial local workflow requires minimal setup.
- A consumer can substitute any default component independently.
- Existing `RSIKernel` functionality remains accessible.
- The README no longer teaches manual internal-policy orchestration as the primary API.

---

## Block 19 — Structured Outcome API, serialization, event stream, and external consumption

**Outcome:** Make libRSI results easy for other systems to consume.

**Depends on:** Blocks 10–18.

Canonical output family:

```text
Outcome
ValidationResult
InvestigationResult
ImprovementResult
RSIResult
```

Every outcome should expose:

- run identity;
- target/snapshot;
- original intent;
- conclusions;
- evidence;
- interventions/candidates;
- baseline/candidate comparisons where applicable;
- confidence/decision;
- unresolved issues;
- recommended next actions;
- artifacts;
- application/verification status.

Support equivalent semantic projections as:

```text
Python objects
JSON
event stream
persistent records
```

**Acceptance:**

- Another program does not need to understand libRSI's internal policy calls to consume a result.
- JSON round-trip preserves semantic identity.
- Schema versions are explicit.
- Output generated in externally driven and library-driven modes is equivalent.

---

## Block 20 — CLI and external-agent/Codex protocol

**Outcome:** Make libRSI operable as a durable controller from an external agent.

**Depends on:** Blocks 7–19.

Suggested CLI surface:

```text
librsi validate
librsi investigate
librsi improve

librsi status
librsi next
librsi submit
librsi resume
librsi outcome
```

`next` should emit a structured action with:

- action type;
- relevant exact context;
- expected output schema;
- target/currentness information;
- constraints;
- evidence references.

`submit` should accept a validated structured result.

This is the primary clean integration path for Codex when Codex owns the outer execution loop.

**Acceptance:**

- An entire run can be driven through structured JSON with no Python embedding.
- Killing and restarting the controlling agent does not lose run state.
- `next` never requires the agent to infer lifecycle state from prose.
- Invalid/stale submissions fail closed.

---

## Block 21 — Provider integrations, beginning with a reasoner adapter

**Outcome:** Support libRSI-driven autonomous reasoning while preserving provider neutrality.

**Depends on:** Blocks 9 and 18–20.

Ship optional provider adapters rather than making a model SDK fundamental to libRSI.

At minimum:

```text
Reasoner protocol
ExternalAgentReasoner
one maintained hosted-model reasoner implementation
```

Provider-specific concerns stay outside core semantic records.

The adapter should implement structured reasoning tasks, not decide epistemic truth directly.

**Acceptance:**

- Installing base libRSI does not require a model SDK.
- Installing a provider extra enables managed reasoning.
- Swapping reasoners does not alter the stored epistemic schema.
- External-agent mode remains equally supported.

---

## Block 22 — Software target reference support and Software Factory consumer integration

**Outcome:** Prove that a sophisticated software implementation system can consume libRSI rather than libRSI depending on it.

**Depends on:** Blocks 5, 8, 12, 15–20.

### libRSI side

Provide only generic contracts and, optionally, lightweight software helpers:

```text
SoftwareTarget
multi-repo TargetSnapshot helper
local command experimenter
basic workspace/candidate helper
```

There must be **no libRSI → Software Factory dependency**.

### Software Factory side

In the Software Factory repository, import libRSI and implement the relevant capabilities, potentially including:

```text
Inspector
Reasoner
Experimenter
Implementer
Reviewer
Applier
Verifier
```

Software Factory can then drive libRSI:

```python
run = rsi.start(...)

while action := run.next():
    run.submit(factory.handle(action))
```

or supply its capabilities and allow libRSI to dispatch them.

Software Factory should be able to use libRSI for both:

```text
external target repository improvement
```

and:

```text
governed improvement of Software Factory itself
```

**Acceptance:**

- Software Factory imports libRSI; the reverse never occurs.
- One Software Factory-backed run operates on an ordinary target repository.
- Multi-repository target identity works.
- Accepted intervention/candidate evidence returns to libRSI for epistemic evaluation.
- Software Factory implementation correctness and libRSI improvement validity remain separately representable.

---

# Phase VI — Proof of architecture

## Block 23 — End-to-end validation, investigation, and improvement dogfoods

**Outcome:** Prove that the architecture works as a system rather than only as unit-tested components.

**Depends on:** Blocks 10–22.

Maintain at least these end-to-end scenarios:

### A. Validation-only

```text
Claim
→ gather evidence
→ validate
→ no intervention
```

### B. Investigation-only

```text
Question
→ multiple hypotheses
→ falsify one
→ refine another
→ supported conclusion
```

### C. Improvement with externally driven execution

```text
Goal
→ host consumes actions
→ candidate
→ comparison
→ ImprovementResult
```

### D. Same improvement with libRSI-driven capabilities

Must produce semantically equivalent state/outcome.

### E. Interrupted run

Terminate after an arbitrary action and resume from persistent state.

### F. Application disabled

Produce a standardized intervention consumable by an external system.

### G. Application + verification + rollback

Apply a deliberately bad candidate, detect regression, and restore the authoritative target.

### H. Parallel search

Explore multiple candidate/hypothesis lanes and select the evidence-supported winner.

### I. RSI/self-change

Evaluate a candidate change to some improvement policy under the stronger meta-change gates.

**Acceptance:**

All scenarios are maintained CI tests or deterministic dogfoods, not one-time demonstrations.

---

## Block 24 — Cross-domain agnosticism proof

**Outcome:** Demonstrate that the architecture has not accidentally become a software-specific RSI framework.

**Depends on:** Block 23.

Create at least one small non-software target adapter, preferably something deterministic such as:

- parameterized numerical model;
- structured document;
- synthetic process/configuration target.

Run:

```text
validation
investigation
improvement
```

through the same generic engine.

**Acceptance:**

- No software/Git-specific type is required by generic workflow code.
- `Intervention` and `Candidate` semantics work unchanged.
- Target-specific implementation resides entirely behind capabilities/adapters.
- The same `Outcome` family is returned.

---

## Block 25 — Public API cleanup, documentation, packaging, migration, and release gate

**Outcome:** Make the redesigned architecture the actual product surface.

**Depends on:** Blocks 0–24.

Update:

- package organization;
- top-level exports;
- README;
- internal architecture docs;
- API examples;
- type documentation;
- versioning;
- package metadata;
- optional dependency extras;
- CLI entrypoint;
- LICENSE;
- migration notes from `0.2.x`.

Recommended primary README progression:

```python
lib = LibRSI.for_repo(".")
result = lib.validate("...")
```

then:

```python
result = lib.investigate("...")
```

then:

```python
result = lib.improve("Reduce scheduler queue latency")
```

then a strongly typed declarative example, followed by the stepped/external-host API, and only later the low-level kernel.

Do not use the current manual hypothesis → command experiment → evaluate → apply-evidence example as the headline interface.

**Acceptance:**

- Package build and wheel smoke test remain green.
- Ruff/mypy/tests/branch-coverage remain enforced.
- Public examples execute.
- No documentation claims capabilities that are only planned.
- Current low-level functionality is either preserved or explicitly documented as migrated/deprecated.
- The package description reflects validation/investigation/improvement/RSI rather than “pure policies only.”

---

# 4. Dependency overview

```text
0  Architecture contract
│
├─1  Canonical records
│  └─2  Integrity migration
│     └─3  Epistemics
│        └─4  Experiments
│
├────────5  Targets/currentness
│           │
│           └─6  Knowledge
│              └─7  Run/Event/Action engine
│                 ├─8  Capabilities/control neutrality
│                 │  └─9  Reasoning
│                 │
│                 └─────────────┐
│                               │
│                        10 Validation
│                               │
│                        11 Investigation
│                               │
│                        12 Interventions
│                               │
│                        13 Goals/baselines
│                               │
│                        14 Comparison/selection
│                               │
│                        15 Improvement
│                               │
│                        16 Apply/verify/rollback
│                               │
│                        17 RSI/meta-improvement
│                               │
│                        18 Local runtime/API
│                               │
│                     ┌─────────┴─────────┐
│                     │                   │
│                  19 Outputs          21 Reasoners
│                     │
│                  20 CLI/agent protocol
│                     │
│                  22 Software Factory consumer
│                     │
│                  23 E2E system dogfood
│                     │
│                  24 Cross-domain proof
│                     │
└───────────────── 25 Release/docs
```

---

# 5. Migration map for current code

The existing modules should not simply be deleted.

| Current component | Target role |
|---|---|
| `identity.py` | foundational canonical identity utilities |
| `models.py` | split into canonical domain-specific records |
| `hypotheses.py` | epistemic policies / built-in evidence aggregation |
| `experiments.py` | generic experiment policy + command adapter |
| `checkpoints.py` | currentness/materiality and runtime checkpoint policy |
| `portfolios.py` | search/exploration lane scheduling |
| `programs.py` | intervention/currentness/application-policy precursor |
| `selections.py` | selection invariants, expanded by real comparison/selection |
| `reviews.py` | configurable governance/risk-review primitives |
| `selector_policies.py` | RSI/meta-intervention governance |
| `ports.py` | expand into granular capability protocols |
| `kernel.py` | deterministic policy/transition core, not the public workflow façade |

The physical package does **not** have to be reorganized into dozens of directories immediately. Stabilize semantic ownership first and move modules when doing so reduces rather than creates churn.

---

# 6. Program-level completion gates

I would not consider the redesign fundamentally complete until all of these statements are true:

1. A caller can validate a claim without constructing an improvement loop.
2. A caller can investigate a question without proposing a change.
3. A caller can give libRSI a high-level goal rather than a prewritten hypothesis.
4. libRSI can establish or request a measurable evaluation contract and baseline.
5. Hypotheses, experiments, evidence, candidates, and outcomes are complete durable records with exact lineage.
6. Experimental evaluation is not limited to exit codes/string matching.
7. Invalid execution is never silently converted into evidence against a hypothesis.
8. A run can survive process/agent interruption and resume from authoritative state.
9. Persistent knowledge from prior runs can be reused without treating stale target evidence as current.
10. Candidate implementation is distinct from authoritative application.
11. libRSI can return an intervention without applying it.
12. libRSI can apply an intervention when an appropriate `Applier` is supplied.
13. Applied changes are independently re-verified.
14. Failed verification can route to rollback.
15. Multiple candidate/hypothesis paths can be explored and compared.
16. `SelectionPolicy` or its successor actually answers which candidate, if any, is better.
17. libRSI can be driven externally through `next()/submit()`.
18. The same engine can drive supplied capabilities itself.
19. Hybrid execution is supported.
20. Software Factory can import libRSI and implement its capabilities without libRSI importing Software Factory.
21. A non-software target can use the same validation/investigation/improvement engine.
22. Self-improvement uses the same intervention/evidence machinery with stronger governance rather than a parallel special-purpose system.
23. The primary public API is declarative and useful in a few lines.
24. The low-level deterministic policies remain available for sophisticated consumers.
25. End-to-end CI proves whole workflows, not merely individual policy functions.

---

# 7. Recommended execution strategy

Do **not** start with the autonomous RSI loop.

The highest-leverage ordering is:

```text
canonical records
→ experiment integrity/generalization
→ target + knowledge
→ persistent state/action engine
→ validation
→ investigation
→ intervention
→ improvement
→ application
→ RSI
→ integrations
```

That ordering matters because validation and investigation force the epistemic layer to become genuinely reusable instead of accidentally embedding assumptions that every hypothesis exists only to justify a code change.

Likewise, implement the **stepped `Action → Result` protocol before the fully managed `run()` convenience loop**. Once that boundary works, managed execution is mostly capability dispatch around the same engine; doing it in the opposite order risks baking a particular host into the runtime.

The current policy kernel is therefore not something to replace. It becomes the initial deterministic nucleus underneath a much larger architecture.
