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
| `in-review` | Intended implementation is complete enough for review/integration, but acceptance is not yet established. |
| `implemented` | Intended implementation is present, but full Block acceptance or maintained verification is pending. |
| `verified` | All maintained Block acceptance criteria are satisfied by current implementation and retained verification evidence. |
| `deferred` | Work is intentionally postponed despite otherwise being in scope. |
| `superseded` | The Block or implementation path was replaced by a later maintained design/Block. |

`implemented` and `verified` are deliberately distinct. A commit, PR, passing local test, or merge is not by itself proof that a Block's complete acceptance contract is satisfied.

## Accounting rules

For every status change beyond `not-started`, retain enough exact evidence to reconstruct the claim:

- owner/workstream;
- branch and PR where applicable;
- exact material implementation commit SHA(s);
- exact verification evidence such as CI run, maintained test/dogfood, or report;
- last-updated date;
- remaining work or blocker when not `verified`.

Detailed records are required for active, blocked, implemented, or verified Blocks. Empty per-Block boilerplate is intentionally omitted for `not-started` Blocks; the summary table is authoritative for their status.

A Block may only be marked `verified` after its maintained acceptance criteria have been checked against the current implementation. If an implementation is later invalidated, retain the historical evidence in the update log and move the Block to the appropriate new status.

## Program summary

| Block | Short name | Status | Owner / workstream | Branch / PR | Last updated |
|---:|---|---|---|---|---|
| 0 | Architecture contract / namespace plan / legacy baseline | `verified` | Architecture / integration | `feat/block-0-architecture-baseline` / PR #1 | 2026-08-21 |
| 1 | Canonical immutable records / identity | `ready` | — | — | 2026-08-21 |
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
**Branch:** `feat/block-0-architecture-baseline`  
**PR:** #1, `Block 0: architecture contract and 0.2 compatibility baseline`  
**Last updated:** 2026-08-21

### Material implementation

Planning/design records inherited from the implementation-program branch:

- `38a9398b47f5e9f8558baff95dac096b3ba0bb45` — architecture expansion implementation tracker.
- `e6a5fb72a3c84f53d0d3e1b0888440515ab28214` — parallel implementation/dependency plan.

Block 0 implementation commits:

- `d7dbe255952119c517753bcaea17a11dcd45b42b` — maintained architecture and namespace ownership contract.
- `ee383123740bce1180629315f6b9284e137c9d83` — rooted libRSI `0.2.0` compatibility fixture.
- `ce7d43ea7c73d87c411fbc81ce1a4f07ded77db6` — executable `0.2.0` public-policy compatibility regression suite.
- `f504bd9fd042b5e83a7de853a38900775c0969d1` — link maintained architecture contract from implementation-program index.
- `eec9fc1b27e095d0311668281af17af8e0abc560` — final Ruff-compatible test formatting used by the successful verification run.

### Verification evidence

- GitHub Actions CI run `32518645629` against commit `eec9fc1b27e095d0311668281af17af8e0abc560`: **success** across the maintained Python 3.11, 3.12, and 3.13 matrix.
- The CI workflow includes Ruff lint, Ruff formatting check, mypy, pytest with branch coverage, package build, and Python 3.11 wheel smoke test.
- The existing repository tests remained in the same CI invocation as the new compatibility baseline.

### Acceptance reconciliation

- Maintained architecture documentation exists: `docs/implementation/architecture-contract.md`.
- Epistemics, knowledge, targets, experiments, runtime, interventions, validation, investigation, improvement, and RSI/meta-improvement ownership are defined.
- Control-plane neutrality is explicit: externally driven, libRSI-driven, and hybrid execution share one action/result/state model.
- `Target != Knowledge != Intent` is explicit.
- Candidate implementation is distinct from authoritative application.
- Every current `0.2.0` module has an explicit future semantic owner.
- No libRSI dependency on Software Factory or another high-level consumer was introduced; the required dependency direction is documented as consumer → libRSI.
- Executable regression fixtures cover representative `0.2.0` public exports, identities, checkpoint, reflection/hypothesis/evidence, command-experiment, program, portfolio, review, selection, and selector-policy behavior.
- Full maintained CI passed.

**Remaining for Block 0:** None. Any future architecture change must be made as an explicit maintained architecture revision rather than silently redefining this completed Block.

### Update log

- **2026-08-21:** Architecture and parallelization planning documents created; Block remained `in-progress` because namespace ownership and legacy regression baseline were missing.
- **2026-08-21:** Added the maintained architecture contract and executable `0.2.0` compatibility baseline on `feat/block-0-architecture-baseline`.
- **2026-08-21:** PR #1 CI initially exposed only test import-formatting issues; corrected them without changing the baseline semantics.
- **2026-08-21:** CI run `32518645629` passed the full matrix. Block 0 marked `verified`; Block 1 becomes `ready`.

---

## Block 1 — Canonical immutable domain records and identity model

**Status:** `ready`  
**Owner / workstream:** Unassigned  
**Branch / PR:** —  
**Verification evidence:** Block 0 predecessor is `verified`.  
**Last updated:** 2026-08-21  
**Notes / remaining:** Available to begin. The architecture contract and `0.2.0` compatibility baseline are now the migration guardrails for this work.

---

# Program update log

- **2026-08-21:** Initialized the architecture-expansion implementation program and parallelization plan.
- **2026-08-21:** Added maintained Block 20A covering the libRSI service/API/server and MCP server surface.
- **2026-08-21:** Block 0 verified by PR #1 and successful CI run `32518645629`; Block 1 moved to `ready`.
