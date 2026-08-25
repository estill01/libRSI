# Public API guide

libRSI has one semantic engine with three public altitudes. Use the highest altitude
that exposes the control you need.

## Facade-first use

`LibRSI.local(path)` creates an isolated local composition with replaceable SQLite
runtime and knowledge stores, an argv-only command runner, deterministic filesystem
inspection, immutable artifacts, and structured transition logging. `LibRSI.for_repo`
is the explicitly software-repository-shaped convenience; it does not change generic
workflow records.

The facade owns these entry paths:

| Method | Input | Result or frontier | Authority boundary |
|---|---|---|---|
| `claim`, `question`, `snapshot` | local declarations | canonical records | observation only |
| `validate` | claim plus evidence or configured collector | `ValidationResult` | evidence collection remains a capability |
| `test_hypothesis` | hypothesis, argv, immutable criteria | `HypothesisTestResult` | local runner executes only inside its configured root |
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
