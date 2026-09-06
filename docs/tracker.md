# libRSI Adaptive Operation Implementation Tracker

- Tracker status: `in-progress`
- Tracker sequence: Blocks 0–2
- Program identity: `adaptive-operation`; qualify references as `adaptive-operation/Block N`.
- Repository: `https://github.com/estill01/libRSI`
- Baseline: `545104792830369de6acbe8f305eb724a99cf950` on `main`.
- Governing objective: the user's direct instruction to implement the proposed reusable improvement runner, versioned strategies, and consumer template fully, end to end.
- Canonical owner: `docs/tracker.md`; first eligible Block: 0.
- Direct range: the full program and its installed restart/adoption outcome. No authoring-only hold; implement immediately after authoring verification.

## 1. Purpose and intended outcome

An ordinary consumer task uses a persistent strategy and records its measured outcome.
A bounded learning pass uses that history to generate competing strategy revisions,
measures them, runs existing self-change evaluation/review/application, and preserves
the accepted revision. After restart, the next ordinary task uses that revision.
The shared composition belongs in libRSI; the host supplies domain work and scoring.

### Mission frame

- Primary outcome: reusable improvement through consumer use, with real adoption rather than a saved proposal alone.
- Observable completion: an installed public example records actual task outcomes, derives strategy proposals from them, measures candidates on distinct cases, persists native workflow progress, adopts only an accepted revision, restarts, and uses it on a new task. Rejection, rollback, and restart negatives preserve the appropriate active strategy.
- Ordinary effect classes needed: library composition/local adapter changes, focused tests, templates/examples/docs, local offline execution and wheel validation, scoped commits and branch pushes.
- Hard direct authority or safety boundaries: retain proposal/evidence/application separation and existing self-change gates; no live model spend, deployment, release, production consumer mutation, or edits to Graphy/Patent Studio are needed for this library/template deliverable.
- Material goal alteration or reversal: a new distributed service, model training platform, automatic source rewriting, replacement semantic engine, or broad storage migration exceeds the lightweight request.

### Target-product capability frame

- Applicability: `consequential`.
- Applicability rationale: this adds a reusable consumer operation that can activate a revised strategy and affect subsequent tasks.
- Direct product sources: the current direct user request and preceding three-piece proposal; `docs/api.md`, `docs/consumer-integration.md`, `src/librsi/improvement/workflow.py`, `src/librsi/rsi/workflow.py`, and `pyproject.toml` at the baseline.
- Product thesis and intended effect: ordinary embedded applications can improve a bounded host-supplied reasoning/proposal strategy using measured task outcomes.
- Protected capabilities: zero mandatory dependencies, domain-neutral semantic owners, exact evidence/currentness, bounded execution, durable restart, and explicit application with verification/rollback.
- Architecture strategy: add composition and local profile support around existing records, artifacts, RuntimeStore, ImprovementWorkflow, RSIWorkflow, and capability routes; retain those owners' acceptance authority.
- Requested capability: a maintained standard loop, versioned strategies, and a public consumer adapter template with demonstrated next-task adoption.
- Proportionality: one serialized local owner with small histories and separate consumer profiles. A reusable layer is justified by Graphy and Patent Studio as intended consumers; a standalone platform is not.
- Tradeoffs: support bounded strategy configurations and prompts first. Keep built-in evaluation/governance rules fixed, retain explicit host scoring, and use the host's existing scheduling mechanism.
- Uncertainty: no production consumer workload, scorer, or provider budget was supplied. Offline evidence must demonstrate the full mechanism without claiming proven model-quality gains or deployed consumer integration.

## 2. Target architecture and authority boundaries

`Consumer task → active strategy → host execution/measurement → immutable feedback`.
`Feedback + configured ReasoningBackend → candidate strategies → existing investigation/comparison/improvement → RSI historical/shadow/review → application/verification/rollback → next task`.

A local profile owns active strategy data and references to feedback/pass inputs.
Existing runtime stores alone own workflow history. The profile is application state,
not a second workflow status ledger. Persist requests and completed host results before
advancing, use exact current snapshots, and make local strategy application recoverable.
Ordinary tasks cannot run through an unresolved activation. Host adapters own domain
inputs, actual outputs, scores, distinct evaluation cases, and independent review.

## 3. Existing owners to reuse

| Concern | Existing owner | Treatment |
|---|---|---|
| Versioned data and lineage | TargetRef, TargetSnapshot, Observation, ArtifactRef, record codecs | Reuse without a new semantic schema. |
| Immutable local payloads | `local/artifacts.py` | Reuse for strategy revisions, task observations, pass inputs and completed host results. |
| Workflow durability | RuntimeStore, SQLiteRuntimeStore, persist_transitions | Reuse; no migration or parallel lifecycle. |
| Proposals | ReasoningBackend and typed hypothesis-generation requests | Adapt into competing strategy hypotheses. |
| Evaluation and selection | InvestigationWorkflow, ExperimentEvaluator, CandidateTrialBatch, ImprovementWorkflow | Compose; never manufacture accepted outcomes. |
| Self-change and application | RSIWorkflow, SelfChangePolicy, ApplicationWorkflow | Compose existing historical/shadow/review/apply/verify/rollback routes. |
| Public integration | `facade/`, `local/`, `examples/`, docs | Add bounded opt-in composition and a maintained adapter template. |

## 4. Prior-work and source-adaptation map

The accepted predecessor is preserved byte-for-byte at
`docs/implementation/lightweight-readiness-20260906.md`, SHA-256
`8cecb7e77fa16d6fdb47a49c5889fb9e6a1cb614586400769b799cf9694d419e`.
Its Blocks 0–6 remain accepted historical evidence. The older architecture program and
all other planning documents retain their historical dispositions; none is another
active queue. Exactly one current program is selected: `adaptive-operation`, Blocks 0–2.
No successor queue is required. The new direct request supersedes only the prior
feature exclusions needed for this proposed standard operation.

## 5. Scope, non-goals, and proportionality

In scope: persistent strategy profiles and feedback, reusable bounded orchestration,
provider-generated revisions, exact native governance/application, a maintained host
adapter template, and actual installed restart/adoption proof.

Out of scope: shared global learning across consumers, production consumer rollout,
new daemons/transports, distributed owners, model weight training, arbitrary core
policy rewriting, storage redesign, and release publication. Keep profiles separate;
reuse the host scheduler for cadence. No new dependencies are required.

## 6. Block execution contract

1. Execute the complete range 0–2 in order. Block Stops delimit changes and acceptance; they do not end the user request.
2. Update the table and Block when implementation starts; preserve unrelated work including untracked `uv.lock` and all existing private evidence. Follow the host storage preflight.
3. Use the narrowest existing owner. Independent agent review is not required for this bounded composition; perform a separate self-review before final proof. Do not start a supervisor or agent fleet.
4. Run focused tests first, then mapped existing checks. Freeze candidate bytes before acceptance; rerun only proof invalidated by corrections. At terminal completion run the native static checks and one complete branch-covered suite, plus one installed-wheel example. Do not repeat whole suites after every Block or dispatch duplicate CI matrices.
5. Use existing Python 3.13.5 validation environment `/srv/patent-studio/private/librsi-gcp/venv/bin/python`, repository cwd, native `python -m pytest` and pyproject settings. `TMPDIR=/srv/patent-studio/private/tmp`. Evidence: `/srv/patent-studio/private/librsi-adaptive-20260906`. No live model calls; injected deterministic backends must derive proposals/measurements from inputs rather than return canned acceptance.
6. Use visible finite limits on candidates, feedback/evaluation cases, iterations, and host executions. Resume consumes saved request/result identities. One local profile owner is supported; no claim of exactly-once arbitrary external effects after a crash before recording.
7. Record scoped checkpoints and pushes on `codex/librsi-adaptive-operation`. Keep deployment, release publication, consumer production changes, and a new merge outside this implementation run.
8. Retry the maintained optional range gate at boundaries. If its owner is unavailable, record the limitation and reconcile full direct scope locally without fabricated bindings or an alternate supervision ledger.
9. Accept only after substantive outcomes and current proof hold. Preserve failed diagnostics; repair concrete in-scope defects, including affected compatibility fixtures, through their owner. Stop after the final observable outcome.

### Completion-evidence template

For each Block replace Pending with exact commit/content root, changed owners,
focused/mapped commands and results, capability review against the frame, self-review
closure, retained limitations, post-Block status, and commit/push posture. Record final
installed artifact identity and actual reopened state separately from test success.

## 7. Status and required order

| Block | Scope | Depends on | Status |
|---:|---|---|---|
| 0 | Persist strategy profiles and measured feedback | — | `not-started` |
| 1 | Run bounded improvement and native self-change adoption | 0 | `not-started` |
| 2 | Ship consumer template and prove installed next-task adoption | 1 | `not-started` |

Required order: `0 → 1 → 2`.

## Block 0 — Persist strategy profiles and measured feedback

Status: `not-started`

### Objective

A local consumer profile retains exact strategy revisions, ordinary task feedback, and immutable learning-pass inputs across restart.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: A local consumer profile retains exact strategy revisions, ordinary task feedback, and immutable learning-pass inputs across restart.
- Potential capability loss or regression: partial or stale state must not be mistaken for an accepted strategy.
- Protected-capability effect: retain exact native records, finite execution, domain ownership, and application authority.
- Architecture and operating-model effect: compose existing owners with a local single-owner adapter.
- Tradeoff and source evidence: explicit host capabilities and small profiles follow the direct lightweight request and consumer integration contract.

### Inputs and dependencies

Baseline record/artifact/runtime contracts; no earlier Block dependency.

### Required work

- Add a local strategy/profile adapter that reuses existing canonical record serialization and LocalArtifactStore; active state and pending-pass references are application bindings only.
- Record task input/output/measurement with its exact producing strategy; reject conflicting reuse of task/pass IDs and cross-profile state.
- Provide recoverable local strategy apply/rollback operations tied to the exact native action; preserve immutable revisions and reject unexpected currentness drift.

### Scope and non-goals

Local profile state and feedback only. No proposal runner, acceptance policy, general registry, cleanup, or new runtime schema.

### Deliverables and recorded state

Typed composition records, local profile adapter, focused persistence/currentness tests.

### Resource and economy contract

Section 6 applies: bounded offline inputs, focused proof first, current proof reused, and no duplicate full-suite or provider execution.

### QA and independent review

Focused mechanical proof plus a separate capability/authority/self-review pass before final mapped validation. No independent agent is required by this program.

### Acceptance

- Restart recovers the identical active strategy and feedback; independent profiles remain isolated.
- Duplicate completed task IDs reuse the same recorded observation; conflicting input or profile identities reject.
- Interrupted local application can reconcile the exact action; old strategy revisions remain available.

### Negative tests

- Malformed/tampered canonical payloads, stale strategy effects, cross-profile references, and conflicting task/pass identities reject.

### Completion evidence

Pending.

### Stop

Stop before proposal generation and learning orchestration in Block 1.

## Block 1 — Run bounded improvement and native self-change adoption

Status: `not-started`

### Objective

A reusable runner turns measured feedback into tested strategy revisions and adopts only a revision accepted through existing self-change/application owners.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: A reusable runner turns measured feedback into tested strategy revisions and adopts only a revision accepted through existing self-change/application owners.
- Potential capability loss or regression: partial or stale state must not be mistaken for an accepted strategy.
- Protected-capability effect: retain exact native records, finite execution, domain ownership, and application authority.
- Architecture and operating-model effect: compose existing owners with a local single-owner adapter.
- Tradeoff and source evidence: explicit host capabilities and small profiles follow the direct lightweight request and consumer integration contract.

### Inputs and dependencies

Accepted Block 0; existing reasoning, investigation, evaluation, improvement, RSI and application contracts.

### Required work

- Provide an explicit consumer adapter contract and configured ReasoningBackend for generation; map structured proposals to canonical hypotheses and strategy candidates.
- Compose real baseline/candidate measurements and native investigation/comparison; use bounded counts and exact feedback, scorer/adapter identities, and distinct evaluation case sets.
- Persist the improvement and governance/application updates before another host effect; resume pending work using existing workflow state.
- Use existing historical evaluation, forward-shadow, independent review, apply, verify, and rollback. Persist the accepted strategy so a later ordinary task uses it; stop ordinary tasks during unresolved activation.
- Expose explicit run-task and bounded learning-pass operations suitable for a host scheduler; use saved feedback rather than inventing success.

### Scope and non-goals

One reusable opt-in composition layer and its necessary helpers. No alternative evaluator/runtime, indefinite loop, generalized scheduler, or source-code self-rewriting.

### Deliverables and recorded state

Public runner, consumer protocol, proposal/measurement composition, checkpoint and adoption tests.

### Resource and economy contract

Section 6 applies: bounded offline inputs, focused proof first, current proof reused, and no duplicate full-suite or provider execution.

### QA and independent review

Focused mechanical proof plus a separate capability/authority/self-review pass before final mapped validation. No independent agent is required by this program.

### Acceptance

- Feedback reaches the proposal backend; candidates are evaluated from actual host outputs and native policy derives acceptance.
- A rejected or insufficient candidate does not replace the active strategy; failed post-application verification restores the prior strategy.
- An interrupted pass resumes saved progress and completed work without repeating recorded effects; exact profile/currentness checks remain enforced.
- Resource/candidate/case bounds are validated before affected host calls; holdout observations are absent from proposal inputs.

### Negative tests

- Missing capabilities, invalid/duplicate proposals, changed pass inputs, overlapping case sets, stale activation, failed review, and exhausted bounds do not produce an accepted active revision.

### Completion evidence

Pending.

### Stop

Stop before the public template, installed example, and final program proof in Block 2.

## Block 2 — Ship consumer template and prove installed next-task adoption

Status: `not-started`

### Objective

A consumer can use a maintained template and installed example to run the complete feedback-to-adoption cycle and observe a new ordinary task using the accepted revision after restart.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: A consumer can use a maintained template and installed example to run the complete feedback-to-adoption cycle and observe a new ordinary task using the accepted revision after restart.
- Potential capability loss or regression: partial or stale state must not be mistaken for an accepted strategy.
- Protected-capability effect: retain exact native records, finite execution, domain ownership, and application authority.
- Architecture and operating-model effect: compose existing owners with a local single-owner adapter.
- Tradeoff and source evidence: explicit host capabilities and small profiles follow the direct lightweight request and consumer integration contract.

### Inputs and dependencies

Accepted Blocks 0–1; public package/export/typing/documentation and existing CI owners.

### Required work

- Add a self-contained executable consumer example and documented adapter template using public imports. Generate strategy ideas from measured task feedback and compute candidate scores from actual executions.
- Demonstrate separate profiles, bounded improvement, interruption/reopen, adoption, and a next ordinary task using the accepted strategy. Explain provider injection, host-owned scoring/review, caller cadence, and retained limits.
- Run focused example proof, mapped existing workflow/authority/compatibility tests, terminal native static checks and full branch-covered suite, and one fresh installed-wheel smoke run.
- Independently reopen actual installed output/profile/runtime state, reconcile all requested effects, and record current artifact identities.

### Scope and non-goals

Library template, docs, integration proof and exact completion evidence. No edits or rollout to Graphy/Patent Studio, provider spend, new service, release, or automatic merge.

### Deliverables and recorded state

Executable example, adapter guide, public exports, accepted tracker, installed artifact and reopened outcome evidence.

### Resource and economy contract

Section 6 applies: bounded offline inputs, focused proof first, current proof reused, and no duplicate full-suite or provider execution.

### QA and independent review

Focused mechanical proof plus a separate capability/authority/self-review pass before final mapped validation. No independent agent is required by this program.

### Acceptance

- A fresh wheel environment with only declared dependencies runs the example without repository-test imports or credentials.
- Measured outcomes cause a strategy revision; after interruption/restart and accepted activation, the next ordinary task loads and uses the new revision.
- All required Block outcomes are current; static checks, full program regression, and installed proof pass with no unresolved required work.

### Negative tests

- The example cannot claim success from a hard-coded acceptance flag, a proposal alone, or loading the original strategy after reported adoption; missing dependencies/capabilities remain explicit.

### Completion evidence

Pending.

### Stop

Stop before deferred work, production consumer integration, live model evaluation, publication, or deployment.

## 8. Verification matrix

| Invariant | Owner | Proof |
|---|---|---|
| Strategy/feedback identity and profile isolation | Block 0 | Focused persistence and existing artifact/record checks |
| Generated proposals, measured selection, bounded execution | Block 1 | Focused learning tests and existing improvement/resource checks |
| Governed adoption, restart, rejection and rollback | Block 1 | Native RSI/application tests and focused interruption tests |
| Public next-task behavior and dependency boundary | Block 2 | Public example, installed wheel, complete native tests/static checks |

## 9. Final completion definition

All Blocks 0–2 must be accepted, with no remaining required effects. The actual
installed example must complete a measured learning pass and reopen with a changed
accepted strategy that its next ordinary task uses. Logs, proposals, test counts,
commits, or a completed tracker alone do not establish that result. Consumer production
integration and proof of live-model quality remain explicit separate outcomes.
