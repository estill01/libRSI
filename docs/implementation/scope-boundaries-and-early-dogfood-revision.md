# libRSI Scope Boundaries and Early Dogfood Revision

**Program:** libRSI Architecture Expansion  
**Status:** Maintained planning amendment  
**Applies to:** `architecture-contract.md`, `architecture-expansion-implementation-tracker.md`, `parallel-implementation-plan.md`, and `server-mcp-implementation-block.md`  
**Last updated:** 2026-08-21

This document is a normative amendment to the implementation program. It does **not** replace the 0–25 tracker or the parallelization plan. Instead, it sharpens product ownership boundaries, moves important dogfoods earlier, and clarifies where mature external systems should be used behind libRSI contracts rather than reimplemented inside libRSI.

Where this document conflicts with the older wording of the implementation tracker or parallel plan, this revision controls unless a later maintained architecture revision explicitly supersedes it.

---

# 1. Product boundary

The differentiated libRSI product is:

> **A domain-neutral, evidence-driven validation, investigation, and improvement engine with exact provenance, resumable semantic workflows, candidate/application separation, and stronger governance for self-change.**

Recursive self-improvement is an advanced composition of that engine, not the ontology from which all lower-level behavior must inherit.

The public progression should remain:

```text
validate
→ investigate
→ improve
→ recurse when appropriate
```

The name `libRSI` remains appropriate, but public positioning should lead with evidence-driven validation/investigation/improvement rather than implying that every use is an autonomous self-improvement loop.

---

# 2. What libRSI owns

libRSI owns the **semantics and integrity rules** of:

```text
knowing
asking
hypothesizing
testing
interpreting evidence
operationalizing goals
proposing interventions
forming candidates
comparing candidates
selecting or rejecting candidates
requesting/authorizing application
verifying applied changes
learning from outcomes
governing self-change
```

Concretely, core ownership includes:

- canonical semantic records and identities;
- exact target snapshots/currentness;
- claims, questions, goals, constraints, hypotheses, and evidence;
- provenance and evidence validity;
- experiment specifications and evaluation semantics;
- intervention/candidate/application separation;
- comparative selection, including “none accepted”;
- deterministic `State → Action → ActionResult → State` semantics;
- structured outcomes;
- stronger meta-change governance when the target includes improvement machinery.

The following distinctions are architectural invariants:

```text
Target ≠ Knowledge ≠ Intent
Claim ≠ Question ≠ Goal ≠ Constraint
Experiment specification ≠ execution mechanism
Invalid experiment ≠ evidence against a hypothesis
Intervention ≠ Candidate ≠ authoritative application
Passing execution ≠ verified improvement
Ordinary improvement ≠ self-change without stronger governance
```

---

# 3. What libRSI does not own as a platform

The following are generally **capabilities, adapters, backends, transports, or thin reference implementations**, not independent platforms for libRSI to rebuild:

- model-provider infrastructure;
- general-purpose agent frameworks;
- coding agents;
- sandbox/container fleets;
- distributed schedulers and worker queues;
- generic workflow orchestration;
- agent-to-agent messaging platforms;
- generic tracing/observability backends;
- artifact/object storage platforms;
- experiment dashboards and registries;
- vector databases;
- generic MLOps infrastructure;
- API gateways;
- UI frameworks;
- notification systems.

A batteries-included local configuration is still desirable. Shipping a local command runner, SQLite store, basic artifact directory, structured logging, HTTP projection, or MCP projection does **not** mean libRSI owns those infrastructure categories as product areas.

The rule is:

> **Own the semantic contract; ship thin useful defaults; integrate mature infrastructure behind replaceable interfaces.**

---

# 4. External systems are capability implementations

libRSI should be able to use external systems without giving them epistemic authority.

Examples:

```text
DSPy / GEPA
    candidate generation or optimization of LLM programs

AFlow-style search / other workflow search
    candidate/search strategy

Optuna or another numerical optimizer
    parameter candidate generation/search

Software Factory / Codex / OpenHands / SWE-style systems
    software inspection, implementation, experimentation, application, verification

MLflow / W&B / another experiment platform
    experiment-run/artifact projection and visualization

LangGraph / Prefect / another workflow engine
    optional execution/orchestration of libRSI actions
```

libRSI remains responsible for how exact inputs, claims, evidence, candidates, decisions, applications, and outcomes relate.

An optimizer may propose the next candidate. It must not automatically define whether that candidate is an accepted improvement.

An experiment backend may execute and store a trial. It must not automatically define whether that observation is valid evidence for a claim.

A workflow system may schedule an action. It must not become the authoritative libRSI lifecycle model.

---

# 5. Block amendments

## Block 3 — General epistemic model

No change to the core goal. Strengthen the boundary:

- `EvidenceAggregator` defines semantic aggregation policy;
- storage/tracing/experiment dashboards do not define epistemic truth;
- external reasoners may propose claims or interpretations but cannot promote them directly to validated knowledge.

## Block 4 — Generic experiments / measurements / metrics / evaluation

Block 4 owns the ontology and deterministic interpretation of:

```text
ExperimentSpec
Trial
Observation
Measurement
Metric
DecisionRule
ExperimentEvaluation
valid / invalid / inconclusive
baseline / candidate comparison
```

It does **not** aim to become a generalized experiment-tracking/MLOps platform.

Add to acceptance:

- experiment semantics can be projected to or executed by an external experiment backend without changing canonical libRSI identities/evaluation;
- no dashboard, registry, artifact platform, or model registry is required for Block 4 completion.

## Block 5 — Targets/currentness

Add an **early domain-neutrality sentinel**.

In addition to software examples, Block 5 must maintain at least one deterministic non-software target fixture, such as:

- a parameterized numerical simulation;
- a structured document;
- a synthetic process/configuration target.

Add to acceptance:

- the non-software fixture can be snapshotted and currentness-checked using only generic target semantics;
- no Git/repository field is required by generic target code.

This is an early sentinel, not the final cross-domain proof of Block 24.

## Block 6 — KnowledgeStore

Keep the current distinction between knowledge state and runtime state.

Clarify scope:

- own the `KnowledgeStore` contract, semantic retrieval/currentness behavior, provenance, and a minimal SQLite reference implementation;
- do not turn Block 6 into a vector-database, analytics, data-lake, experiment-dashboard, or knowledge-graph platform project;
- external storage backends may satisfy the same contract later.

## Block 7 — Run/Event/State/Action engine

Block 7 owns the **semantic runtime**, not a competing generic workflow/orchestration platform.

Split the conceptual responsibility:

```text
7A Semantic runtime
    Run
    RunState
    Event
    Action
    ActionResult
    Transition
    replay/idempotence/correlation/budgets

7B Reference durability
    append-only event persistence
    materialized state
    SQLite reference store
```

Explicitly out of scope for Block 7:

- distributed worker scheduling;
- generalized task orchestration;
- worker-fleet management;
- generic retry queues independent of run semantics;
- agent messaging buses;
- tracing platforms.

External orchestrators may execute libRSI `Action`s provided they return canonical `ActionResult`s and do not become a second lifecycle authority.

## Block 8 — Capability protocols

Keep the existing capability families and add the following architectural rule:

> Search, candidate generation, optimization, execution, and storage strategies are replaceable capability implementations.

Do not create one monolithic `Optimizer` that owns evaluation/acceptance. If an optimizer/search capability is introduced, its authority ends at proposing candidates/search work. Evaluation and selection remain governed by libRSI semantic contracts.

Add an early dogfood:

- exercise at least one capability against the Block 5 non-software target fixture.

## Block 9 — Reasoner contract

No core change. Clarify that DSPy/GEPA or other LLM-program optimizers may be used behind reasoner/candidate-generation contracts, but model output remains a proposal rather than epistemic authority.

## Block 10 — Validation workflow

Add an early non-software validation dogfood to acceptance:

- one deterministic non-software claim can be validated through the same generic workflow used for software targets;
- no repository/test/patch assumptions appear in generic validation code.

This should run in CI once Block 10 is functional.

## Block 12 — Intervention/candidate lifecycle

Maintain the current universal semantic envelope and extensible domain-specific specification.

Add to acceptance:

- the non-software fixture can express at least one intervention/candidate without adding domain-specific fields to generic core records.

## Block 13 — Goal / EvaluationContract

No major scope change. Keep operationalization and typed evaluation contracts in libRSI. External optimizers may consume those contracts, but they do not replace them.

## Block 14 — Comparative evaluation / selection / search

Clarify ownership:

libRSI owns:

```text
comparison semantics
metric/guardrail interpretation
minimum meaningful effect
uncertainty handling
risk-adjusted acceptance
Pareto/non-dominated representation
“none accepted”
selection provenance
```

External systems may own:

```text
how candidate N+1 is generated
how a search space is traversed
which optimizer algorithm proposes the next trial
```

Block 14 should define a replaceable search/candidate-generation boundary where useful, but must not reimplement mature optimization algorithms merely to satisfy the Block.

## Block 15 — Complete improvement workflow

Add an **early cross-domain improvement dogfood** to acceptance.

The Block should not be considered fully accepted until the same improvement engine can complete:

1. one software-oriented deterministic/synthetic improvement; and
2. one small deterministic non-software improvement.

The non-software case can be deliberately simple; its purpose is to catch ontology leakage before later integrations harden around software assumptions.

Block 24 remains the comprehensive final cross-domain proof across validation, investigation, and improvement.

## Block 18 — Batteries-included local runtime

Keep this Block, but make its scope explicitly reference-oriented.

Reference defaults may include:

- SQLite;
- local command execution;
- basic filesystem inspection;
- local artifact persistence;
- structured logging/events.

Add this invariant:

> These defaults exist to make `pip install librsi` useful. They do not establish libRSI ownership of generic process execution, artifact storage, logging, orchestration, or repository automation as independent platforms.

Every default must remain independently replaceable.

## Block 19 — Outcomes and external consumption

Treat outcome semantics as **incremental**, not something first invented late in the program.

### 19A — workflow-owned result contracts

Introduce/complete result contracts alongside the workflow that needs them:

```text
Block 10 → ValidationResult
Block 11 → InvestigationResult
Block 15 → ImprovementResult
Block 17 → RSIResult
```

These must share the canonical `Outcome` substrate established by Block 1.

### 19B — stable projection/consumption layer

Block 19 completes:

- stable versioned JSON projections;
- event-stream projections;
- persistent projections;
- cross-mode equivalence;
- consumer-facing schema stability.

This prevents each workflow from inventing incompatible results while avoiding premature freezing of incomplete output schemas.

## Block 20 — CLI / external-agent protocol

Keep the current role. It remains the first non-Python projection worth exercising once `Run / Action / ActionResult / Outcome` contracts stabilize.

Do not let CLI concerns redefine the runtime or workflow semantics.

## Block 20A — Server / service API / MCP

Keep Block 20A, but **defer compatibility commitment** until the semantic interfaces it projects are stable.

The effective hard prerequisites are:

```text
Block 7  Run / Action / ActionResult semantics stable
Block 8  capability/authority semantics stable
Block 19 outcome/serialization contracts stable enough for transport
Block 20 external-agent schemas substantially stable
```

Transport-independent `LibRSIService` design may begin earlier, but HTTP/MCP schema stabilization and broad public surface should not get ahead of those contracts.

HTTP and MCP are thin optional transports, not a libRSI product moat and not separate workflow engines.

## Block 21 — Provider and optional integration adapters

Broaden the interpretation of this Block from only “hosted model provider” to optional capability/backend adapters that have stable core contracts.

Reasoner/provider support remains the first required adapter.

Other optional adapters may include, when useful and justified:

- DSPy/GEPA-style optimizer integration;
- numerical optimizer integration;
- external experiment-tracking projection;
- external workflow/orchestrator action execution.

These are not required merely for ecosystem completeness. Add an adapter only when it validates a useful contract or serves a real dogfood/integration need.

## Block 22 — Software Factory consumer integration

Block 22 remains the **final acceptance gate** for Software Factory integration, but the workstream must begin incrementally much earlier.

The integration track is:

```text
Q1 after Block 8 contract work
    map Software Factory capabilities to libRSI capabilities/actions

Q2 after Block 5
    map Software Factory target/revision state to TargetSnapshot

Q3 after Block 12
    map Software Factory candidate/worktree/effect state to Intervention/Candidate

Q4 after Block 15
    complete a Software Factory-backed improvement workflow

Q5 after Block 16
    integrate application/post-application verification where appropriate
```

Do not wait until every product/interface Block is complete before testing these mappings.

The dependency direction remains strictly:

```text
Software Factory → imports/consumes libRSI
```

never the reverse.

## Block 23 — End-to-end dogfoods

Keep Block 23 as a convergence/system-proof Block, but do not defer all end-to-end testing until it.

Each earlier Block must add deterministic dogfoods as soon as a vertical slice becomes possible.

Block 23 collects and extends those into the complete system matrix.

## Block 24 — Cross-domain proof

Retain Block 24.

Its role changes from “first time we check domain neutrality” to **final comprehensive proof that domain neutrality survived the complete system**.

By Block 24, the non-software sentinel introduced in Blocks 5/8/10/12/15 should already be a maintained test fixture. Block 24 extends it through the full intended validation/investigation/improvement surface and verifies no later software integration leaked into the core.

## Block 25 — Public API / release gate

Public positioning should lead with evidence-driven validation, investigation, and improvement, with governed recursive self-improvement as an advanced mode.

Do not claim infrastructure ownership or planned capabilities that are only provided by optional adapters/backends.

---

# 6. Revised parallel workstreams

The original parallel plan remains broadly correct. The following additions are normative.

## Stream X — Cross-domain sentinel

Start with Block 5 and maintain continuously thereafter.

```text
Block 5
    non-software target + snapshot/currentness

Block 8
    generic capability against non-software target

Block 10
    non-software validation

Block 12/13
    non-software intervention + evaluation contract

Block 15
    non-software improvement

Block 24
    comprehensive final cross-domain proof
```

This is not a separate product implementation; it is a persistent architectural test.

## Stream Q — Software Factory integration

Begin incrementally after relevant contracts freeze, as described above. Do not wait for late Block 22 final acceptance.

Its purpose is to expose bad abstractions early while keeping Software Factory operational concerns out of libRSI core.

## Stream P — optional integrations

Provider/optimizer/backend adapters begin only after the corresponding core contract is stable. They must not be allowed to redefine canonical records or workflow semantics.

## Server/MCP placement

Do **not** prioritize HTTP/MCP implementation merely because a server skeleton can technically be built after Block 7.

Recommended sequence:

```text
Freeze C
Run / Action / ActionResult / Capability
        ↓
exercise stepped Python/external-host API
        ↓
Outcome/result schemas stabilize with real workflows
        ↓
CLI/external-agent schema stabilizes
        ↓
LibRSIService
        ↓
HTTP + MCP projections
```

A transport-independent service facade may be prototyped earlier, but it should not create compatibility obligations around incomplete workflow schemas.

---

# 7. Revised implementation waves

## Wave 1 — current foundation fan-out

After Blocks 0–2:

```text
A  Block 3 — epistemics
B  Block 4 — generic experiments
C  Blocks 5–6 — targets + knowledge
D  Block 7A / 8A — semantic runtime + capability contracts
E  early 12/13/19A contracts where interfaces are sufficiently frozen
X  begin non-software target sentinel with Block 5
```

## Wave 2 — first useful vertical slice

```text
7B/8B runtime durability + dispatch
9 reasoner contract
10 validation
12 intervention lifecycle
13 evaluation contracts
19A ValidationResult
Q1/Q2 Software Factory mapping as contracts permit
X non-software validation dogfood
```

The **first major convergence remains Validation**.

## Wave 3 — investigation and optimization

```text
11 investigation
14 comparative selection/search boundary
18 local façade scaffold
21 reasoner/optimizer adapters only where useful
Q3 Software Factory intervention/candidate mapping
19A InvestigationResult
```

## Wave 4 — improvement convergence

```text
15 improvement
16 application semantics in parallel where ready
18/19 completion around real workflows
Q4 Software Factory improvement
X non-software improvement dogfood
```

## Wave 5 — application and RSI

```text
16 complete apply/verify/rollback
17 RSI/meta-governance
Q5 Software Factory application/verification
19A RSIResult
```

## Wave 6 — product projections and final proofs

```text
20 CLI/external-agent stabilization
20A server/MCP after the projected contracts are stable
23 system dogfoods
24 comprehensive cross-domain proof
25 release/docs
```

Provider/backend adapters may proceed in parallel once their contracts are frozen, but they are not on the semantic critical path unless a real dogfood depends on them.

---

# 8. Acceptance discipline for future Blocks

For every future Block, reviewers should ask:

1. **Is this semantic product logic, or are we rebuilding infrastructure another project already owns?**
2. **Could this implementation be replaced behind a protocol without changing libRSI records/outcomes?** If yes, prefer a capability/backend boundary.
3. **Does this Block accidentally make software/Git concepts fundamental?** Check the maintained non-software sentinel.
4. **Does a provider/optimizer/executor gain epistemic or application authority merely because it produced a result?** It must not.
5. **Does transport or orchestration introduce a second lifecycle/state model?** It must not.
6. **Can the same exact semantic transition be driven externally or automatically?** Control-plane neutrality must remain true.
7. **Does this work improve the core validate/investigate/improve/recurse lifecycle?** If not, question whether it belongs in libRSI core.

---

# 9. Completion test for independent value

A strong proof that libRSI deserves to exist as an independent library is:

```text
Can the same libRSI semantic engine drive:

1. a Software Factory-backed improvement run; and
2. a materially non-software improvement run;

while preserving:

exact target/currentness
exact evidence lineage
candidate comparison
application separation
post-application verification
rollback semantics
control-plane neutrality
stronger governance for self-change

without either host leaking its ontology into the core?
```

The implementation program should optimize toward making that answer clearly **yes**.

---

## Update log

- **2026-08-21:** Added after architecture review of the implementation program. Clarified semantic-product versus infrastructure ownership, promoted incremental Software Factory consumption and early non-software dogfoods, made external optimizers/backends replaceable capability implementations, staged Outcome contracts earlier, and deferred HTTP/MCP compatibility commitment until runtime/outcome/external-agent contracts stabilize.