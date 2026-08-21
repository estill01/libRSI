# Block 20A — libRSI Server, Service API, and MCP Server

**Program:** libRSI Architecture Expansion  
**Companion to:** `architecture-expansion-implementation-tracker.md`, `parallel-implementation-plan.md`, and `implementation-status.md`  
**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** 2026-08-21

## Outcome

Make libRSI available as a long-running local or remote service, including a maintained Model Context Protocol (MCP) server, without creating a second libRSI execution model.

The server is an interface/deployment layer over the same canonical runtime used by the Python API and CLI:

```text
                         canonical libRSI runtime
                 Run / State / Action / Result / Outcome
                                   │
                 ┌─────────────────┼─────────────────┐
                 │                 │                 │
              Python             CLI             Service
                                                     │
                                        ┌────────────┴────────────┐
                                        │                         │
                                   HTTP / JSON                   MCP
```

Embedded Python, external-host stepping, managed execution, CLI, HTTP, and MCP must not have separate workflow semantics, state machines, or evidence models.

## Depends on

**Hard contracts:**

- Block 7 — durable `Run / Event / State / Action` engine;
- Block 8 — capability protocols and control-plane-neutral dispatch;
- Block 19 — canonical `Outcome` and serialization contracts.

**Integration dependencies:**

- Block 10 for validation operations;
- Block 11 for investigation operations;
- Block 15 for improvement operations;
- Block 16 for application/verification operations where exposed;
- Block 17 for explicitly authorized RSI/meta-improvement operations;
- Block 20 for shared external-agent schemas where the CLI and service expose equivalent operations.

The service framework, run/status endpoints, and MCP transport can begin once Blocks 7, 8, and the relevant portion of Block 19 are interface-stable; it does not need to wait for every workflow to be complete.

---

## 1. Generic libRSI service layer

Introduce a transport-independent service/facade, conceptually:

```python
class LibRSIService:
    def start(...): ...
    def validate(...): ...
    def investigate(...): ...
    def improve(...): ...

    def get_run(...): ...
    def get_status(...): ...
    def next_actions(...): ...
    def submit_result(...): ...
    def get_outcome(...): ...

    def query_knowledge(...): ...
```

The exact method names may differ, but the service must delegate into the canonical libRSI runtime and stores rather than reimplementing orchestration.

The same service methods should back HTTP and MCP where practical.

### Required basic operations

At minimum expose service operations for:

```text
start validation
start investigation
start improvement

get run
get status
list/poll outstanding actions
submit action result
pause/cancel where supported
resume
get outcome

query relevant knowledge/evidence
inspect server/runtime capabilities
```

Operations that are not yet implemented by the underlying runtime must report capability absence explicitly rather than simulate support at the service layer.

---

## 2. Explicit run handles

Remote/service execution must use explicit libRSI run IDs/handles.

For example:

```text
start improvement
    ↓
run_id = rsi-123
    ↓
status(rsi-123)
next(rsi-123)
submit(rsi-123, result)
outcome(rsi-123)
```

Protocol/session state must not become the authoritative location of libRSI workflow state.

This makes service requests restartable, horizontally routable, and compatible with external agents that reconnect between actions.

---

## 3. HTTP/JSON server

Provide a basic maintained remote service interface over the canonical service layer.

The exact HTTP framework is an implementation decision, but the API should expose versioned structured schemas rather than prose-driven endpoints.

A reasonable conceptual surface is:

```text
POST /v1/runs/validation
POST /v1/runs/investigation
POST /v1/runs/improvement

GET  /v1/runs/{run_id}
GET  /v1/runs/{run_id}/status
GET  /v1/runs/{run_id}/actions
POST /v1/runs/{run_id}/results
GET  /v1/runs/{run_id}/outcome

POST /v1/knowledge/query
GET  /v1/capabilities
GET  /health
```

Exact endpoint structure may change when the runtime schemas stabilize.

### Requirements

- structured versioned request/response schemas;
- deterministic mapping to canonical Python records;
- explicit run IDs;
- idempotent/replay-safe result submission where the runtime supports it;
- stale action/result rejection;
- bounded request sizes;
- structured errors;
- health/readiness endpoints;
- graceful shutdown without losing durable run state;
- multiple concurrent runs;
- optional target/project namespace isolation.

---

## 4. MCP server

Ship a maintained libRSI MCP server as an optional service/integration surface.

The MCP server must be a projection over `LibRSIService`, not another controller.

### Initial MCP tools

A basic tool set should map closely to the canonical run API, approximately:

```text
librsi_validate
librsi_investigate
librsi_improve

librsi_run_status
librsi_run_next
librsi_run_submit
librsi_run_resume
librsi_run_outcome

librsi_knowledge_query
librsi_capabilities
```

Names may be refined, but MCP operations should not invent semantics absent from the normal service/Python APIs.

Long-running operations should normally return an explicit libRSI run handle rather than holding one tool invocation open for the complete RSI workflow.

### MCP resources

Where useful, expose read-only canonical state as MCP resources, for example:

```text
librsi://runs/{run_id}
librsi://runs/{run_id}/outcome
librsi://runs/{run_id}/evidence
librsi://knowledge/claims/{claim_id}
librsi://knowledge/evidence/{evidence_id}
```

Resources are projections of authoritative stores; they do not become a second source of truth.

### MCP transports

Support the useful deployment modes available in the maintained MCP SDK/spec at implementation time. The intended initial modes are:

- **stdio** for local process-spawned integrations;
- **Streamable HTTP** for remote/network service use.

Do not build the libRSI application state around transport-level sessions. Persistent run state belongs to libRSI and is addressed through explicit run IDs.

---

## 5. Server-side capability model

The server should report the capabilities actually configured in that process.

For example, one deployment may expose only:

```text
validation
investigation
external action stepping
knowledge queries
```

while another may also have:

```text
managed reasoner
experiment execution
implementer
applier
verifier
RSI self-change governance
```

Remote callers must be able to inspect this rather than infer it from failures.

The server must preserve the same `automatic / external / human-reserved / unavailable` capability distinctions defined by Block 8.

---

## 6. Security and authority boundaries

Keep the first implementation basic, but establish the correct authority model from the beginning.

Requirements:

- local-only deployment can default to an explicitly local binding/configuration;
- remote deployment must support an authentication/authorization boundary appropriate to the chosen transport/framework;
- read-only knowledge/run inspection must be distinguishable from mutating/result-submission/application authority;
- MCP or HTTP availability must never imply authority to apply an intervention;
- target-specific credentials remain outside canonical epistemic records;
- secrets must not be emitted through outcomes, evidence projections, logs, MCP resources, or error responses;
- server configuration determines which capabilities may execute automatically.

Fine-grained multi-tenant authorization can be expanded later, but the first server must not conflate network access with unrestricted RSI authority.

---

## 7. Concurrency and durability

The server must be able to host more than one durable run.

At minimum:

- concurrent independent run IDs;
- process restart followed by run recovery from the normal libRSI runtime store;
- no hidden in-memory session state required for correctness;
- safe duplicate/retried requests;
- action/result correlation by exact IDs;
- cancellation/pause semantics delegated to the runtime rather than fabricated by the transport.

Horizontal scaling is not required for the first implementation, but the service boundary should not preclude it.

---

## 8. Observability

Provide basic operational visibility distinct from epistemic evidence.

At minimum:

```text
health/readiness
structured request errors
run/action IDs in logs
request/run correlation
basic runtime metrics hooks
```

Operational telemetry must not automatically become scientific evidence or claim support.

---

## 9. Packaging and execution

The server should be installable without forcing server/MCP dependencies on minimal embedded users.

A likely packaging shape is conceptually:

```text
pip install librsi
pip install "librsi[server]"
pip install "librsi[mcp]"
```

or one combined service extra if that proves simpler.

Provide maintained executable entrypoints, conceptually:

```text
librsi server
librsi mcp
```

Exact packaging/CLI names are deferred to implementation.

---

## 10. Tests / dogfoods

Maintain at least:

### A. Python ↔ HTTP semantic equivalence

Start or inspect the same logical workflow through the Python/service API and HTTP projection and verify equivalent canonical records/outcomes.

### B. MCP local stdio smoke test

Spawn the MCP server, list the expected tools, create/inspect a run, and obtain a canonical result.

### C. MCP remote transport smoke test

Exercise the maintained remote MCP transport against a disposable server.

### D. Restart/resume

Start a run through the service, terminate the server process, restart it, and successfully continue the same explicit run ID.

### E. Stale/duplicate result handling

Verify duplicate or stale submissions cannot advance a run twice.

### F. Capability/authority boundary

Verify a server lacking an `Applier` can return an accepted intervention but cannot silently apply it.

---

## Acceptance

Block 20A may be marked `verified` only when:

- one canonical `LibRSIService` or equivalent transport-independent service facade exists;
- a maintained HTTP/JSON server exposes basic durable run lifecycle operations;
- a maintained MCP server exposes libRSI through MCP without a second workflow/state model;
- local stdio MCP operation works;
- remote MCP operation works through the maintained modern transport at implementation time;
- explicit run handles survive service restart;
- HTTP, MCP, CLI/external-agent, and Python execution use the same canonical runtime records and outcomes;
- configured capabilities/authority are inspectable and enforced;
- stale/duplicate result submission fails safely;
- server unavailability/restart does not corrupt durable libRSI state;
- maintained integration tests cover the basic service and MCP paths.

---

## Parallelization placement

Treat this as **Block 20A**, a sibling of Block 20 rather than a successor to all product work.

Recommended schedule:

```text
Freeze C:
Run / Action / ActionResult / Capability
             │
             ├──────── CLI / external-agent work (Block 20)
             │
             └──────── service facade + server skeleton (Block 20A)
                                   │
                         Outcome schema stabilizes
                                   │
                         HTTP + MCP projections
```

The service framework and run/status/action interfaces can therefore proceed in parallel with later investigation/improvement features; each workflow is exposed as its canonical API becomes available.

---

## Update log

- **2026-08-21:** Added Block 20A after architecture review identified that the program covered CLI/external-agent integration but did not explicitly cover a libRSI server or MCP server. Initialized status as `not-started`.