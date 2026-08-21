# libRSI Implementation Status Ledger

**Companion to:** `architecture-expansion-implementation-tracker.md` and `parallel-implementation-plan.md`  
**Baseline:** `main` at `d96cc666c7800681dfdde2f991f841b09155dfe8`  
**Purpose:** Canonical implementation accounting for the architecture-expansion program.

This document is the mutable execution ledger for the implementation program. The architecture tracker defines **what must be built and accepted**; this file records **what is actually underway, implemented, reviewed, and verified**, with exact repository references.

## Status model

Use exactly one primary status per Block:

| Status | Meaning |
|---|---|
| `not-started` | No implementation work has been claimed for the Block. |
| `ready` | Dependencies/contracts required to begin are satisfied and the Block is available to take. |
| `in-progress` | Implementation is actively underway but the Block has not met all acceptance criteria. |
| `blocked` | Work started or was ready, but a concrete dependency/decision prevents progress. |
| `in-review` | Intended implementation is complete enough for review/integration, but acceptance is not yet established. |
| `implemented` | The intended implementation is merged/present, but full Block acceptance or maintained verification is still pending. |
| `verified` | All Block acceptance criteria are satisfied by current code and retained verification evidence. |
| `deferred` | Work is intentionally postponed despite otherwise being in scope. |
| `superseded` | The Block or its original implementation path was replaced by a later maintained design/Block. |

`implemented` and `verified` are deliberately distinct. A commit, passing local test, or completed PR does not by itself establish that the Block's full acceptance contract is satisfied.

## Accounting rules

For every status change beyond `not-started`, update the corresponding Block record below with enough exact evidence to reconstruct the claim:

- **Owner / workstream:** person, agent, worktree, or named stream currently responsible.
- **Branch / PR:** active branch and PR number/link when applicable.
- **Implementation commits:** exact commit SHA(s) that materially implement the Block; do not cite a broad branch head as a substitute when narrower commits are known.
- **Verification evidence:** exact test/dogfood/report/commit references establishing acceptance. For `verified`, this field must be nonempty.
- **Last updated:** ISO date (`YYYY-MM-DD`); add time when same-day ordering matters.
- **Notes / remaining:** current scope, partial completion, blocker, follow-up, or why acceptance is not yet established.

When a Block is implemented by multiple commits, append the material commits rather than replacing history with only the newest SHA. If a prior implementation is reverted or superseded, retain that history in the Block's update log and identify the authoritative replacement.

A Block may only be marked `verified` when its acceptance criteria in `architecture-expansion-implementation-tracker.md` or its maintained extension Block document have been checked against the current authoritative code/state. Process evidence alone is insufficient.

## Program summary

| Block | Short name | Status | Owner / workstream | Branch / PR | Last updated |
|---:|---|---|---|---|---|
| 0 | Architecture contract / legacy baseline | `in-progress` | Architecture / integration | `docs/implementation-trackers` | 2026-08-21 |
| 1 | Canonical immutable records / identity | `not-started` | — | — | — |
| 2 | Hypothesis / experiment integrity repair | `not-started` | — | — | — |
| 3 | General epistemic model | `not-started` | — | — | — |
| 4 | Generic experiments / metrics / evaluation | `not-started` | — | — | — |
| 5 | Target / snapshot / currentness model | `not-started` | — | — | — |
| 6 | Persistent knowledge / KnowledgeStore | `not-started` | — | — | — |
| 7 | Durable Run / Event / State / Action engine | `not-started` | — | — | — |
| 8 | Capability protocols / neutral dispatch | `not-started` | — | — | — |
| 9 | Reasoner contract / structured reasoning | `not-started` | — | — | — |
| 10 | Validation workflow | `not-started` | — | — | — |
| 11 | Investigation workflow | `not-started` | — | — | — |
| 12 | Intervention / candidate lifecycle | `not-started` | — | — | — |
| 13 | Goals / objectives / constraints / baselines | `not-started` | — | — | — |
| 14 | Comparative evaluation / selection | `not-started` | — | — | — |
| 15 | Complete improvement workflow | `not-started` | — | — | — |
| 16 | Apply / verify / rollback | `not-started` | — | — | — |
| 17 | RSI / meta-targeting / self-change governance | `not-started` | — | — | — |
| 18 | Batteries-included local runtime / Python API | `not-started` | — | — | — |
| 19 | Outcome API / serialization / events | `not-started` | — | — | — |
| 20 | CLI / external-agent protocol | `not-started` | — | — | — |
| 20A | Server / service API / MCP server | `not-started` | — | — | 2026-08-21 |
| 21 | Provider / reasoner integrations | `not-started` | — | — | — |
| 22 | Software target support / Software Factory consumer | `not-started` | — | — | — |
| 23 | End-to-end dogfoods | `not-started` | — | — | — |
| 24 | Cross-domain agnosticism proof | `not-started` | — | — | — |
| 25 | Public API / docs / packaging / release gate | `not-started` | — | — | — |

---

# Block records

## Block 0 — Architecture contract, namespace plan, and legacy baseline

**Status:** `in-progress`  
**Owner / workstream:** Architecture / integration  
**Branch / PR:** `docs/implementation-trackers`  
**Implementation commits:**

- `38a9398b47f5e9f8558baff95dac096b3ba0bb45` — add architecture expansion implementation tracker.
- `e6a5fb72a3c84f53d0d3e1b0888440515ab28214` — add parallel implementation/dependency plan.

**Verification evidence:** Not yet sufficient for Block acceptance.  
**Last updated:** 2026-08-21  
**Notes / remaining:** The architecture and parallelization design records now exist. Block 0 remains `in-progress` because its complete acceptance contract also requires the maintained namespace/ownership contract and regression/legacy baseline to be established and checked before architecture work is considered closed.

### Update log

- **2026-08-21:** Initialized program accounting. Recorded the two implementation-planning documentation commits; did not claim full Block 0 acceptance.

---

## Block 1 — Canonical immutable domain records and identity model

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 2 — Repair current hypothesis and experiment referential integrity

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 3 — General epistemic model and pluggable belief/evidence aggregation

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 4 — Generic experiment, measurement, metric, and evaluation subsystem

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 5 — Target, target snapshot, multi-component target, and currentness model

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 6 — Persistent knowledge model and `KnowledgeStore`

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 7 — Durable Run / Event / State / Action engine

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 8 — Capability protocols and control-plane-neutral dispatch

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 9 — Reasoner contract and structured reasoning work

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 10 — First-class validation workflow

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 11 — Investigation / scientific-understanding workflow

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 12 — Generic intervention and candidate lifecycle

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 13 — Goals, objectives, constraints, guardrails, and operationalization

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 14 — Comparative evaluation, actual candidate selection, and search policy

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 15 — Complete improvement workflow

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 16 — Application, authoritative target transition, verification, and rollback

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 17 — Generalized RSI/meta-targeting and self-change governance

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 18 — Batteries-included local runtime and high-level Python façade

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 19 — Structured Outcome API, serialization, event stream, and external consumption

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 20 — CLI and external-agent/Codex protocol

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 20A — libRSI Server, Service API, and MCP Server

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** 2026-08-21  
**Notes / remaining:** Full implementation and acceptance contract is maintained in `server-mcp-implementation-block.md`. The server must remain a transport/interface layer over the canonical libRSI runtime rather than introducing a separate workflow, state, evidence, or persistence model.

### Update log

- **2026-08-21:** Added Block 20A to cover a transport-independent libRSI service, HTTP/JSON server, local/remote MCP server, explicit durable run handles, capability/authority reporting, concurrency/restart behavior, and basic service/MCP dogfoods. Status initialized as `not-started`.

---

## Block 21 — Provider integrations, beginning with a reasoner adapter

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 22 — Software target reference support and Software Factory consumer integration

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 23 — End-to-end validation, investigation, and improvement dogfoods

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 24 — Cross-domain agnosticism proof

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

## Block 25 — Public API cleanup, documentation, packaging, migration, and release gate

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Implementation commits:** —  
**Verification evidence:** —  
**Last updated:** —  
**Notes / remaining:** —

---

# Program update log

Use this section only for program-level events that affect multiple Blocks, dependency interpretation, or the authoritative execution plan. Block-local progress belongs in the relevant Block record.

- **2026-08-21:** Initialized implementation accounting on `docs/implementation-trackers`. Block 0 marked `in-progress` based only on the architecture and parallel implementation documentation; no code Block is claimed implemented or verified.
- **2026-08-21:** Added Block 20A as a maintained program extension covering the libRSI server/service/API/MCP surface. It is tracked in this ledger and specified in `server-mcp-implementation-block.md`.