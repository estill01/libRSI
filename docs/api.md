# Public API guide

libRSI has one semantic engine with three public altitudes. Use the highest altitude
that exposes the control you need.

## Small embedded improvement

From an installed checkout, run
`python examples/embedded_improvement.py --data-dir ./my-first-improvement`.
The [self-contained example](../examples/embedded_improvement.py) minimizes
`abs(4 - x)` from `x=0`, requiring a decrease of at least 2. Measured candidates
`x=1` and `x=3` have errors 3 and 1: libRSI rejects the first and selects the second.
Two cycles, two candidate comparisons, four hypothesis experiments, and explicit
resource limits keep the run bounded. Deterministic repetitions demonstrate record
composition; they are not a claim of statistical independence for real measurements.

The host supplies a typed `ImprovementRequest` (goal, baseline, criterion, hypotheses,
risk policy, and budget) and an `ImprovementCycleProvider`. Its `resource_claim(action)`
declares the exact persisted per-attempt cap; `improve_cycle(action)` performs the
domain work and returns measured investigation/candidate records. The example host
uses no SDK or credentials. A reasoning adapter alone does not supply candidate
implementation or experiments; missing capabilities remain a frontier or error.
Optional model configuration is described in [providers.md](providers.md).

`LibRSI.start(request)` returns the public handle; `next()` exposes its step frontier
and `run()` persists accepted updates before dispatching another host effect. The
example intentionally interrupts before cycle 2, closes its store, recreates the
same request, and reopens `SQLiteRuntimeStore`. Resume uses the public
`ImprovementWorkflow.resume` and `run_managed(..., on_update=...)`, with
`persist_transitions` saving each update. The facade does not yet expose a resume
convenience. Real hosts must re-observe their target and pass its current snapshot;
the demo target is immutable. A selected `ApplicationHandoff` is a result to inspect,
and applying it requires separate explicit authority.

Use one serialized owner per working database, small run histories, and a small
knowledge corpus. Avoid overlapping managed calls: there are no cross-owner action
leases or exactly-once provider effects. SQLite appends still validate the full
history; knowledge queries can scan the corpus and make repeated lookups. Optional
HTTP/service use is serialized and can block during managed work. Long histories,
concurrent service operation, storage redesign, broader search policies, provider
lifecycle redesign, and broad API cleanup remain deferred until a concrete use case
needs them. Local command root restrictions validate cwd only; they do not sandbox
filesystem access. POSIX timeouts clean up owned process groups, but cannot contain
descendants that deliberately leave the group.

## Facade-first use

`LibRSI.local(path)` creates an isolated local composition with replaceable SQLite
runtime and knowledge stores, an argv-only command runner, deterministic filesystem
inspection, immutable artifacts, and structured transition logging. `LibRSI.for_repo`
is the explicitly software-repository-shaped convenience; it does not change generic
workflow records.

Filesystem snapshots include file content, symlink targets, and executable mode
bits. Incidental timestamp changes do not alter the revision. Snapshots produced
before executable bits were included may compare stale after upgrading; recapture
the target and re-evaluate affected evidence instead of rewriting historical roots.

The facade owns these entry paths:

| Method | Input | Result or frontier | Authority boundary |
|---|---|---|---|
| `claim`, `question`, `snapshot` | local declarations | canonical records | observation only |
| `validate` | claim plus evidence or configured collector | `ValidationResult` | evidence collection remains a capability |
| `test_hypothesis` | hypothesis, argv, immutable criteria | `HypothesisTestResult` | local runner validates cwd against its configured root; no filesystem sandbox |
| `investigate` | question or `InvestigationRequest` | `InvestigationResult` | only configured automatic reasoning/experiment routes run |
| `improve` | `ImprovementRequest` | `ImprovementResult` | selection produces a handoff, not application authority |
| `recurse` | `RSIRequest` | `RSIResult` or a stopped `LibRSIRun` | self-change gates and activation authority remain mandatory |
| `start` | any public workflow request | `LibRSIRun` | caller may own the external action loop |

`LibRSIRun.next()` returns the exact canonical pending `Action`. `submit()` accepts the
matching typed `ActionResult`; `run()` advances only automatic routes. External,
human-reserved, unavailable, and application-authority frontiers stop without being
silently converted into success.

## Service and protocol projections

`librsi.service.LibRSIService`, the `librsi` CLI, HTTP, and MCP projections wrap the same
external-agent controller and persistence contracts. They do not own another state
machine. The base wheel installs the core CLI and zero dependencies. HTTP and MCP are
separate extras:

```bash
python -m pip install 'libRSI[server]'  # FastAPI and Uvicorn
python -m pip install 'libRSI[mcp]'     # MCP transport
python -m pip install 'libRSI[service]' # both projections
```

These commands describe release metadata; installation or redistribution remains
subject to the repository's selected license posture. Non-loopback service binding
fails closed without the documented bearer configuration.

## Provider adapters

The provider-neutral `ReasoningBackend` and `StructuredReasoner` are the public semantic
boundary. `libRSI[openai]` and `libRSI[providers]` install the published OpenAI SDK.
Provider outputs remain schema-validated proposals and never become evidence,
application authority, or acceptance merely because a model produced them.

The exact utils-backed Codex app-server adapter is an internal, interface-only lane. It
has no public extra or registry requirement while its producer package remains
unpublished and unlicensed. See [providers.md](providers.md).

## Expert surface and typing

`librsi.expert` is a curated composition namespace for the kernel, selected workflow
policies/workflows, capability dispatcher/registry, runtime engine, and SQLite stores.
Typed records, capability protocols, and projection codecs remain in their owning
modules and in the documented top-level exports; `librsi.expert` does not duplicate
them. Top-level `librsi.__all__` retains every `0.2.0` compatibility export and the
additive `0.3.0` surface. The distribution includes `py.typed`; public records,
protocols, and facade methods are statically typed and checked on Python 3.11, 3.12,
and 3.13.

Canonical records are immutable and content-addressed. Hosts own filesystems,
subprocesses, providers, credentials, deployment, authoritative target observation, and
application effects. Successful dispatch or implementation is never evidence of
improvement; verification evaluates the actual host-observed state.

## Adaptive operation through consumer use

`AdaptiveLoop`, `LearningPolicy`, `LearningCase`, `LearningAdapter`, `TaskMeasurement`, `LearningResult`, and `LocalLearningStore` provide the public opt-in composition for measured feedback, bounded strategy revisions, durable restart and governed next-task adoption. See the [adapter contract and scheduling guide](adaptive-operation.md) and [executable template](../examples/adaptive_strategy.py). Core dependencies remain empty.
