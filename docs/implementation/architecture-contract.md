# libRSI Architecture Contract

**Program:** Architecture Expansion, Block 0  
**Baseline:** libRSI `0.2.0` at `d96cc666c7800681dfdde2f991f841b09155dfe8`  
**Status:** Maintained implementation contract

This document defines the architectural boundaries that later implementation Blocks must preserve unless an explicit architecture revision supersedes them. It is intentionally more stable than the implementation-status ledger.

The maintained planning amendment [`scope-boundaries-and-early-dogfood-revision.md`](scope-boundaries-and-early-dogfood-revision.md) further constrains implementation scope and ordering. Where that amendment narrows older implementation-tracker wording, the narrower maintained boundary applies.

## 1. Product scope

libRSI is a composable framework for evidence-driven validation, investigation, problem solving, improvement, and recursive self-improvement.

The product should be understood and eventually positioned primarily as:

> **A domain-neutral, evidence-driven validation, investigation, and improvement engine with exact provenance, resumable semantic workflows, candidate/application separation, and stronger governance for self-change.**

Recursive self-improvement is an important advanced composition of the framework, not the ontology from which every lower-level capability must inherit.

The reusable semantic layers are:

```text
Target / TargetSnapshot
        ↓
Claims / Questions / Goals / Constraints
        ↓
Evidence / Knowledge
        ↓
Experiments / Measurements / Evaluation
        ↓
Validation / Investigation
        ↓
Interventions / Candidates / Selection
        ↓
Improvement
        ↓
RSI / meta-improvement
```

A validation or investigation run must not require a change proposal. An improvement run may produce a change proposal without applying it. An RSI run uses the same underlying machinery while allowing some portion of the improvement machinery itself to be a target.

The intended public progression is:

```text
validate
→ investigate
→ improve
→ recurse when appropriate
```

## 2. Canonical semantic distinctions

### Target is not knowledge

A `Target` identifies the subject being inspected, reasoned about, measured, or potentially changed. A `TargetSnapshot` identifies an exact/current state of that target.

`Knowledge` is accumulated belief/evidence about a target or domain. Historical knowledge may remain useful after the target has changed, but target-bound evidence must retain the snapshot/currentness against which it was established.

### Intent is not belief

The framework distinguishes at least these intent-bearing propositions:

- `Claim` — something that may be true;
- `Question` — something to determine or understand;
- `Goal` — something to make true;
- `Constraint` — something that must remain true.

A hypothesis is an epistemic object, normally a provisional/testable claim. It is not the default user-facing representation of a goal.

### Experiment is not execution mechanism

An `Experiment` is a specification for generating discriminating evidence. Command execution, simulation, benchmark execution, shadow traffic, physical experimentation, model training, or another mechanism may implement an experiment.

The command experiment currently present in `0.2.0` becomes an adapter/convenience form rather than the universal experiment ontology.

### Invalid execution is not negative evidence

Experiment validity is distinct from experiment outcome. Infrastructure failure, malformed execution, timeout, or inability to obtain a requested observation does not by itself count as evidence against the claim or hypothesis being tested.

### Intervention is not authoritative application

An `Intervention` describes a proposed change. An `Implementer` may turn an intervention into a `Candidate`, which is a prospective target state.

A candidate does not become authoritative merely because it was produced, tested, or selected. Authoritative application is a separate lifecycle step performed through an `Applier` or an external owner.

The generic lifecycle is approximately:

```text
Intervention
    ↓
Implementer
    ↓
Candidate
    ↓
Experiment / Evaluation / Selection
    ↓
Accepted Candidate
    ↓
Applier or external application owner
    ↓
Authoritative TargetSnapshot
    ↓
Verification
```

### Passing execution is not verified improvement

A command, test, benchmark, review, or implementation step completing successfully is only an observation about that step. Improvement requires evaluation against the exact goal/evaluation contract, relevant guardrails, evidence validity, and—after application where applicable—the exact authoritative target state actually produced.

### Ordinary improvement is not ungoverned self-change

When the target includes machinery that determines future reasoning, evidence interpretation, selection, promotion, or governance, stronger self-change controls apply. A self-change candidate may not gain authority merely because it proposes or evaluates itself favorably.

## 3. Control-plane neutrality

All workflows must support the same semantic execution in three modes.

### Externally driven

```python
run = lib.start(...)

while action := run.next():
    result = host.handle(action)
    run.submit(result)
```

The host owns the outer loop.

### libRSI-driven

```python
lib = LibRSI(capabilities=[...])
result = lib.improve(...)
```

libRSI dispatches actions through configured capability implementations.

### Hybrid

libRSI may automatically execute some action types while surfacing others to an external host or reserved human authority.

### Invariant

These modes must share the same `Run`, `State`, `Event`, `Action`, `ActionResult`, evidence, experiment, intervention, and outcome semantics. There must not be separate embedded and managed state machines.

Managed execution is convenience dispatch around the same action/result transition model exposed to external hosts.

External workflow/orchestration systems may schedule or execute libRSI actions, but they must not become a second authoritative libRSI lifecycle model.

## 4. Domain neutrality

The core must not require software-specific concepts such as repositories, commits, patches, worktrees, builds, or pull requests.

A software target may expose those concepts through software-specific target/capability implementations, but generic workflows must also support targets such as:

- models;
- datasets and knowledge systems;
- structured documents;
- processes and configurations;
- simulations;
- physical systems;
- externally owned systems that libRSI can inspect but cannot mutate directly.

Multi-component targets are first-class. A software system composed of multiple repositories is one example, not a special case in the core ontology.

Domain neutrality must be tested continuously rather than deferred to a final audit. Once generic target/currentness contracts exist, the implementation program must maintain at least one deterministic non-software fixture and progressively exercise it through capabilities, validation, interventions, evaluation contracts, and improvement. The final cross-domain Block remains the comprehensive proof that later integrations did not leak software assumptions back into the core.

## 5. Capability ownership and inversion of control

libRSI defines generic capability contracts. Implementations may be built in, supplied by the embedding application, exposed by an external agent, or reserved to a human/operator.

Expected capability families include:

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

A single runtime object may implement multiple capability protocols.

Capability availability must be explicit. Missing mutation authority must not be confused with failed implementation or failed scientific evidence.

Search, candidate generation, optimization, experiment execution, and storage strategies are replaceable implementations behind stable libRSI semantic contracts. If a search/optimizer capability is introduced, its authority ends at proposing candidates, experiments, or search work; libRSI evaluation and selection semantics determine whether those proposals are accepted.

External systems can therefore implement capabilities such as:

```text
LLM-program/prompt optimization
workflow-structure search
numerical parameter search
software inspection/implementation
experiment execution/tracking
workflow scheduling
```

without becoming the source of epistemic truth, candidate acceptance, or application authority merely because they produced a result.

High-level systems such as Software Factory consume libRSI and implement libRSI capability contracts. libRSI must not import or depend on Software Factory.

The allowed dependency direction is:

```text
libRSI
  ▲
  │ imports
  │
consumer / Software Factory / other host
```

not:

```text
libRSI → Software Factory
```

Consumer integration should begin incrementally as relevant contracts freeze rather than waiting until every libRSI product surface is complete. Final integration acceptance remains a late convergence gate.

## 6. Core semantic product versus infrastructure platforms

libRSI owns the **semantics and integrity rules** of knowing, asking, testing, interpreting evidence, operationalizing goals, proposing interventions, forming candidates, comparing/selecting candidates, requesting or authorizing application, verifying outcomes, learning, and governing self-change.

It should not grow into a competing general-purpose platform for concerns that can be replaced behind those semantic contracts.

The following are normally adapters, backends, transports, or thin reference implementations rather than independent libRSI platform products:

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

The governing rule is:

> **Own the semantic contract; ship thin useful defaults; integrate mature infrastructure behind replaceable interfaces.**

A backend may store or visualize an experiment without deciding whether its observation is valid evidence. An optimizer may propose a candidate without deciding whether it is an accepted improvement. An orchestrator may execute an action without defining libRSI lifecycle state.

## 7. Deterministic core versus batteries-included product

The current `0.2.0` implementation deliberately keeps database, process, filesystem, and provider effects outside the package. That is no longer a constraint on the complete product.

The new architecture retains a deterministic core for identity, policy, evaluation, and state-transition semantics while permitting libRSI to ship useful default implementations around that core, including persistence, local execution, service/CLI surfaces, and optional provider/integration adapters.

The design target is:

> batteries-included but replaceable

not:

> pure policies only; every practical concern belongs to every consumer

and not:

> batteries-included means rebuilding every infrastructure category inside libRSI

Reference defaults exist to make `pip install librsi` useful. They must remain thin and independently replaceable.

The deterministic core must remain independently testable and usable by sophisticated hosts.

## 8. Persistence boundaries

Two kinds of persisted state are conceptually distinct even if one backend stores both:

### Runtime state

Authoritative execution state for a particular run:

- events;
- actions and action results;
- lifecycle/status;
- retries/failures;
- budgets;
- current transition state;
- terminal outcome.

Runtime state must support replay, idempotence, interruption, and resume.

The runtime owns these semantic durability guarantees. It does not need to own distributed worker scheduling, generalized task orchestration, or a tracing platform.

### Knowledge state

Reusable accumulated understanding:

- claims and hypotheses;
- evidence;
- observations and measurements;
- experiments and evaluations;
- target snapshots/currentness;
- interventions and outcomes;
- lineage, provenance, causal/dependency relationships.

Knowledge survives individual runs and may be reused when its target/currentness conditions remain valid.

The core knowledge layer owns semantic retrieval/currentness behavior and a storage contract. A SQLite reference implementation is appropriate; a generalized data/analytics/vector/experiment platform is not required.

## 9. Evidence and epistemic integrity

Reasoning output, successful command execution, passing tests, commits, reviews, optimizer scores, and attractive narrative are not automatically truth.

The epistemic layer owns the relationships between claims and evidence and must retain exact provenance.

Core requirements include:

- infrastructure failure is not evidence against a hypothesis;
- experiment validity is distinct from experiment outcome;
- success/evaluation criteria are identity-bound to the exact experiment specification;
- observations/results are correlated to the exact execution input that produced them where applicable;
- evidence retains the exact claim/hypothesis and target snapshot it bears on;
- conflicting evidence may coexist without being silently discarded;
- belief/confidence aggregation is policy-driven rather than permanently hard-coded to one scalar update rule;
- an external reasoner, optimizer, executor, tracker, or workflow system cannot promote its own output directly to validated knowledge merely by returning success.

## 10. Public workflow layers

### Validation

Primary intent: determine whether a claim is supported, contradicted, bounded, or inconclusive.

Validation may reuse existing knowledge and may request additional observations or experiments. It requires no intervention.

### Investigation

Primary intent: reduce uncertainty around a question.

Investigation may generate and refine competing hypotheses, gather evidence, redesign experiments, branch, abandon unproductive approaches, and return unresolved items as well as supported conclusions.

### Improvement

Primary intent: achieve a goal subject to constraints.

Improvement composes investigation, intervention generation, candidate implementation, comparative experimentation, selection, optional application, verification, and learning.

### RSI

RSI is improvement in which some portion of the machinery that performs understanding, experimentation, selection, reasoning, resource allocation, or improvement is itself part of the target.

RSI uses the same ordinary records and workflow semantics plus stronger self-change governance such as historical evaluation, forward shadowing, independent evaluation, activation gates, and rollback.

## 11. Outcome semantics are workflow-level contracts

`Outcome` is part of the canonical semantic substrate, not merely a late presentation layer.

Specialized result contracts should emerge alongside the workflows that require them:

```text
Validation → ValidationResult
Investigation → InvestigationResult
Improvement → ImprovementResult
RSI → RSIResult
```

A later outcome/projection Block stabilizes external JSON/event/persistent projections and cross-mode schema equivalence. It should not be the first point at which workflows define consumable semantic results.

## 12. Service and protocol projections

Python embedding, CLI, HTTP/service APIs, MCP, and external-agent protocols are interface projections over the same canonical runtime.

They must not create separate run semantics, evidence models, or persistence authorities.

Durable run identity belongs to libRSI runtime state, not to a transport session.

The service/MCP surface is useful but not on the semantic critical path. A transport-independent service facade may be designed earlier, but HTTP/MCP compatibility should not be stabilized until `Run / Action / ActionResult / Capability`, outcome serialization, and the shared external-agent schemas are sufficiently stable from real workflow use.

Transport availability never implies application authority.

## 13. Namespace and ownership plan

The physical package may migrate incrementally. New functionality should be placed under the appropriate semantic owner; existing modules move when touched rather than through a disruptive all-at-once rename.

Target conceptual ownership:

| Current / planned area | Semantic owner |
|---|---|
| `identity.py` | core identity / canonical serialization |
| `models.py` | transitional; split into domain-owned immutable records |
| `hypotheses.py` | epistemics |
| `experiments.py` | experiments; current command logic becomes an adapter/convenience layer |
| `checkpoints.py` | core currentness/materiality and runtime checkpoint policy |
| `portfolios.py` | search/exploration scheduling primitives, not a generic optimizer platform |
| `programs.py` | intervention/currentness/application policy precursor |
| `selections.py` | selection invariants and later comparison/acceptance policy |
| `reviews.py` | governance/review primitives |
| `selector_policies.py` | RSI/meta-intervention governance |
| `ports.py` | transitional; expand/split into generic capability protocols |
| `kernel.py` | deterministic composition/transition core, not primary end-user workflow API |
| planned target records/adapters | `targets` ownership |
| planned persistent epistemic retrieval | `knowledge` ownership |
| planned run/event/action engine | `runtime` ownership |
| planned intervention/candidate lifecycle | `interventions` ownership |
| planned validation/investigation/improvement compositions | workflow ownership |
| planned optimizer/provider/backend adapters | `integrations` ownership behind core contracts |
| planned server/CLI/MCP | interface/deployment ownership over canonical runtime |

A practical eventual layout may include namespaces such as:

```text
librsi/
    core/
    epistemics/
    experiments/
    targets/
    knowledge/
    runtime/
    interventions/
    workflows/
    integrations/
    server/
```

This table establishes semantic ownership, not a requirement to perform a mechanical package move before the corresponding code changes.

## 14. `0.2.0` compatibility baseline

Block 0 establishes an executable regression baseline for the current public low-level behavior before semantic refactoring begins.

The baseline intentionally protects representative behavior in:

- public exports;
- canonical identity/hash generation exposed through current policies;
- checkpoint materiality;
- reflections and hypothesis updates;
- command experiment construction/evaluation;
- program-change identity/application guards;
- sequential/parallel portfolio transitions;
- review independence;
- selection review/eligibility;
- selector-policy evaluation/activation/rollback gates.

Later Blocks may introduce superior canonical records and APIs, but existing low-level behavior must either remain available through compatibility wrappers or be deliberately migrated with explicit release/migration documentation. It must not drift accidentally.

The compatibility check is intentionally additive: legacy `0.2.0` exports must remain available and publicly exported, but later Blocks may add APIs and bump the package version.

The executable baseline lives in `tests/test_v020_compatibility_contract.py` with rooted fixtures in `tests/fixtures/v020_contract.json`.

## 15. Implementation-planning authority

The implementation program is maintained across:

- `architecture-expansion-implementation-tracker.md` — primary 0–25 Block definitions;
- `parallel-implementation-plan.md` — dependency/workstream execution strategy;
- `scope-boundaries-and-early-dogfood-revision.md` — normative scope/order amendments;
- maintained extension Block documents such as `server-mcp-implementation-block.md`;
- `implementation-status.md` — current implementation accounting only.

The scope/dogfood revision specifically requires:

- early non-software target/capability/validation/intervention/improvement sentinels rather than waiting until the final cross-domain Block;
- incremental Software Factory consumption as contracts freeze rather than waiting until final Block 22 acceptance;
- external optimizers/orchestrators/experiment platforms as replaceable implementations rather than core semantic owners;
- a semantic runtime rather than a competing generic workflow engine;
- workflow result contracts before late projection/schema stabilization;
- delayed HTTP/MCP compatibility commitment until projected contracts stabilize.

## 16. Block 0 completion boundary

Block 0 is complete when:

1. this maintained architecture contract exists;
2. every current module has an explicit future semantic owner;
3. control-plane neutrality is explicit;
4. `Target != Knowledge != Intent` is explicit;
5. candidate creation is explicitly distinct from authoritative application;
6. libRSI-driven, externally driven, and hybrid modes are all architectural requirements;
7. no libRSI dependency on Software Factory or another high-level consumer is introduced;
8. the `0.2.0` public-policy regression baseline is executable and passing;
9. the pre-existing test suite remains passing.

Later maintained revisions may sharpen implementation boundaries, as this document now does, without reopening Block 0 provided those original acceptance guarantees remain true.

No Block 1+ semantic implementation is required for Block 0.
