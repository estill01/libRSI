# libRSI Architecture Contract

**Program:** Architecture Expansion, Block 0  
**Baseline:** libRSI `0.2.0` at `d96cc666c7800681dfdde2f991f841b09155dfe8`  
**Status:** Maintained implementation contract

This document defines the architectural boundaries that later implementation Blocks must preserve unless an explicit architecture revision supersedes them. It is intentionally more stable than the implementation-status ledger.

## 1. Product scope

libRSI is a composable framework for evidence-driven validation, investigation, problem solving, improvement, and recursive self-improvement.

Recursive self-improvement is an important composition of the framework, not the ontology from which every lower-level capability must inherit.

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

## 6. Deterministic core versus batteries-included product

The current `0.2.0` implementation deliberately keeps database, process, filesystem, and provider effects outside the package. That is no longer a constraint on the complete product.

The new architecture retains a deterministic core for identity, policy, evaluation, and state-transition semantics while permitting libRSI to ship useful default implementations around that core, including persistence, local execution, service/CLI surfaces, and optional provider integrations.

The design target is:

> batteries-included but replaceable

not:

> pure policies only; every practical concern belongs to every consumer

The deterministic core must remain independently testable and usable by sophisticated hosts.

## 7. Persistence boundaries

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

## 8. Evidence and epistemic integrity

Reasoning output, successful command execution, passing tests, commits, reviews, and attractive narrative are not automatically truth.

The epistemic layer owns the relationships between claims and evidence and must retain exact provenance.

Core requirements include:

- infrastructure failure is not evidence against a hypothesis;
- experiment validity is distinct from experiment outcome;
- success/evaluation criteria are identity-bound to the exact experiment specification;
- evidence retains the exact claim/hypothesis and target snapshot it bears on;
- conflicting evidence may coexist without being silently discarded;
- belief/confidence aggregation is policy-driven rather than permanently hard-coded to one scalar update rule.

## 9. Public workflow layers

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

## 10. Service and protocol projections

Python embedding, CLI, HTTP/service APIs, MCP, and external-agent protocols are interface projections over the same canonical runtime.

They must not create separate run semantics, evidence models, or persistence authorities.

Durable run identity belongs to libRSI runtime state, not to a transport session.

## 11. Namespace and ownership plan

The physical package may migrate incrementally. New functionality should be placed under the appropriate semantic owner; existing modules move when touched rather than through a disruptive all-at-once rename.

Target conceptual ownership:

| Current / planned area | Semantic owner |
|---|---|
| `identity.py` | core identity / canonical serialization |
| `models.py` | transitional; split into domain-owned immutable records |
| `hypotheses.py` | epistemics |
| `experiments.py` | experiments; current command logic becomes an adapter/convenience layer |
| `checkpoints.py` | core currentness/materiality and runtime checkpoint policy |
| `portfolios.py` | search/exploration scheduling primitives |
| `programs.py` | intervention/currentness/application policy precursor |
| `selections.py` | selection invariants and later comparison/optimization policy |
| `reviews.py` | governance/review primitives |
| `selector_policies.py` | RSI/meta-intervention governance |
| `ports.py` | transitional; expand/split into generic capability protocols |
| `kernel.py` | deterministic composition/transition core, not primary end-user workflow API |
| planned target records/adapters | `targets` ownership |
| planned persistent epistemic retrieval | `knowledge` ownership |
| planned run/event/action engine | `runtime` ownership |
| planned intervention/candidate lifecycle | `interventions` ownership |
| planned validation/investigation/improvement compositions | workflow ownership |
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

## 12. `0.2.0` compatibility baseline

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

## 13. Block 0 completion boundary

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

No Block 1+ semantic implementation is required for Block 0.
