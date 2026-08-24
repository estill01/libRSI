# Managed service, HTTP, and MCP

`LibRSIService` is the single transport-independent service facade. It delegates
target admission, durable run state, canonical actions/results, outcomes, and
knowledge storage to `ExternalAgentController`; `ManagedServiceRunner` is only a
bounded dispatcher over that same controller. HTTP and MCP call the facade and do
not own sessions, workflow state, scheduling, semantic decisions, or application
authority.

## Installation and entrypoints

The core library and `librsi.service` have no third-party runtime dependency.
Install optional projections from a checkout with one of:

```console
python -m pip install -e '.[server]'
python -m pip install -e '.[mcp]'
python -m pip install -e '.[service]'
```

The corresponding executables are `librsi-http` and `librsi-mcp`. HTTP uses
FastAPI/Uvicorn. MCP uses the maintained MCP Python SDK and supports local stdio
and stateless Streamable HTTP. Neither executable starts a model, coding agent,
provider, scheduler, or another app-server process. An embedding host supplies
capability implementations and owns any such provider process exactly once.

## Service lifecycle

Every run begins from a canonical `TargetAdmission`, which binds its exact target
snapshot, objective, evaluation contract, capability route and posture, application
governance requirement, evidence baseline, and resource ceilings. A caller then:

1. starts validation, investigation, improvement, or governed RSI and retains the
   explicit canonical run ID;
2. reads status or the exact next action and result schema;
3. either submits an externally produced typed result or asks the managed runner for
   one explicitly bounded pass; and
4. reads the canonical v1 outcome projection only after the run is terminal.

The SQLite admission, runtime, and knowledge stores are reopened on every process
restart. Transport sessions are never state authority. Duplicate, divergent,
out-of-order, or stale submissions are rejected by the shared controller and workflow
validators before a transition is appended.

Managed execution requires `ManagedBounds(max_actions=...)`. It resolves only exact
admitted routes that also match the process registry, executes only configured
automatic providers, and submits the resulting `ActionResult` through the same
canonical transition path used by external hosts. It stops with a structured reason
on terminal outcome, action bound, unavailable capability, external/human authority,
or application authority. Application is disabled unless the embedding caller passes
`allow_application=True`; that flag does not replace the request's identity-bound
governance approval or currentness checks. A managed composition that permits
application must also supply `current_snapshot_resolver`; libRSI calls it immediately
before apply, verify, and rollback provider effects. A missing resolver stops at
`currentness-unavailable`, and a live snapshot that differs from the persisted exact
frontier stops at `currentness-gate` with zero provider calls.

The managed improvement path can carry multiple competing hypotheses through
discriminating experiments and counterexamples, classify supported, rejected, and
inconclusive branches, construct and compare interventions, select one/many/none, and
iterate under the request's evaluation and resource contracts. Governed RSI reuses
that result and the ordinary historical replay, forward shadow, independent review,
application, produced-state verification, and rollback owners rather than introducing
a service-specific lifecycle.

## HTTP v1

`librsi-http --data-dir .librsi` binds to `127.0.0.1:8000` by default. The maintained
surface is:

| Method and path | Permission | Operation |
| --- | --- | --- |
| `GET /health` | public | process liveness only |
| `GET /ready` | read | store readiness |
| `GET /v1/capabilities` | read | workflows, routes, provider presence, and limits |
| `POST /v1/targets` | mutate | submit an exact admission |
| `POST /v1/runs/{validation,investigation,improvement,rsi}` | mutate | start a run |
| `GET /v1/runs/{run_id}` or `/status` | read | durable status |
| `GET /v1/runs/{run_id}/actions` | read | exact pending action |
| `POST /v1/runs/{run_id}/results` | mutate or apply | typed external/human result |
| `POST /v1/runs/{run_id}/resume` | mutate | canonical reconstruction |
| `POST /v1/runs/{run_id}/managed` | mutate or apply | bounded managed pass |
| `GET /v1/runs/{run_id}/outcome` | read | canonical terminal projection |
| `POST /v1/knowledge/query` | read | bounded canonical knowledge query |

Optional bearer tokens are supplied only through environment variables and remain
outside semantic records, stores, responses, capability reports, and error messages:

```console
export LIBRSI_HTTP_READ_TOKEN='...'
export LIBRSI_HTTP_MUTATE_TOKEN='...'
export LIBRSI_HTTP_APPLY_TOKEN='...'
librsi-http --data-dir .librsi
```

A read token cannot mutate; a mutate token cannot authorize application; an apply
token includes all three permissions. If any token is configured, protected endpoints
fail closed. Non-loopback binding is rejected unless bearer protection is configured.
Request bodies are bounded before canonical decoding. Pydantic request models reject
unknown fields, and service errors use the structured `librsi.external-error/v1`
envelope without echoing request bodies or secrets.

## MCP

`librsi-mcp --data-dir .librsi` starts the maintained local stdio transport. Use
`--transport streamable-http` for the current remote-capable transport. The server
publishes tools for target submission, all four workflow starts, status, next,
external result submission, resume, bounded managed execution, outcomes, knowledge,
and capabilities. It also publishes dynamic JSON resources at
`librsi://runs/{run_id}` and `librsi://runs/{run_id}/outcome`.

Generic MCP result submission accepts only external or human-reserved authority and
rejects application and rollback actions. MCP managed execution always sets
`allow_application=False`. Thus possession of MCP transport access cannot claim
automatic provider identity or application authority.

Every MCP tool/resource argument envelope is measured against the same
`ServiceLimits.max_request_bytes` ceiling before canonical record decoding or store
mutation. Streamable HTTP additionally applies that ceiling at the transport. Stdio
framing remains owned by the MCP SDK, but oversized decoded envelopes fail before they
reach libRSI state.

Loopback Streamable HTTP may be used without auth for disposable local composition.
Non-loopback binding requires all of `LIBRSI_MCP_TOKEN`, `--auth-issuer-url`, and
`--auth-resource-url`; partial configuration is rejected. The server uses stateless
Streamable HTTP, so protocol sessions do not become libRSI run state.

## Operational boundary

- Use disposable local stores and loopback binding for development.
- Put TLS, rate limiting, identity federation, audit retention, deployment, and public
  ingress in the owning host or gateway; they are not provided by libRSI.
- Configure the smallest capability set and explicit postures per admission.
- Never treat a successful provider call as evidence, candidate acceptance, or target
  mutation. Canonical workflow policy derives those meanings from typed results.
- Close the service or use its context manager so SQLite resources shut down cleanly.
