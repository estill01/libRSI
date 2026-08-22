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
replay-checked SQLite implementation. The separate `librsi.capabilities` package maps
exact action kinds to eight granular host protocols and explicit automatic, external,
human-reserved, or unavailable postures without creating another state machine.
The `librsi.reasoning` package adds strict provider-neutral reflection, hypothesis,
experiment-design, explanation, intervention, decomposition, and revision proposals.
Managed and external reasoners answer the same exact runtime action; their output is a
lineage-bearing proposal, never evidence, validated knowledge, or application authority.
The `librsi.validation` package is the first vertical workflow built on those primitives:
it validates a `Claim` directly, reuses only current stored evidence, emits the smallest
explicit evidence gap when needed, and returns a provenance-complete `ValidationResult`
whose disposition is supported, contradicted, bounded, or inconclusive.
The `librsi.intent` package turns declarative goals into typed `EvaluationContract`
records with exact baselines, objectives, constraints, guardrails, and stopping rules.
Operationalization proposals remain proposals; missing measurement facts are returned
explicitly instead of being invented.

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

`CapabilityDispatcher` is optional control-plane convenience around that same engine.
It invokes only explicitly supplied, automatically authorized capability objects; an
external host can submit the same exact `ActionResult`, and hybrid mode may leave other
actions external, human-reserved, or unavailable. Capability success never creates an
`Outcome`, promotes knowledge, or grants selection/application authority on its own.
Intervention dispatch is additionally fail-closed: `advance()` or `submit()` requires an
explicit `current_snapshot` and verifies it against the intervention baseline before an
Implementer is called or a result can mutate runtime state.

Structured reasoning uses the same boundary. `ReasoningRequest` binds its inputs and
exact target snapshot, `ReasoningResult` validates one of seven closed proposal schemas,
and libRSI's nonreplaceable `ReasoningResultValidator` runs immediately before either
managed or external submission mutates runtime state. The reserved `reason` action
cannot pass through the dispatcher without canonical validation and an exact reasoner
route; optional host validators run only in addition. A host can install
`StructuredReasoner` around any
object implementing the zero-provider `ReasoningBackend` protocol, or consume the
serialized reasoning `Action` itself and return the same `ActionResult`. Downstream
evidence or intervention decisions can use `require_reasoning_derivation()` to prove
that both the proposal and every original input remain in lineage.

Claim-only validation does not require a goal or intervention:

```python
from librsi import Claim, Evidence, validate

claim = Claim(statement="The service remains available", kind="behavioral")
evidence = tuple(
    Evidence(
        evidence_type="support",
        data={"sample": sample},
        subject_refs=(claim.ref,),
        source_refs=(claim.ref,),
        weight=1.0,
    )
    for sample in (1, 2)
)
result = validate(claim=claim, evidence=evidence)
assert result.disposition == "supported"
```

`ValidationWorkflow.start()`, `step()`, `submit()`, and `resume()` expose the same exact
runtime transitions and restart projection to external hosts. `resume()` returns a
`ValidationUpdate`; hosts append any returned reconciliation transitions before
continuing. `run_managed()` accepts the existing granular `Experimenter` protocol. The
workflow reconciles every direct or managed submission against the persisted canonical
frontier before mutation; when reused knowledge is present, pass the same
`knowledge_store` to `submit()` or `run_managed()` so its exact roots can be revalidated.
The convenience `validate()` path carries that store through the same transitions;
when neither current knowledge, explicit evidence, nor a collector is available it
returns an explicit inconclusive result rather than synthesizing support from narrative.
Block 10 uses the canonical built-in epistemic policy in result identity; alternate
sufficiency policies require a versioned semantic policy contract rather than silent
runtime injection.

Questions with competing explanations use the separate investigation workflow:

```python
from librsi import InvestigationRequest, InvestigationWorkflow, Question

request = InvestigationRequest.for_question(
    investigation_id="mechanism-study",
    question=Question(prompt="Which mechanism explains the observation?"),
    max_hypotheses=3,
    max_experiments=4,
)
update = InvestigationWorkflow().start(request)
assert update.progress.state.pending_actions[0].kind == "investigation-reason"
```

That first reserved action requests a structured competing-hypothesis proposal. Subsequent
frontiers request one exact experiment design or experiment at a time. Sequential mode
finishes one lane before the next; parallel mode activates all viable lanes and
round-robins the least-tested branch, preserving deterministic persistence while keeping
search alternatives live. Null or otherwise inconclusive evidence can trigger a bounded
redesign. Supported findings repeat only the exact hypothesis statement and cite its
canonical evidence; reasoner narration never becomes a conclusion. Falsified branches,
unavailable evidence, experiment/redesign budgets, and unresolved alternatives remain
explicit in `InvestigationResult`.

`InvestigationWorkflow.start()`, `step()`, `submit()`, `resume()`, and `run_managed()`
use the same Block 7 runtime. Managed Reasoner and Experimenter capabilities are invoked
only after the persisted frontier and any reused `KnowledgeStore` roots reconcile
exactly. Every reserved reasoning or experiment action embeds an `InvestigationFrontier`
containing the complete ordered branch roster and the one policy-selected active branch.
`CapabilityDispatcher` rejects investigation routes and results; only
`InvestigationWorkflow.submit()` may validate and advance this specialized state machine.
The public `derive_investigation_action()` function is the single action authority: it
derives branch selection, design-versus-experiment phase, sequence, and budget eligibility
from the complete roster, and builders, decoders, replay, and failed results require an
exact match.
Investigation experiment design uses a closed observation-only schema: a reasoner
selects `measure`, `observe`, or `retrieve`, bounded measurement identifiers, and canonical
evidence criteria. It cannot add operation/procedure payloads, intervention, candidate,
implementation, mutation, application, or target-change authority. Target changes begin in
later lifecycle blocks.

Proposed changes enter a separate intervention-to-candidate lifecycle:

```python
from librsi import InterventionSpec, InterventionWorkflow

intervention = InterventionSpec.create(
    intervention_id="bounded-change",
    baseline=current_snapshot,
    kind="host.domain_change",
    specification={"domain_owned": "payload"},
    rationale=("The cited evidence supports preparing this candidate",),
    supporting_refs=(claim.ref,),
    evidence=(supporting_evidence,),
    expected_effects={"metric": {"direction": "increase"}},
    risks=("The expected effect may not reproduce",),
    constraints=(),
    validation_plan={"measure": "metric"},
    rollback_expectations={"restore": current_snapshot.ref.to_dict()},
)
waiting = InterventionWorkflow().start(
    intervention,
    current_snapshot=current_snapshot,
).progress
assert waiting.handoff is not None
assert waiting.handoff.authority == "candidate-only"
```

`librsi.interventions` separates the universal `InterventionSpec`, exact Implementer
action/result codecs, candidate-only policy, and restartable workflow into distinct
modules. Domain data lives only in `specification`; evidence rationale, risks,
constraints, validation plan, rollback expectations, baseline currentness, and lineage
remain generic and identity-bound. Without an Implementer, the workflow returns a
complete serializable handoff. With a host-supplied Implementer, it may prepare a
prospective `CandidateSnapshot`, but the `ImplementationResult` and terminal `Outcome`
continue to name the unchanged authoritative baseline. The package intentionally has no
candidate `apply` operation, domain implementation engine, comparison, or acceptance
shortcut. The legacy low-level `Intervention` and `Candidate` records remain available;
the structured records provide explicit compatibility projections.

The base distribution ships no target, provider, subprocess, filesystem, worker, or
transport implementation. Any effects occur only inside a capability object explicitly
supplied by the host. Persistence and dispatch are opt-in; `RSIKernel` does not open a
database, infer a storage location, or construct capabilities. See
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
