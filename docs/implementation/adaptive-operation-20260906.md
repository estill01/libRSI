# libRSI Adaptive Operation Implementation Tracker

- Tracker status: `accepted`
- Tracker sequence: Blocks 0–2
- Program identity: `adaptive-operation`; qualify references as `adaptive-operation/Block N`.
- Repository: `https://github.com/estill01/libRSI`
- Baseline: `545104792830369de6acbe8f305eb724a99cf950` on `main`.
- Governing objective: the user's direct instruction to implement the proposed reusable improvement runner, versioned strategies, and consumer template fully, end to end.
- Canonical owner: `docs/tracker.md`; first eligible Block: none (Blocks 0–2 accepted).
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
- Hard direct authority or safety boundaries: retain proposal/evidence/application separation and existing self-change gates; no live model spend, deployment, release, production consumer mutation, or edits to consumer repositories are needed for this library/template deliverable.
- Material goal alteration or reversal: a new distributed service, model training platform, automatic source rewriting, replacement semantic engine, or broad storage migration exceeds the lightweight request.

### Target-product capability frame

- Applicability: `consequential`.
- Applicability rationale: this adds a reusable consumer operation that can activate a revised strategy and affect subsequent tasks.
- Direct product sources: the current direct user request and preceding three-piece proposal; `docs/api.md`, `docs/consumer-integration.md`, `src/librsi/improvement/workflow.py`, `src/librsi/rsi/workflow.py`, and `pyproject.toml` at the baseline.
- Product thesis and intended effect: ordinary embedded applications can improve a bounded host-supplied reasoning/proposal strategy using measured task outcomes.
- Protected capabilities: zero mandatory dependencies, domain-neutral semantic owners, exact evidence/currentness, bounded execution, durable restart, and explicit application with verification/rollback.
- Architecture strategy: add composition and local profile support around existing records, artifacts, RuntimeStore, ImprovementWorkflow, RSIWorkflow, and capability routes; retain those owners' acceptance authority.
- Requested capability: a maintained standard loop, versioned strategies, and a public consumer adapter template with demonstrated next-task adoption.
- Proportionality: one serialized local owner with small histories and separate consumer profiles. A reusable layer is justified by multiple intended downstream consumers; a standalone platform is not.
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
| 0 | Persist strategy profiles and measured feedback | — | `accepted` |
| 1 | Run bounded improvement and native self-change adoption | 0 | `accepted` |
| 2 | Ship consumer template and prove installed next-task adoption | 1 | `accepted` |

Required order: `0 → 1 → 2`.

## Block 0 — Persist strategy profiles and measured feedback

Status: `accepted`

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

- Changed `local/learning.py` (SHA-256 `5f529c690c6f9c24e0315a848bda016d08347c5a8d0819a82cc475a64ec98b21`) and `tests/test_learning_store.py` (`2c96a12016333a35de2e47bd10d632b1f363aa308626f674460563d679f6792f`); scoped implementation checkpoint `9bf3b79`, pushed before Block 1.
- Focused store regressions: 4 passed in 1.34s (`block0-focused.log`). Mapped existing local artifact/authority checks: 3 passed in 0.69s (`block0-mapped.log`). Changed-file ruff lint/format and mypy passed.
- Capability frame SHA-256: `760c3f7835b791e0356bd1d44bd7118e2187c193fd7fe846311cc00d402b79be`. Selected a local application binding plus existing immutable artifact/runtime owners over copying records into another database or keeping active strategy only in process memory. No new semantic record or runtime schema was added.
- Self-review: profile IDs qualify target identity, feedback preserves producing snapshots and recorded order, pass/task conflicts reject, cached records are immutable, and strategy data/effect identity change atomically. Runtime/application authorization remains the native workflow/runner responsibility in Block 1; this lower-level host store does not derive acceptance.
- Limits: one serialized owner and small histories; arbitrary external effects interrupted before recording may repeat. No independent reviewer required. Post-Block audit: accepted; no open Block 0 items. Optional canonical range gate remains unavailable; full range is reconciled locally.

### Stop

Stop before proposal generation and learning orchestration in Block 1.

## Block 1 — Run bounded improvement and native self-change adoption

Status: `accepted`

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

- Implementation checkpoint `18f55080aa1e675e3134cb93f919268499dd667b` is pushed. A scoped follow-up distinguishes provider execution failure from malformed proposals. Owners: `facade/learning.py`, `learning_records.py`, `learning_host.py`, `learning_workflows.py`, `local/learning.py`, and `tests/test_adaptive_loop.py`.
- Focused adoption, interruption, review rejection, activation-disabled, rollback, invalid-input and store tests: 15 passed in 597.64s (`block1-focused.log`). Added final result/pass binding and insufficient-effect proof: 7 passed in 87.14s (`block1-final-delta.log`); final failure-classification delta: 5 passed in 2.51s (`block1-failure-classification.log`). Overlapping proof is intentional only for changed branches; 16 distinct tests are covered across the store and loop files.
- Four mapped existing facade, self-change approval, and application-authority regressions passed in 82.22s (`block1-mapped.log`). Ruff lint/format, mypy and tracker verification passed. Logs are under `/srv/patent-studio/private/librsi-adaptive-20260906`.
- Current result-binding audit independently loaded completed native outcomes and checked actual profile state (`block1-result-binding-audit.log`). Accepted native root `9f965e9629ebc7fe5a216d4e41ed450124ab481f8e18be9722633be2908c45dd` retains active strategy root `85e0aa15afe7ef7f18bb20d28c952976360399de92b2f08c6246089fcb3c1cdb`. The recovery test interrupts after local activation before receipt persistence, then again after terminal-result persistence, and proves the proposer/reviewer each ran once and only remaining verification measurements resumed.
- Capability frame SHA-256 remains `760c3f7835b791e0356bd1d44bd7118e2187c193fd7fe846311cc00d402b79be`. Native InvestigationWorkflow, ComparativeSelectionPolicy, ImprovementWorkflow and RSIWorkflow derive all dispositions. One bounded generation supplies competing full configurations; native canonical rank breaks single-objective ties. Only the local strategy pointer is applied; native governance and verification/rollback remain authoritative.
- Self-review closed exact metric/provider/reviewer bindings, immutable pass inputs, non-leaking holdout inputs, finite case/candidate allowances, failure versus evidence separation, and both activation/terminal crash windows. No independent agent is required. Retained limits: serialized local owner, small histories, host-bounded individual calls, and possible replay of an external effect interrupted before recording. Native audit replay is CPU-heavy; schedule learning outside ordinary request handling.
- Optional canonical range gate still returns `Governing outcome member directory is unavailable or unsafe`; no binding or supervision ledger was fabricated. Local range reconciliation: Blocks 0–1 accepted; Block 2 remains the authorized frontier. No live provider, consumer production, release, deployment or merge effects occurred.

### Stop

Stop before the public template, installed example, and final program proof in Block 2.

## Block 2 — Ship consumer template and prove installed next-task adoption

Status: `accepted`

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

Library template, docs, integration proof and exact completion evidence. No edits or rollout to consumer repositories, provider spend, new service, release, or automatic merge.

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

Implementation, installed behavior, and final validation are complete.

- Public template/API/guide checkpoint: `0cb3db59e36f794bf9188dc2593f1406d91afd3b`, pushed. Public exports, separate consumer profiles, example/public-source and legacy compatibility checks: 4 passed in 0.48s (`block2-focused.log`). Native lint, formatting (254 files) and mypy (149 files) passed.
- Initial fresh zero-dependency wheel SHA-256: `3affee4b9536505cfd85ebd68ade1022cbdda1828b9c231b346bff44eacb2586`. Actual installed example resumed a saved proposal action, adopted offsets `[3, 4]` from `[1]`, reopened, and produced ideas `[43, 44]` with measured next-task error 0. Native disposition `verified`, result root `c5c4b041788b581b672a2cb571a123f2d0ce6771d8f376f19c71ff6c435ee6e3`, active/next-task strategy root `57d8eb3cd3cbc72e9100c2c058c508aaf308f3afa74305907890064048589824`. `block2-installed-demo.json` and independent `block2-installed-state-audit.json` retain actual completed investigation/improvement/governance/application states and three feedback records.
- Baseline main CI run `34051288258` exposed two stale fingerprint fixtures: 830 passed, 2 failed in 6231.26s. Reviewed the prior prompt guidance, terminal outcome, improvement callback, and scoped SQLite codec changes; no authority weakening or new domain leak was found. Commit `4230652` refreshes only the provider adapter's own source root and the generic-tree expected root; all upstream artifact pins, the 102-file generic scope, and leakage checks remain unchanged. Both exact tests pass (`block2-fingerprint-fixes.log`, 2 passed in 5.47s). Review detail: `source-fingerprint-review.json`.
- Economy adjustment preserves the complete 849-node regression scope. The initial native branch-covered run was interrupted after 10 passing adaptive cases, with no test failures (`block2-full-suite.log`). Pytest did not flush that prefix's coverage file, so its pass evidence is retained and its coverage is conservatively excluded. `block2-shards.json` partitions the remaining **839** exact collected nodes into disjoint 444/395-node native pytest runs on the two available cores. Both completed successfully: **444 passed in 8433.57s** and **395 passed in 8427.21s**, with existing deprecation warnings. Their command/result files retain exact selection and environment. `block2-regression-membership.json` verifies all **849 distinct cases** are accounted for. Combining the two saved coverage fragments with `--keep` and enforcing `coverage report --fail-under=90` passed at **90.218712%** combined line/branch coverage (`block2-coverage-report.log`, `block2-coverage.json`). No supplemental run or threshold reduction was needed.
- Final wheel SHA-256: `8e54be371b3e23cecdb0f891dfcf7745e73d49f9038f2265c0fdedad696e749b` (`dist-final/librsi-0.3.0-py3-none-any.whl`). The archive comparison proves all Python members byte-identical to the original tested wheel; only `providers/compatibility.json` and wheel `RECORD` differ (`block2-wheel-byte-review-2.json`). A fresh `wheel-venv-final` contains only libRSI, validates the installed provider fingerprint, and reopens the actual accepted profile/native states (`block2-final-installed-demo-2.json`, `block2-final-installed-state-audit.json`). Its completed-pass reuse is reported honestly as `resumed_saved_pass: false`; the original actual interruption/adoption run remains the byte-identical functional proof. The initial rebuild invocation used the evidence cwd and failed before installation; corrected cwd execution and diagnostics are retained separately.
- Concurrent test-efficiency work was merged into this branch as `05eca0b`, followed by repository validation guidance at `e7d8848`. It changes selection, CI cadence, documentation, and immutable fixture reuse; runtime and example bytes are unchanged. The full shards collected the pre-efficiency tests; final collection confirms the same 849-node scope. The three modified fixture consumers passed separately in 203.85s (`/srv/patent-studio/private/librsi-test-efficiency-20260906/cross-domain-after.log`). Current source, examples, and changed test files match verified efficiency commit `3504432` byte-for-byte; their lint/format checks also pass. This reuses applicable proof as required by the merged `AGENTS.md`, without restarting the full suite. No merge to main was performed by this implementation run.
- Final reconciliation at `e7d8848` is recorded in `block2-final-reconciliation.json`: all 149 installed package members match current source; the original installed interruption/adoption and independent reopen remain current functional evidence. The later README development link changes descriptive metadata only. Untracked `uv.lock` and the archived predecessor tracker retain their recorded hashes. The capability frame and native authority boundaries are unchanged; no required product effect remains.
- The optional terminal range gate still reports `Governing outcome member directory is unavailable or unsafe` (`block2-terminal-range-gate.log`). Full direct scope and actual installed state were reconciled locally without inventing a supervision binding. Blocks 0–2 are accepted. The final scoped documentation checkpoint records this acceptance and is pushed to `codex/librsi-adaptive-operation`; production consumer wiring, live-model quality evaluation, publication, deployment, and a new merge remain separate outcomes.

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
