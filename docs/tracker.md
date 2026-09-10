# libRSI Failure-Informed Proposal Learning Implementation Tracker

- Tracker status: `planning`
- Tracker sequence: Blocks 0–2
- Program identity: `proposal-learning`; qualify references as `proposal-learning/Block N`.
- Repository: `https://github.com/estill01/libRSI`
- Baseline: `4f06a6ced8898ca3d75182172d40070d963bc125` on main.
- Governing objective: the September 10 direct user request in task `01a088ad-fde7-7941-9f42-6427f5f0b269` to retain and learn from unsuccessful proposal operations, experiment with improving proposal generation itself, and provide that capability generally in libRSI rather than only in Graphy.
- Canonical owner: `docs/tracker.md`; sole current queue `proposal-learning/Blocks 0–2`; first eligible Block 0 after authoring review.
- Direct range: all three Blocks through installed standalone use, scoped upstream publication and main integration. Internal Stops are not final-return authority.

## 1. Purpose and intended outcome

An ordinary libRSI consumer can inspect what a learning attempt proposed and measured,
why it ended without adoption, and what was actually spent. A bounded later attempt
uses that exact history, may request reflection, and tries an evidence-informed
revision. The change target can itself be a proposal generator: revised generator
settings must earn acceptance from measured usefulness of their downstream proposals.

Completion means a standalone installed example actually rejects an initial revision,
uses its retained observations to formulate a different approach, measures a better
proposal generator on fresh held-out cases, adopts it through existing native owners,
reopens storage and uses the adopted generator on a new ordinary input. This is a
framework demonstration with deterministic, input-driven reasoning, not a claim that
LLM quality or an external consumer workload has improved.

### Mission frame

- Primary outcome: reusable failure-informed proposal learning and measured improvement of proposal generation in libRSI.
- Observable completion: exact native rejected and accepted results, retained operation/feedback records, public source and tests, installed-wheel restart and a later generated proposal produced by the adopted generator revision.
- Ordinary effect classes needed: isolated library/docs/example/test edits, local Python environments and offline experiments, scoped commits/pushes, PR and authorized main integration; no consumer rollout is needed.
- Hard direct authority or safety boundaries: existing evidence/evaluation/application owners and user instruction to preserve ongoing Graphy/Patent work; preserve their exact installed libRSI pin and private environments. No paid provider calls, production activation, new service, model-weight training or release tag.
- Material goal alteration or reversal: moving learning semantics into Graphy, substituting a canned acceptance, ending at a history dashboard, or changing fixed acceptance rules instead of improving proposals would change the goal.

### Target-product capability frame

- Applicability: `consequential`.
- Applicability rationale: changes reusable adaptive proposal context, follow-up behavior and operation records while retaining native acceptance and effect boundaries.
- Direct product sources: direct user messages in this task; baseline `docs/adaptive-operation.md`, `docs/consumer-integration.md`, `src/librsi/facade/learning.py`, `src/librsi/improvement/policy.py`, `src/librsi/rsi/records.py`, and `AGENTS.md`.
- Product thesis and intended effect: any embedded consumer can turn unsuccessful attempts into useful future experiments and evaluate revisions of its own proposal generator.
- Protected capabilities: no mandatory dependencies, host-neutral records/storage ports, exact identities, bounded work, old-pass replay, held-out separation, explicit activation and native rollback/currentness.
- Architecture strategy: compose existing LearningStore/RuntimeStore, Observation, ReasoningRequest/Result, Investigation/Improvement/RSI workflows; expose derived history and freeze its safe projection into new pass inputs.
- Requested capability: retained attempt inspection, bounded failure-informed follow-up, optional reflection, and a usable proposal-generator self-change example.
- Proportionality: implement generic behavior in existing facade owners and supply one standalone consumer adapter; no graph dependency, separate telemetry database or automatic scheduler.
- Tradeoffs: additional bounded history validation and optional reasoning calls cost time; fail-closed replay and held-out isolation take precedence over convenience. Host execution costs have declared partial scopes.
- Uncertainty: no paid model budget or production scoring corpus is supplied; actual offline outcomes demonstrate the mechanism, not general provider/model superiority.

## 2. Target architecture and authority boundaries

`Completed native attempt → exact operation-history view → allowlisted historical
training feedback → optional reflection → new hypothesis proposal → existing trials,
selection and governance → explicitly authorized adoption → later ordinary use`.

The history view is derived from canonical records; it grants no acceptance or
activation. The proposer-safe projection excludes full terminal trees, held-out
inputs/outputs, free-form review/failure text and automatic causal-truth claims.
New pass inputs freeze selected history, ordering, policy and provider identities.
Legacy pass inputs reconstruct their original requests unchanged. The host still
owns scoring, actual effects, storage implementation and scheduling/fenced profile
ownership. A bounded explicit follow-up may reuse a failed pass's training batch;
it must name its predecessor, preserve baseline/scoring identity and use fresh
held-out cases. Defaults retain fresh-feedback scheduling and one proposal call.

## 3. Existing owners to reuse

| Concern | Existing owner | Treatment |
|---|---|---|
| Durable inputs/completed work | `LearningStore`, `RuntimeStore`, `local/learning.py` | Reuse public ports; add no parallel store or workflow authority. |
| Operation/feedback records | `Observation`, native Action/ActionResult/Outcome and learning measurements | Derive history; record scoped durations for new learning-pass host calls. |
| Proposal and reflection | `reasoning/` and `facade/learning.py` | Compose existing typed request/result semantics and durable actions. |
| Evidence and acceptance | InvestigationWorkflow, ComparativeSelectionPolicy, ImprovementWorkflow, RSIWorkflow | Reuse unchanged acceptance/rollback authority. |
| Proposal-generator target | LearningAdapter and versioned TargetSnapshot | Use the same strategy mechanism; host adapter measures actual downstream proposal usefulness. |

## 4. Prior-work and source-adaptation map

| Source or predecessor | Exact revision/hash | Disposition | Owning Block | Remaining work |
|---|---|---|---:|---|
| Accepted adaptive-operation Blocks 0–2 | `docs/implementation/adaptive-operation-20260906.md`, SHA-256 `7fa50f0f76b7bc9299098d0bb4b51fc844ae1803759bca7e45a9125ea2a5cd73` | Preserve byte-for-byte historical acceptance; no Block renumbering | 0 | Extend the maintained facade without changing prior receipts. |
| Native comparison/investigation/self-change contracts | baseline `4f06a6ced8898ca3d75182172d40070d963bc125` | Reuse | 0 | Provide the missing feedback composition. |
| Completed Graphy pilot | Graphy main `03e2233b270ecccf98521962a6acee1b113225d0` | Design motivation only | 2 | No source/evidence import or new consumer requirement. |

All older implementation documents remain historical/noncompeting as classified in
the preserved predecessor and `docs/implementation/README.md`. The completed old
three-Block program is replaced only as the current queue by this new three-Block
program; no accepted Block identity or result is altered. No required successor
queue is omitted.

## 5. Scope, non-goals, and proportionality

In scope: bounded history, safe previous-attempt context, explicitly bounded follow-up
on consumed training data, optional single reflection call, learning-pass operation
telemetry, and actual standalone improvement of a configured proposal generator.

Out of scope: ordinary task-exception persistence (its existing exception contract
remains), automatic background scheduling, unbounded retries, model-weight training,
full provider/child-process CPU billing, distributed storage, consumer deployment,
new transport, replacement evaluation/governance or a release/tag. Successful task
feedback and native learning-pass failure records remain available. Unknown costs
are unknown, not zero. No change to existing Graphy or Patent Studio pins.

## 6. Block execution contract

1. Execute the full range 0–2 in order. Authoring acceptance, reviews, commits and handoffs are internal checkpoints; continue to the actual terminal outcome.
2. Mark each table/header in progress before its implementation. Preserve old accepted tracker bytes, earlier evidence and other worktrees.
3. Use one existing reviewer for bounded authoring and exact-candidate source/outcome review; no supervisor or agent fleet. Finish likely-mutating review before expensive final validation.
4. Repository invocation envelope: owned checkout `/srv/graphy-worktrees/librsi-feedback-20260910`, private Python 3.13 environment `/srv/patent-studio/private/librsi-feedback-20260910/venv`, editable install from this checkout, native `python -m pytest`/ruff/mypy with checked-in pyproject and tests/conftest. No borrowed mutable imports or Git/Python path overrides. Evidence is under `/srv/patent-studio/private/librsi-feedback-20260910`.
5. Validate focused invariants first, then one fast suite and affected slow adaptive/store/reasoning/workflow tests following `AGENTS.md` and `docs/testing.md`. Reuse passing proof for unchanged source; widen only for a named affected invariant. Full global coverage is required for a broad core-runtime change or release, neither planned here. Preserve CI's existing checks.
6. Bound history selection and follow-up depth explicitly; one optional reflection and one proposal call per pass. Consumer adapters retain per-call time/resource limits. Measure native call counts and scoped wall/process CPU without adding nested durations or claiming provider totals.
7. Keep the public example offline, within three learning passes, at most two candidates and bounded disjoint cases per set. Preserve real negative results and raw outputs; diagnose failures before retrying. No provider calls or acceptance literals in demonstrations.
8. Commit coherent verified candidates, push the owned branch, review exact revisions and append corrections. At terminal, publish a PR and integrate reviewed changes into main under standing user authorization; do not repin consumers or publish a release.
9. No optional supervision binding is available/required for this task. Reconcile the complete user range and current deliverables locally at every boundary without inventing a supervision ledger or asking for Resume.

### Completion-evidence template

Record exact implementation commit and source hashes, inputs and observed native
results, focused/mapped tests, independent review and corrections, actual operation
cost scope, installed source/artifact, accepted status and push/main disposition.
Preserve historical results rather than relabeling failed or stale proof.

## 7. Status and required order

| Block | Scope | Depends on | Status |
|---:|---|---|---|
| 0 | Inspect bounded native learning history and operation telemetry | — | `not-started` |
| 1 | Learn from failed attempts through bounded reflection and follow-up | 0 | `not-started` |
| 2 | Demonstrate and deliver reusable proposal-generator improvement | 1 | `not-started` |

Required order: `0 → 1 → 2`.

## Block 0 — Inspect bounded native learning history and operation telemetry

Status: `not-started`

### Objective

Consumers can inspect bounded attempts and their exact native provenance, training observations and measured learning-pass execution scope through the public library.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Consumers can inspect bounded attempts and their exact native provenance, training observations and measured learning-pass execution scope through the public library.
- Potential capability loss or regression: replay drift, accidental held-out feedback, or unsupported adoption claims.
- Protected-capability effect: preserve exact source identity, bounded work and existing native acceptance/effect owners.
- Architecture and operating-model effect: extend the reusable facade and consumer adapters without host-specific state authority.
- Tradeoff and source evidence: bounded context and optional reasoning add cost; the direct request and baseline adaptive/consumer contracts require reusable behavior and truthful outcomes.

### Inputs and dependencies

Existing canonical learning inputs, native results, runtime histories and public store ports; no earlier Block dependency.

### Required work

- Add a bounded public history projection tied to exact pass input, proposal, candidate and native result roots, distinguishing failure/rejection/disabled activation/rollback from adoption.
- Make proposer-safe historical training context a distinct allowlisted projection; exclude full nested terminal trees and held-out/free-form review or failure contents.
- Record explicit logical ordering in new pass inputs; do not treat sorted pass_ids as chronology. Legacy ordering remains explicitly unknown/deterministic.
- Retain scoped elapsed/process CPU and known usage for new learning-pass host calls through existing records; distinguish nested action timing, unknown costs, reused work and failed calls.

### Scope and non-goals

History projection and learning-pass operation records only. Ordinary task exception behavior, proposal request changes and follow-up execution belong outside this Block.

### Deliverables and recorded state

Owned source, public behavior, focused tests and exact native/evidence roots establishing the objective; immutable prior evidence remains historical.

### Resource and economy contract

Section 6 governs the shared invocation envelope, bounded normal path, proof reuse and widening triggers. Review before expensive final mapped validation; no repeated producer after unchanged acceptance.

### QA and independent review

Use the existing reviewer for exact-source and substantive outcome acceptance. Mechanical tests do not establish proposal quality or substitute for inspecting actual outputs.

### Acceptance

- Public history API and native-derived attempt records are reproducible after reopening and through the non-subclass LearningStore adapter.
- Historical attempts cannot assert current strategy authority; exact roots/stages and missing measurement scope are explicit.

### Negative tests

- Reject cross-pass/profile substitution and malformed historical records; preserve missing legacy telemetry as unknown.
- Do not leak nested held-out or free-form failure/review content into the safe projection; reject contradictory new ordering.

### Completion evidence

Pending.

### Stop

Stop before new proposal/reflection or follow-up behavior owned by Block 1. This is an internal checkpoint within the full range.

---

## Block 1 — Learn from failed attempts through bounded reflection and follow-up

Status: `not-started`

### Objective

A later bounded learning pass can use exact unsuccessful-attempt feedback to request reflection and propose a materially different approach without replay drift or held-out leakage.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: A later bounded learning pass can use exact unsuccessful-attempt feedback to request reflection and propose a materially different approach without replay drift or held-out leakage.
- Potential capability loss or regression: replay drift, accidental held-out feedback, or unsupported adoption claims.
- Protected-capability effect: preserve exact source identity, bounded work and existing native acceptance/effect owners.
- Architecture and operating-model effect: extend the reusable facade and consumer adapters without host-specific state authority.
- Tradeoff and source evidence: bounded context and optional reasoning add cost; the direct request and baseline adaptive/consumer contracts require reusable behavior and truthful outcomes.

### Inputs and dependencies

Block 0 accepted; existing reasoning schemas, native proposal runtime, LearningPolicy and learning workflows.

### Required work

- Freeze bounded compatible historical context and exact references into every new enabled pass; reconstruct legacy pending/completed passes using their original request/configuration shapes.
- Add opt-in single reflection using the existing reasoning kind and durable action/result workflow; failure ends the pass without an unreviewed fallback and reflection never becomes evidence or approval.
- Support an explicit failed-predecessor follow-up using its consumed training batch under a finite lineage-depth allowance; require the same current baseline/scoring and fresh held-out inputs. Default scheduling still requires new feedback.
- Feed safe context/reflection into the next proposal request. Prevent unbounded repeat attempts and respect the configured generation/evaluation budget; keep native acceptance and rollback unchanged.

### Scope and non-goals

Generic facade composition and its policy/configuration only; no host-specific semantic logic, automatic scheduler or evaluator rule changes.

### Deliverables and recorded state

Owned source, public behavior, focused tests and exact native/evidence roots establishing the objective; immutable prior evidence remains historical.

### Resource and economy contract

Section 6 governs the shared invocation envelope, bounded normal path, proof reuse and widening triggers. Review before expensive final mapped validation; no repeated producer after unchanged acceptance.

### QA and independent review

Use the existing reviewer for exact-source and substantive outcome acceptance. Mechanical tests do not establish proposal quality or substitute for inspecting actual outputs.

### Acceptance

- Failure-informed proposals and follow-up run through normal public adapters after restart; limits and unsafe predecessor/case changes fail closed.
- Old persisted passes recover/reuse exactly and do not rerun saved provider actions; reflection is optional and each enabled pass makes at most one reflection plus one proposal call.

### Negative tests

- Reject reused/renamed held-out cases, another profile/baseline/scorer, adopted predecessors, conflicting pass options and exhausted follow-up depth.
- Malformed/failed reflection cannot produce adoption; historical failure text cannot enter proposer input; an interrupted recorded action resumes without duplicate completed calls.

### Completion evidence

Pending.

### Stop

Stop before public generator demonstration and upstream delivery owned by Block 2. This is an internal checkpoint within the full range.

---

## Block 2 — Demonstrate and deliver reusable proposal-generator improvement

Status: `not-started`

### Objective

An installed standalone consumer actually improves the configuration that generates proposals, then uses the accepted generator on a later ordinary input.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: An installed standalone consumer actually improves the configuration that generates proposals, then uses the accepted generator on a later ordinary input.
- Potential capability loss or regression: replay drift, accidental held-out feedback, or unsupported adoption claims.
- Protected-capability effect: preserve exact source identity, bounded work and existing native acceptance/effect owners.
- Architecture and operating-model effect: extend the reusable facade and consumer adapters without host-specific state authority.
- Tradeoff and source evidence: bounded context and optional reasoning add cost; the direct request and baseline adaptive/consumer contracts require reusable behavior and truthful outcomes.

### Inputs and dependencies

Block 1 accepted; current public LearningAdapter/ReasoningBackend/store/RSI contracts and existing package build/CI.

### Required work

- Supply a maintained standalone example whose adaptive target is a versioned proposal-generator configuration and whose score is measured usefulness of the proposals it actually produces under equal finite budgets.
- Run an initial rejected attempt, retain its actual observations, derive reflection/revision from those observations, evaluate on fresh held-out problems and obtain existing native adoption/restart/ordinary-use evidence.
- Demonstrate that disabling/removing relevant failure feedback prevents the claimed learned path or changes its outcome; do not key acceptance or the successful strategy only on pass IDs or canned outcomes.
- Document normal use, history/telemetry scopes, follow-up and reflection settings, storage obligations and limits; build/install the wheel, run the public example outside the source checkout and verify actual reopened native state.
- Complete mapped tests and independent source/outcome review, preserve the predecessor and evidence, push reviewed changes and verify upstream main integration without changing consumer pins.

### Scope and non-goals

Library public example, documentation and qualified upstream delivery only. No claim of trained model weights, general provider quality or deployed consumer improvement.

### Deliverables and recorded state

Owned source, public behavior, focused tests and exact native/evidence roots establishing the objective; immutable prior evidence remains historical.

### Resource and economy contract

Section 6 governs the shared invocation envelope, bounded normal path, proof reuse and widening triggers. Review before expensive final mapped validation; no repeated producer after unchanged acceptance.

### QA and independent review

Use the existing reviewer for exact-source and substantive outcome acceptance. Mechanical tests do not establish proposal quality or substitute for inspecting actual outputs.

### Acceptance

- The actual target revision is the generator configuration; the later output contains a proposal generated by that adopted revision and measured downstream benefit rather than a manually substituted task strategy.
- Installed execution imports only public libRSI and standard-library dependencies, works without Graphy/Patent Studio, and retains exact failed and accepted native records across reopen.
- Required focused/fast/affected-slow tests and exact source/outcome review pass; final branch and main contain the reviewed implementation and honest evidence.

### Negative tests

- A missing history signal, failed review/verification, fabricated score or unchanged generator cannot be reported as learned/adopted improvement.
- Keep held-out outcomes out of proposal construction, preserve baseline on rejection and do not treat acceptance rate or proposal count as downstream benefit.

### Completion evidence

Pending.

### Stop

Stop before consumer repinning/deployment, paid model experiments or release publication outside this request. This is an internal checkpoint within the full range.

---

## 8. Verification matrix

| Capability/invariant | Primary Block | Integration Blocks | Terminal proof |
|---|---:|---|---:|
| Native history/provenance, truthful scoped telemetry and legacy ordering | 0 | 1, 2 | 2 |
| Frozen historical context, held-out isolation, bounded reflection/follow-up and old-pass replay | 1 | 2 | 2 |
| Actual proposal-generator change, independent acceptance, restart/new ordinary proposal and installed public API | 2 | — | 2 |

## 9. Final completion definition

All three Blocks are accepted against current source. The installed public example
contains a real failed attempt, uses its retained evidence to improve proposal
generation, measures downstream improvement on fresh held-out problems, obtains
native acceptance, reopens and produces a new ordinary proposal with the adopted
generator. Required tests/reviews pass, owned changes are pushed and reviewed main
integration is verified. No Graphy-specific learning semantics or consumer rollout
is required; no general LLM-quality claim is inferred from the offline demonstration.
