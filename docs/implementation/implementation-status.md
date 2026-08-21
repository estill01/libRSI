# libRSI Implementation Status Ledger

**Companion to:** `architecture-expansion-implementation-tracker.md`, `parallel-implementation-plan.md`, `architecture-contract.md`, and maintained extension Block documents  
**Baseline:** `main` at `d96cc666c7800681dfdde2f991f841b09155dfe8`  
**Purpose:** Canonical implementation accounting for the architecture-expansion program.

The architecture tracker and extension Block documents define **what must be built and accepted**. This file records **what is actually ready, underway, implemented, and verified**, with exact repository references.

## Status model

| Status | Meaning |
|---|---|
| `not-started` | No implementation work has been claimed for the Block. |
| `ready` | Required predecessor contracts are satisfied and the Block is available to take. |
| `in-progress` | Implementation is actively underway but the Block has not met all acceptance criteria. |
| `blocked` | A concrete dependency or decision prevents progress. |
| `in-review` | Intended implementation is complete enough for review/integration, but acceptance is not yet established on the authoritative branch. |
| `implemented` | Intended implementation is present on the authoritative branch, but full Block acceptance or maintained verification is pending. |
| `verified` | All maintained Block acceptance criteria are satisfied by the authoritative implementation and retained verification evidence. |
| `deferred` | Work is intentionally postponed despite otherwise being in scope. |
| `superseded` | The Block or implementation path was replaced by a later maintained design/Block. |

`implemented` and `verified` are deliberately distinct. A commit, PR, passing branch CI, or merge is not by itself proof that a Block's complete acceptance contract is satisfied.

## Accounting rules

For every status change beyond `not-started`, retain enough exact evidence to reconstruct the claim:

- owner/workstream;
- branch and PR where applicable;
- exact material implementation commit SHA(s);
- exact verification evidence such as CI run, maintained test/dogfood, or report;
- last-updated date;
- remaining work or blocker when not `verified`.

The summary table is authoritative for every Block's current status. Detailed records are required for `ready`, active, blocked, implemented, or verified Blocks; repetitive empty records are intentionally omitted for `not-started` Blocks.

A Block may only be marked `verified` after its maintained acceptance criteria have been checked against the authoritative implementation. If later work invalidates a prior acceptance condition, retain the historical evidence in the update log and move the Block to the appropriate current status.

## Program summary

| Block | Short name | Status | Owner / workstream | Branch / PR | Last updated |
|---:|---|---|---|---|---|
| 0 | Architecture contract / namespace plan / legacy baseline | `verified` | Architecture / integration | PR #3 | 2026-08-21 |
| 1 | Canonical immutable records / identity | `verified` | Canonical records / identity | PR #5 | 2026-08-21 |
| 2 | Hypothesis / experiment integrity repair | `ready` | — | — | 2026-08-21 |
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
| 20A | libRSI server / service API / MCP server | `not-started` | — | — | — |
| 21 | Provider / reasoner integrations | `not-started` | — | — | — |
| 22 | Software target support / Software Factory consumer | `not-started` | — | — | — |
| 23 | End-to-end dogfoods | `not-started` | — | — | — |
| 24 | Cross-domain agnosticism proof | `not-started` | — | — | — |
| 25 | Public API / docs / packaging / release gate | `not-started` | — | — | — |

---

# Detailed Block records

## Block 0 — Architecture contract, namespace plan, and legacy baseline

**Status:** `verified`  
**Owner / workstream:** Architecture / integration  
**Authoritative implementation:** `bd3815d51a326dc7f5ace8f54ce462c34e251605` on `main`  
**PR:** #3, `Block 0: architecture contract and 0.2 compatibility baseline`  
**Last updated:** 2026-08-21

### Material implementation

- `2c056ca9a62c1daaaeb401c0ffdcbc2b02be937b` — squash-merge the internal architecture-expansion implementation program and accounting documents onto `main`.
- `bd3815d51a326dc7f5ace8f54ce462c34e251605` — squash-merge the maintained architecture contract and executable `0.2.0` compatibility baseline from PR #3 onto `main`.

### Verification evidence

- PR #3 GitHub Actions CI run `32520018410`: **success** against the exact current-`main` merge base used for integration, across Python 3.11, 3.12, and 3.13.
- The maintained CI workflow covers Ruff lint, Ruff formatting, mypy, pytest with branch coverage, package build, and Python 3.11 wheel smoke testing.
- The compatibility suite runs together with the pre-existing repository tests.
- `tests/test_v020_compatibility_contract.py` requires every legacy `0.2.0` public export to remain available/public while permitting additive future APIs.
- Rooted fixtures pin representative `0.2.0` identities and policy behavior without freezing later package-version evolution.

### Acceptance reconciliation

- Maintained architecture documentation exists at `docs/implementation/architecture-contract.md`.
- Epistemics, knowledge, targets, experiments, runtime, interventions, validation, investigation, improvement, and RSI/meta-improvement ownership are defined.
- Control-plane neutrality is explicit: externally driven, libRSI-driven, and hybrid execution share one action/result/state model.
- `Target != Knowledge != Intent` is explicit.
- Candidate implementation is distinct from authoritative application.
- Every current `0.2.0` module has an explicit future semantic owner.
- No libRSI dependency on Software Factory or another high-level consumer was introduced; the required direction is consumer → libRSI.
- The `0.2.0` public-policy regression baseline is executable and passing.
- The pre-existing test suite remains passing in the same CI invocation.

**Remaining for Block 0:** None. Future architectural changes must be explicit maintained revisions rather than silent redefinition of this completed Block.

### Update log

- **2026-08-21:** Architecture and parallelization planning documents created; Block remained `in-progress` because namespace ownership and a legacy regression baseline were missing.
- **2026-08-21:** Added a maintained architecture contract and executable `0.2.0` compatibility baseline on a feature branch.
- **2026-08-21:** Review found and corrected two issues before merge: premature `verified` accounting and an over-strict export/version freeze that would have obstructed additive future APIs.
- **2026-08-21:** The original stacked PR #1 was closed after the documentation base was squash-merged; clean PR #3 was rebuilt directly from current `main` to avoid duplicated history.
- **2026-08-21:** PR #3 CI run `32520018410` passed and PR #3 was squash-merged as `bd3815d51a326dc7f5ace8f54ce462c34e251605`. Block 0 is `verified` on the authoritative implementation.

---

## Block 1 — Canonical immutable domain records and identity model

**Status:** `verified`  
**Owner / workstream:** Canonical records / identity  
**Authoritative implementation:** `1528c7ecc5eec0e44136ceb8b54e3fa09bb5bf74` on `main`  
**PR:** #5, `Block 1: canonical immutable domain records and identity model`  
**Last updated:** 2026-08-21

### Material implementation

- `1528c7ecc5eec0e44136ceb8b54e3fa09bb5bf74` — squash-merge the complete Block 1 canonical record/identity substrate from PR #5 onto `main`.

### Verification evidence

- PR #5 GitHub Actions CI run `32525534734`: **success** across Python 3.11, 3.12, and 3.13 after the final performance/robustness review.
- The maintained CI workflow passed Ruff lint/formatting, mypy, pytest with branch coverage, package build, and Python 3.11 wheel smoke testing.
- `tests/test_canonical_records.py` exercises a complete target → epistemic → experiment → evidence/evaluation → intervention/candidate → outcome object graph and round-trips every record deterministically.
- Tests cover deep immutability, detachment from mutable inputs, identity stability under mapping order changes, exclusion of presentation metadata from roots, root changes for identity-bearing changes, exact reference mismatch failures, tamper detection, malformed schema/version/root rejection, non-finite/unsupported canonical values, and serialization-marker collision resistance.
- The pre-existing `0.2.0` compatibility suite remained passing, so Block 1 is additive rather than a silent legacy break.

### Acceptance reconciliation

- Complete immutable records are provided for `TargetRef`, `TargetSnapshot`, `Claim`, `Question`, `Goal`, `Constraint`, `Hypothesis`, `Evidence`, `EvidenceRef`, `ExperimentSpec`, `Trial`, `Observation`, `Measurement`, `Evaluation`, `Intervention`, `Candidate`, `Outcome`, and `ArtifactRef`, with common `SemanticRecord` and exact `RecordRef` infrastructure.
- All semantically material record fields are retained in the records; identity is a stable SHA-256 root over deterministic canonical identity data.
- Every record carries exact lineage as typed content-addressed references.
- Durable serialization carries an explicit record schema and per-record schema version and integrity-checks the stored root during reconstruction.
- Presentation metadata is preserved in serialization but explicitly excluded from semantic identity; nested record identity depends on exact record references rather than presentation metadata.
- Deep immutable `FrozenMap` values canonicalize mapping order, reject ambiguous/non-JSON-shaped values, and provide immutable O(1) lookup while retaining deterministic ordering/hashing.
- User data mappings are wrapped during durable serialization so values that resemble libRSI record/reference schema envelopes cannot be misinterpreted during deserialization.
- Exact references bind both record type and root and fail closed when required against a different semantic object.
- All Block 1 records reconstruct from their durable serialized representation without an external synchronized dictionary, and deterministic reserialization reproduces the same bytes/root.
- Existing hypothesis/experiment policies were deliberately not migrated to these records; that referential-integrity migration remains Block 2 as planned.

**Remaining for Block 1:** None. Block 2 may now migrate the current policy APIs onto these canonical records while preserving the Block 0 compatibility baseline.

### Update log

- **2026-08-21:** Implemented the canonical record substrate and public additive exports on `feat/block-1-canonical-records`.
- **2026-08-21:** CI first exposed formatting-only issues; those were corrected without weakening the configured quality gates.
- **2026-08-21:** Second-pass review hardened generic reference validation and wrapped user mappings to prevent collisions with libRSI serialization markers.
- **2026-08-21:** Semantic round-trip testing exposed an `EvidenceRef` convenience-subclass reconstruction mismatch; deserialization was corrected to preserve generic `RecordRef` semantics and let typed containers promote references contextually.
- **2026-08-21:** Final review optimized `FrozenMap` lookup from linear to immutable O(1) indexing without changing identity/hash semantics.
- **2026-08-21:** Final PR #5 CI run `32525534734` passed and PR #5 was squash-merged as `1528c7ecc5eec0e44136ceb8b54e3fa09bb5bf74`. Block 1 is `verified` on the authoritative implementation.

---

## Block 2 — Repair current hypothesis and experiment referential integrity

**Status:** `ready`  
**Owner / workstream:** Unassigned  
**Branch / PR:** —  
**Verification evidence:** Block 1 predecessor is `verified` on `main`.  
**Last updated:** 2026-08-21  
**Notes / remaining:** Available to begin. Block 2 should migrate the existing hypothesis and experiment policy APIs onto the canonical records without collapsing the broader Block 3 epistemic-policy work into this migration.

---

## Block 20A — libRSI Server, Service API, and MCP Server

**Status:** `not-started`  
**Owner / workstream:** —  
**Branch / PR:** —  
**Verification evidence:** —  
**Last updated:** 2026-08-21  
**Notes / remaining:** Full implementation and acceptance contract is maintained in `server-mcp-implementation-block.md`. The server must remain a transport/interface layer over the canonical libRSI runtime rather than introducing a separate workflow, state, evidence, or persistence model.

### Update log

- **2026-08-21:** Added Block 20A covering a transport-independent libRSI service, HTTP/JSON server, local/remote MCP server, explicit durable run handles, capability/authority reporting, concurrency/restart behavior, and service/MCP dogfoods.

---

# Program update log

- **2026-08-21:** Initialized the architecture-expansion implementation program and parallelization plan.
- **2026-08-21:** Added maintained Block 20A covering the libRSI service/API/server and MCP server surface.
- **2026-08-21:** Squash-merged the internal implementation program to `main` as `2c056ca9a62c1daaaeb401c0ffdcbc2b02be937b`.
- **2026-08-21:** Reviewed, hardened, CI-verified, and squash-merged Block 0 to `main` as `bd3815d51a326dc7f5ace8f54ce462c34e251605`; Block 1 moved to `ready`.
- **2026-08-21:** Implemented, twice reviewed, hardened, CI-verified, and squash-merged Block 1 to `main` as `1528c7ecc5eec0e44136ceb8b54e3fa09bb5bf74`; Block 2 moved to `ready`.
