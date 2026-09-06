# libRSI Lightweight Readiness Implementation Tracker

- Tracker status: `in-progress`
- Tracker sequence: Blocks 0–6
- Program identity: `lightweight-readiness`; qualify references as `lightweight-readiness/Block N`.
- Repository: `https://github.com/estill01/libRSI`
- Baseline: `21faded78bd1527881b93cffdef2c124d669bf9f` (2026-09-06).
- Governing objective: the user's 2026-09-06 direction to make libRSI a lightweight, useful drop-in without prolonged engineering or token expenditure.
- Canonical entry point and detailed status owner: `docs/tracker.md`.
- First eligible Block: 1 (in progress).
- Authoring-only hold: expired on the direct implement-tracker-blocks invocation, 2026-09-06. Full range 0–6 is authorized; no approval is required between Blocks (`carry-forward: false`).

## 1. Purpose and intended outcome

Make ordinary embedded libRSI use dependable enough to try on a real small task:
start a bounded improvement, save completed steps, resume, and obtain an honest
success or failure. Fix demonstrated defects through existing owners and provide
one executable example. Keep installation and operation local and simple.

Completion means the seven Blocks below pass their mapped checks and an installed
example completes a small, offline improvement and restart. It does not mean
production service qualification, arbitrary-scale performance, or a new release.

### Mission frame

- Primary outcome: a useful lightweight library with reliable small-run behavior.
- Observable completion: one public embedded example plus exact regression evidence for terminal reporting, saved progress, command cleanup, provider contracts, cheaper appends, and executable-mode currentness.
- Ordinary effect classes needed: after kickoff, narrow library fixes, regression tests, example/documentation edits, local package validation, and scoped Git checkpoints. This turn authorizes tracker documents and a planning commit only.
- Hard direct authority or safety boundaries: the user explicitly requires reporting the plan before kickoff. Preserve proposal/evidence/application separation and explicit application authority. No live provider spend, external target mutation, publication, deployment, upstream utils changes, or new credentials are required.
- Material goal alteration or reversal: distributed workers, a storage-format migration, a new workflow framework, breaking public API cleanup, or mandatory hosted infrastructure exceeds this plan.

### Target-product capability frame

- Applicability: `consequential`.
- Applicability rationale: this work changes failure handling, durability, execution cleanup, provider requests, storage cost, and snapshot behavior.
- Direct product sources: the current user's 2026-09-06 lightweight/drop-in and authoring-only instruction; `README.md`, `pyproject.toml`, and `docs/implementation/architecture-contract.md` at the baseline above; the 2026-09-06 audit identified in section 4.
- Product thesis and intended effect: developers can compose bounded evidence-driven improvement inside an existing Python program without operating another platform.
- Protected capabilities: zero required third-party dependencies in the core, domain neutrality, exact record identities and validation, resumability, external stepping, and application disabled without authority.
- Architecture strategy: retain canonical records, RuntimeEngine, workflows, SQLite, and thin optional adapters; make local corrections behind those owners.
- Requested capability: reliable and understandable small embedded runs with a realistic starting example.
- Proportionality: single local owner and small histories are the supported baseline; repair real failures without adding distributed coordination or redesigning all persistence.
- Tradeoffs: retain a broad advanced API and limited service scalability for now; improve the common path while documenting those limits.
- Uncertainty: the user has not supplied a production workload or throughput target. The bounded benchmark and two-cycle example establish small-run usefulness, not fleet capacity or model answer quality.

## 2. Target architecture and authority boundaries

`Host capability → existing workflow → RuntimeEngine → existing runtime store → LibRSIRun/result`.
The facade records each accepted step before another provider effect. Existing
runtime statuses determine operational termination; a failed run never becomes
successful evidence merely to fill a result field. Provider output remains a
proposal. Filesystem and subprocess effects remain inside their local adapters.

Choose embedded Python and one serialized local owner per working database as the
operating baseline. Existing CLI/HTTP/MCP interfaces remain available, but this
program does not qualify overlapping managed calls or multiple owners. No daemon,
worker lease, new database, scheduler, or supervisor is needed to use the example.

## 3. Existing owners to reuse

| Concern | Existing owner | Treatment |
|---|---|---|
| Termination and result projection | `runtime/records.py`, `protocol/controller.py`, `facade/run.py` | Remediate consumers of existing terminal statuses. |
| Step execution and persistence | `improvement/workflow.py`, `facade/run.py`, `facade/client.py` | Adapt existing submit/record path; retain service per-action submission. |
| Local process lifecycle | `local/commands.py` | Fix owned-process cleanup. |
| Provider content contract | `reasoning/schemas.py`, `providers/prompt.py`, `providers/openai.py` | Supply kind-specific instructions through the existing adapters. |
| Persistence integrity | `runtime/sqlite.py`, `runtime/engine.py` | Remove redundant work inside one append, preserving the storage format. |
| Target currentness | `local/filesystem.py` | Include meaningful executable-mode state. |
| Public entry and examples | `facade/client.py`, `examples/`, `README.md`, `docs/api.md` | Demonstrate existing public composition. |

Python paths above are relative to `src/librsi/`. Existing utility adapters and
conformance owners are reused unchanged unless a directly affected compatibility
fixture must be refreshed; no utility producer rebuild is part of this plan.

## 4. Prior-work and source-adaptation map

This is a new prospective program selected by the latest user instruction. It is
not a renumbering or reacceptance of the architecture-expansion program. The old
canonical tracker is preserved byte-for-byte at
[architecture-program-20260906.md](implementation/architecture-program-20260906.md).
Its SHA-256 is `d7f9068d73f3c513e888ff9fd208eea43e8b409da3f2963ef09e4193c6fd706b`.
Its conflicting active header and terminal-completion prose remain historical
claims; this planning change does not adjudicate them or reactivate old supervision.

Exactly one current program is selected: `lightweight-readiness`, in progress.
There is no required successor queue. The first eligible Block is 0;
all existing architecture-program Block identities remain historical and unchanged.

| Other planning document | Disposition |
|---|---|
| `docs/implementation/architecture-program-20260906.md` | Preserved predecessor evidence; no executable queue. |
| `docs/implementation/architecture-expansion-implementation-tracker.md` | Historical architecture design; not active. |
| `docs/implementation/parallel-implementation-plan.md` | Historical scheduling advice; no delegation or execution authority. |
| `docs/implementation/implementation-status.md` | Historical evidence ledger; not current status. |

Audit source: `/srv/patent-studio/private/librsi-audit-20260906/AUDIT.md`, SHA-256
`80d55107a7f640f4839dc8cffaac7e71ff7699ea3d9d790dd903189a8c22d3b4`.
Reproductions and JSONL logs live in the same directory. The audit belongs to the
baseline; its passing tests do not pre-accept any new Block. The compact failure
conditions below also make the plan usable without the private audit directory.

| Audit finding | Disposition | Owning Block / remaining limit |
|---|---|---|
| 1: failed run reported nonterminal | Remediate | 0 |
| 2: completed cycle lost after next exception | Remediate | 1 |
| 3: duplicate provider execution across owners | Defer mechanism; document restriction | 6; no multi-owner or overlapping managed execution qualification. |
| 4: descendants survive timeout | Remediate | 2; filesystem sandboxing and generalized resource isolation deferred. |
| 5: expensive runtime replay | Adapt narrowly | 4; storage normalization/checkpoints and long histories deferred. |
| 6: knowledge full scans / N+1 queries | Defer | Small local corpus for this tranche; revisit with a concrete growing-corpus use case. |
| 7: HTTP blocking and global lock | Defer | 6 documents optional serialized service posture; revisit when responsive service use is requested. |
| 8: executable-mode drift omitted | Remediate | 5 |
| 9: model schema omitted | Remediate | 3; no live model evaluation or provider framework. |
| Broad exports, repeated helpers, registry/store rigidity, optimization policy, provider lifecycle | Defer | No general cleanup, breaking namespace changes, alternate stores, multi-provider routing, new search policy, or new client-management API. |

## 5. Scope, non-goals, and proportionality

In scope: the seven bounded outcomes below. Fix duplicate code only where needed
for those outcomes. Each Block is independently reviewable; the count reflects
owner boundaries, not seven new subsystems.

Out of scope: action leases, exactly-once effects, multi-user service operation,
record-graph storage, schema migrations, cross-request caches, broad validation
frameworks, export deprecations, new transports, automatic recursion generations,
monitoring, optimization-policy expansion, and CI redesign. These are intentional
exclusions, not an automatic second phase.

Keep the current record and on-disk schemas where possible. Snapshot revision
changes for executable-mode coverage are deliberate currentness corrections.
Any unavoidable protocol projection adjustment stays additive and narrowly tested.

## 6. Block execution contract

1. This authoring turn stops after a validated planning commit and report. After direct kickoff, execute the full selected program in order; internal Block Stops delimit edits and do not require repeated user approval.
2. Re-read only the selected Block, touched owners, and mapped tests. Preserve unrelated work, including the existing untracked `uv.lock`. Follow the host storage preflight and keep artifacts under `/srv/patent-studio`.
3. Use `not-started`, `in-progress`, `completed-with-open-items`, `accepted`, `reopened`, or `blocked`. Update the table and Block together when implementation begins; read-only planning is not implementation.
4. Use the smallest existing mechanism. Review the diff for correctness and scope before final mapped validation. No standing supervisor or independent-agent fleet is required by this program; a focused self-review is not labeled independent review.
5. Freeze the candidate commit/content root before acceptance proof. Record affected commands and results once; rerun only proof made stale by a correction. Existing mandatory release/CI gates remain intact, but this program does not claim a release.
6. Run focused regression first, affected integration tests next, then changed-file lint/types. At terminal validation, run the union of mapped tests once, static checks once, and one wheel/example smoke check. Do not run the entire 807-test suite after every Block or manually dispatch duplicate CI matrices. Widen only for a mapped failure, changed shared serialization semantics, or an actual existing required gate.
7. No live model calls. Reuse installed dependencies and audit fixtures. For Block 4 allow one profiling pass, one selected optimization, and one corrective iteration; benchmarks use only 5 and 10 actions with at most three samples per size/revision and a 120-second wall bound per set. No automatic larger sweep.
8. If the bounded performance approach cannot meet acceptance, record it as an open item and continue independent safe work in Blocks 5 and 6; do not introduce a storage migration or claim full completion. Return the concrete result before proposing a materially larger performance project.
9. Record local scoped checkpoints. Remote publication/deployment is excluded. Ordinary implementation choices within this plan need no new user gate. A missing input blocks only its actual dependent work; preserve that boundary and continue unaffected work.
10. Accept each Block only when its acceptance and mapped proof hold. After the final observable outcome, stop; exclusions do not become fresh tasks.

### Current execution binding

- Direct scope: the 2026-09-06 bare skill invocation authorizes the complete current lightweight-readiness program, Blocks 0–6 and its installed example/restart outcome.
- Optional supervision owner: discovery returned bootstrap-needed; canonical range gate returned `Governing outcome member directory is unavailable or unsafe`. No supervision group or parallel ledger was created. Reconcile the full range locally at each boundary; retry the maintained gate without substituting fabricated authority.
- Test invocation: repository cwd `/srv/patent-studio/workspaces/libRSI`; the CI-owned `python -m pytest` chain uses `/srv/patent-studio/private/librsi-gcp/venv/bin/python` (3.13.5), editable `src/librsi`, pytest 9.1.1, existing `pyproject.toml` options and explicit node selection. `TMPDIR=/srv/patent-studio/private/tmp`; Git environment has only `GIT_PAGER`, no worktree/index overrides. Logs reside under `/srv/patent-studio/private/librsi-implementation-20260906`.
- Capability-frame SHA-256: `f7df78fc07b132d48c5d057f09268f96646a1777bd37c403a4892c256cb9e474`. This exact frame is reused per Block while unchanged.

### Completion-evidence template

For each Block replace `Pending.` with: exact implementation commit/content root;
changed paths; focused and mapped commands/results; compatibility and resource
limits; self-review findings and closure; retained open items; post-Block status;
and Git durability posture. Independent review and external approval are
`not-applicable` unless an actual existing boundary requires them. Historical
failed/aborted measurements remain diagnostic. No additional evidence database is
needed; this tracker owns the planning record.

## 7. Status and required order

| Block | Scope | Depends on | Status |
|---:|---|---|---|
| 0 | Honest terminal status and failure retrieval | — | `accepted` |
| 1 | Persist each completed embedded improvement step | 0 | `in-progress` |
| 2 | Stop owned subprocess descendants on timeout | — | `not-started` |
| 3 | Make optional provider requests self-contained | — | `not-started` |
| 4 | Remove redundant runtime append work | 1 | `not-started` |
| 5 | Detect executable-mode target changes | — | `not-started` |
| 6 | Ship the small embedded improvement example | 0, 1, 2, 3, 4, 5 | `not-started` |

Required order: `0 → 1 → 2 → 3 → 4 → 5 → 6`.
Dependencies identify correctness prerequisites; independent work may continue
under the bounded exception in section 6. Block 6 may be prepared provisionally
while 4 is open, but terminal program acceptance still requires all seven Blocks.

## Block 0 — Honest terminal status and failure retrieval

Status: `accepted`

### Objective

A supported failed or cancelled run is observably finished and its recorded reason is retrievable.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Correct completion detection.
- Potential capability loss or regression: Keep successful outcome projections unchanged.
- Protected-capability effect: Operational failure must not become negative evidence.
- Architecture and operating-model effect: Reuse existing terminal statuses and recorded failures; no new lifecycle.
- Tradeoff and source evidence: Audit finding 1 and `runtime/records.py`, `protocol/controller.py` at baseline.

### Inputs and dependencies

- No earlier Block dependency. Use `failure.jsonl` and the existing improvement/service fixtures.

### Required work

- Derive status, next-action, and managed-stop behavior from `TERMINAL_RUN_STATUSES` consistently.
- Make terminal failure information available through existing status/outcome projections using recorded RuntimeFailure data; preserve successful result behavior. Do not manufacture an ImprovementResult.
- Cover the existing supported workflow variants with a compact shared case table, including cancellation only where it already exists.

### Scope and non-goals

Protocol completion projection and its facade/service consumers. No new cancellation API, workflow base class, or schema redesign.

### Deliverables and recorded state

Narrow projection/consumer correction and focused lifecycle regressions.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- A nonretryable failed improvement reports terminal true, has no pending action, exposes its recorded failure, and repeated managed calls return a terminal report without invoking a provider.
- Normal successful outcomes remain compatible and external/embedded callers agree on termination.

### Negative tests

- A retryable waiting state remains nonterminal. A failure is never projected as successful evidence. Unsupported cancellation is not newly enabled.

### Completion evidence

- Implementation commit: `1e8bd71` (pushed to `origin/codex/librsi-lightweight-readiness-plan`).
- Frozen candidate root: `9a57766d0209ed9d33734750713cbdddb7ead12c5c49e4dc6026a39543574a08`; controller, new terminal regressions, and protocol documentation.
- Validation: 8 initial focused cases passed; the RSI fixture needed its existing external capability routes and then passed with 5 mapped compatibility cases (6 passed in 40.38s). Initial fixture failure is diagnostic, not an implementation failure. Lint, formatting, and controller mypy passed. Logs: `block0-focused.log`, `block0-mapped.log` in the execution directory.
- Product-capability review: consequential; frame hash in current execution binding. Selected direct controller projection through runtime terminal statuses. A new failure-result domain record or workflow superclass adds cost without necessary capability. Successful projections, explicit RSI authority, retry waiting, and supported cancellation preserved by current behavioral checks.
- Self-review: no fabricated successful result, unchanged success envelope, additive failure data. No independent reviewer required. Post-Block audit: accepted; no open Block 0 items.
- Canonical supervision gate unavailable as recorded above; local range remains all seven Blocks, with Blocks 1–6 pending.

### Stop

Stop before changing the embedded persistence loop owned by Block 1.

## Block 1 — Persist each completed embedded improvement step

Status: `in-progress`

### Objective

A provider exception after a completed cycle leaves that cycle saved and resumable.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Retain completed work across later errors.
- Potential capability loss or regression: Avoid altered resource accounting or transition order.
- Protected-capability effect: Exact submissions, currentness, and authority remain enforced.
- Architecture and operating-model effect: Reuse facade submit/record and workflow stepping; at most a small private step hook.
- Tradeoff and source evidence: Audit finding 2 and `facade/run.py`, `improvement/workflow.py` at baseline.

### Inputs and dependencies

- Block 0; `facade.jsonl`; existing improvement resource/continuity fixtures and runtime store interface.

### Required work

- Route embedded managed improvement through accepted per-action persistence before dispatching the next cycle; preserve workflow policy as its sole semantic owner.
- Retain the public run method and provider protocol. Prefer direct stepping or a narrow callback over a generalized workflow driver.
- On persistence failure, do not dispatch further provider work; resume only from actually recorded transitions.

### Scope and non-goals

Embedded improvement step durability. No exactly-once effects, action receipts, distributed coordination, or wholesale RSI-loop refactor.

### Deliverables and recorded state

Incremental facade persistence and restart/failure regression using SQLite.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- With cycle one complete and cycle two raising, the store contains cycle one. Reopen and resume without repeating that completed cycle.
- Successful runs retain their canonical action/result order and budget behavior.

### Negative tests

- A failed store write does not advance to another effect. Divergent or stale submissions still fail through existing checks.

### Completion evidence

Pending.

### Stop

Stop before process execution cleanup in Block 2.

## Block 2 — Stop owned subprocess descendants on timeout

Status: `not-started`

### Objective

A timed-out local experiment stops its owned process group before reporting completion.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Prevent background descendants from continuing a timed-out experiment.
- Potential capability loss or regression: Do not terminate unrelated host processes or change normal output interpretation.
- Protected-capability effect: Timeout remains an invalid observation, not evidence against a claim.
- Architecture and operating-model effect: Use standard-library process-group/session lifecycle in the local adapter.
- Tradeoff and source evidence: Audit finding 4 and `local/commands.py` at baseline; GCP is POSIX.

### Inputs and dependencies

- No earlier Block dependency. Use the harmless delayed-marker reproduction and existing command adapter tests.

### Required work

- Launch the POSIX command in an owned session/process group; terminate, escalate after a short bounded grace, and reap on timeout.
- Preserve exit status/output and invalid-observation behavior. Document the supported cleanup guarantee and explicitly report unsupported host behavior rather than silently claiming process-tree cleanup.
- State that allowed_roots constrains cwd; it is not a filesystem sandbox.

### Scope and non-goals

Timeout cleanup for the existing local command adapter. No container backend, Windows job-object implementation, cgroups, output artifact service, or general resource manager.

### Deliverables and recorded state

Owned-group cleanup, a short platform note, and a deterministic descendant regression.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- The delayed child marker is never written after timeout; the owned group is stopped before the invalid observation returns.
- Normal success, nonzero exit, and timeout output behavior remain usable.

### Negative tests

- Cleanup does not signal an unrelated process. A child ignoring the graceful signal is handled by bounded escalation on supported POSIX hosts.

### Completion evidence

Pending.

### Stop

Stop before provider contract work in Block 3.

## Block 3 — Make optional provider requests self-contained

Status: `not-started`

### Objective

An ordinary configured reasoning request tells the provider the exact content shape it must return.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Make existing model adapters usable without hidden schema knowledge.
- Potential capability loss or regression: Do not loosen strict validation or add required dependencies.
- Protected-capability effect: Provider responses retain proposal-only authority.
- Architecture and operating-model effect: Keep schema guidance beside existing reasoning validators and pass it through the existing prompt.
- Tradeoff and source evidence: Audit finding 9 and `reasoning/schemas.py`, `providers/prompt.py`, `providers/openai.py` at baseline.

### Inputs and dependencies

- No earlier Block dependency. Existing offline provider fixtures and REASONING_KINDS are authoritative inputs.

### Required work

- Add concise kind-specific field/type/required-value guidance owned beside the validators; include it in the existing prompt. Use a small mapping, not a schema-generation framework.
- Check each supported kind against a valid minimal fixture and existing rejection rules so guidance cannot silently omit required fields. Use the provider-neutral prompt contract already present; do not add a second provider-native schema lane.

### Scope and non-goals

Provider output instructions only. No live eval, client-lifecycle API, billing integration, new providers, broad retry policy, multi-provider routing, or model-specific tuning.

### Deliverables and recorded state

Self-contained prompts, offline contract tests, and a short provider documentation update.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- Every existing reasoning kind has sufficient field/type guidance; fake-client valid responses pass the unchanged validator.
- The existing adapter invocation and successful result shape remain compatible; no new provider configuration is required to supply the schema.

### Negative tests

- Missing/extra fields and malformed responses remain rejected. Core import remains possible without the optional SDK.

### Completion evidence

Pending.

### Stop

Stop before changing runtime append behavior in Block 4.

## Block 4 — Remove redundant runtime append work

Status: `not-started`

### Objective

Small durable runs become measurably cheaper without changing storage format or skipping integrity checks.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Reduce avoidable per-append CPU.
- Potential capability loss or regression: Prevent stale caches or weaker replay/tamper detection.
- Protected-capability effect: Keep canonical bytes, divergent-append rejection, and restart validation.
- Architecture and operating-model effect: Reuse an already-verified prefix within the same SQLite write transaction only.
- Tradeoff and source evidence: Audit finding 5 and `runtime/sqlite.py`, `runtime/engine.py` at baseline.

### Inputs and dependencies

- Block 1; benchmark fixture in `probes.py`; runtime replay and SQLite integrity tests. Refresh a matched baseline after the durability correction.

### Required work

- Profile the existing 5/10-action fixture once. Choose one local optimization of duplicate decode/serialization/replay within an append transaction.
- Prefer validating the old prefix once and checking the candidate/newly written rows against it; use the existing engine for the next transition. Retain every observable corruption rejection in mapped tests, including any stored-row mutation the existing schema permits.
- Keep full independent restart verification. No persistent cache, trust-mode switch, new record table, checkpoint format, or migration.

### Scope and non-goals

One narrow append-path optimization. Knowledge queries, service status reconstruction, long-history scalability, and storage normalization are deferred.

### Deliverables and recorded state

One reviewed local optimization, preserved integrity regressions, and matched before/after CPU measurements.

### Resource and economy contract

Section 6 applies. Use only the 5/10-action matched benchmark, at most three samples per size/revision, one selected change and one corrective iteration; retain failed measurements.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- On matched 10-action inputs, median append CPU is at most 75% of the refreshed baseline; action/state roots and persisted outcomes agree. Treat wall time as diagnostic on a shared host.
- Existing tamper, schema, replay, idempotency, and restart tests pass. No new dependency or schema version.
- Apply the section 6 investigation cap; an unmet target stays explicitly open and cannot be accepted by relabeling the benchmark.

### Negative tests

- Corrupt old bytes/projections, invalid next transitions, and divergent duplicate appends still reject. No cross-operation cached prefix hides external edits.

### Completion evidence

Pending.

### Stop

Stop before snapshot semantics in Block 5; do not expand into a persistence redesign.

## Block 5 — Detect executable-mode target changes

Status: `not-started`

### Objective

Changing a local file executable bit makes its target snapshot observably different.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Keep executable behavior changes visible to currentness.
- Potential capability loss or regression: A corrected snapshot revision may stale existing target-bound evidence.
- Protected-capability effect: Preserve content identity and explicit evidence currentness.
- Architecture and operating-model effect: Extend the existing filesystem snapshot entries only.
- Tradeoff and source evidence: Audit finding 8 and `local/filesystem.py` at baseline.

### Inputs and dependencies

- No earlier Block dependency. Use the 0644-to-0755 reproduction and existing filesystem/currentness tests.

### Required work

- Include a defined executable-mode representation in file snapshot entries on supported filesystems.
- Document that older filesystem snapshots may compare stale after this correction; no history rewrite or evidence migration.
- Keep content/symlink handling and ignored-path semantics unchanged.

### Scope and non-goals

Executable-mode currentness only. Directory traversal optimization, timestamp tracking, generalized ACLs, and atomic whole-tree snapshots are excluded.

### Deliverables and recorded state

Mode-aware snapshot entries, focused regression, and compatibility note.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- The same file changing from 0644 to 0755 changes its snapshot; repeated snapshots without semantic changes agree.
- Existing content, symlink, and stale-evidence checks pass.

### Negative tests

- Touching an incidental timestamp does not itself change the snapshot. Old evidence is not silently rebound to the corrected revision.

### Completion evidence

Pending.

### Stop

Stop before the public example and final mapped validation in Block 6.

## Block 6 — Ship the small embedded improvement example

Status: `not-started`

### Objective

A developer can install the library, run a real bounded improvement example, and understand exactly what the host supplies.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: Provide a practical drop-in starting point.
- Potential capability loss or regression: Avoid implying unattended service or autonomous coding capabilities.
- Protected-capability effect: Exercise the public facade with proposal/application separation intact.
- Architecture and operating-model effect: A small example composes existing records and capabilities; no new runtime.
- Tradeoff and source evidence: The current lightweight user instruction, README.md, and audit feature-scope findings.

### Inputs and dependencies

- Blocks 0–5 for final acceptance. Existing examples, public facade, and deterministic improvement fixtures may be reused as design inputs.

### Required work

- Add `examples/embedded_improvement.py`: a tiny deterministic target, explicit goal/criterion, measured candidate comparison, and public start/step/resume/result use. Bound it to two cycles and at most four candidate experiments; no application or network calls.
- Demonstrate interruption after a completed cycle and reopening from SQLite. The example must execute without importing tests or private repository paths.
- Put a short practical entry near the beginning of README/docs/api and link the optional provider setup. Explain the host cycle provider clearly.
- Document one serialized owner, small histories/corpora, optional service limitations, cwd-only authority, and the deferred audit issues without turning them into new code work.
- Run the terminal mapped regression union and one installed-wheel example smoke check after the final candidate is stable.

### Scope and non-goals

An executable example, concise onboarding, and this program's integration proof. No new convenience framework, API deprecations, provider fleet, docs rewrite, release, or deployment.

### Deliverables and recorded state

Public example, concise usage/limits documentation, exact validation results, and reconciled tracker status.

### Resource and economy contract

Section 6 applies. One focused regression batch and its mapped checks; no live providers, full-suite repetition, or extra hardening.

### QA and independent review

Focused mechanical proof plus a separate diff/self-review pass for the stated acceptance and boundary. Independent review is not required by this program; preserve any existing gate actually affected by the change.

### Acceptance

- In a fresh writable directory, the installed example completes its bounded improvement and interrupted/restarted path using only declared dependencies; the already completed cycle is not repeated.
- Instructions identify required host capability inputs and yield a clear terminal result.
- Blocks 0–5 are accepted and mapped proof is current; retained exclusions are explicit.

### Negative tests

- Missing optional SDK or absent host capability is explained rather than replaced with simulated success. No hidden test-package imports or provider credentials are required.

### Completion evidence

Pending.

### Stop

Stop before any deferred work, hosted-model evaluation, publication, or deployment.

## 8. Verification matrix

| Capability/invariant | Primary Block | Mapped existing proof | Terminal proof |
|---|---:|---|---|
| Terminal failure reporting | 0 | External protocol, outcome, service-boundary tests; one compact workflow case table | 6 |
| Saved improvement step/restart | 1 | Improvement workflow/resource tests, facade tests, SQLite restart regression | 6 |
| Owned-process timeout cleanup | 2 | Command adapter success/failure/timeout tests and delayed descendant fixture | 6 |
| Self-contained provider contract | 3 | All reasoning-kind validators and existing offline provider adapter tests | 6 |
| Faster append with exact integrity | 4 | Runtime replay tests and `tests/test_block7_runtime_sqlite_integrity.py`; matched benchmark | 6 |
| Executable-mode currentness | 5 | Local filesystem snapshot and affected currentness tests | 6 |
| Installed public example | 6 | Union above, lint/format/types, one wheel smoke execution | 6 |

Select exact test nodes from these owners once during each Block; reuse the mapped
set until changed behavior justifies widening. Existing broad release fixtures are
not evidence that this new implementation is accepted, and the lightweight program
is not authority to delete them or weaken their invariants.

## 9. Final completion definition

The governing outcome owner is this tracker. Its terminal rule is simple: all
seven Blocks accepted at exact current revisions, mapped proof current, the public
installed example and its restart working, and exclusions accurately documented.
A commit, handoff, exhausted investigation allowance, or passing structural
verifier is not implementation completion. Historical architecture-program status
is preserved separately and does not govern this program's completion.

After authoring, report this path, the qualified range
`lightweight-readiness/Block 0` through `lightweight-readiness/Block 6`, the selected
small-run/single-owner assumption, verification result, and first eligible Block.
Do not begin implementation until the user's subsequent kickoff instruction.
