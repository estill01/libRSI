# libRSI Architecture Expansion Implementation Tracker

- Tracker status: `active`
- Tracker sequence: Blocks 0–26
- Repository: `https://github.com/estill01/libRSI`
- Governing objective: evolve libRSI into a domain-neutral, evidence-driven validation, investigation, improvement, and governed recursive-self-improvement library.
- Canonical status owner: this file.
- First eligible Block: 3.

## 1. Purpose and intended outcome

Evolve the current deterministic policy kernel into a batteries-included but
replaceable semantic engine that can validate claims, investigate questions,
improve targets, and govern self-change while preserving exact provenance,
resumability, candidate/application separation, and host-neutral execution.

Completion means:

- the same canonical engine completes validation, investigation, improvement,
  application/verification/rollback, and governed self-change workflows;
- externally driven, managed, and hybrid control produce semantically equivalent
  state and outcomes;
- an operator can submit a target, objective, evaluation contract, capabilities,
  and authority envelope to a standalone local service and receive a durable RSI
  run that generates competing hypotheses, proposes discriminating tests,
  interprets evidence, compares interventions, applies only when authorized,
  verifies, and iterates;
- a Software Factory consumer and a deterministic non-software target both use
  the engine without leaking their ontologies into the core; and
- the public Python, CLI, service, and MCP projections are versioned, tested,
  documented, installable, and backed by the same runtime authority.

### Mission frame

- Primary outcome: a reusable libRSI product whose evidence semantics and
  improvement lifecycle work across hosts and domains.
- Observable completion: every Block is accepted at a current pushed revision,
  the terminal verification matrix passes, public examples execute from the
  built wheel, and the two required cross-host dogfoods produce current outcomes.
- Ordinary effect classes needed: library code and schemas, reference SQLite and
  local adapters, tests and dogfoods, consumer integration, documentation,
  package builds, scoped Git commits, and pushes to the configured remote.
- Hard direct authority or safety boundaries: no PyPI publication, hosted-model
  spend, production deployment, external credential use, or irreversible target
  application without separate authority; authoritative application remains
  capability-gated and defaults off.
- Material goal alteration or reversal: making software/Git fundamental to the
  core, creating a second lifecycle or evidence authority, dropping control-plane
  neutrality, or redefining the product as a generic orchestration platform.

### Target-product capability frame

- Applicability: `consequential`.
- Applicability rationale: this program changes public feature behavior,
  canonical representations, architecture strategy, operating model, persistence,
  and external integration surfaces.
- Direct product sources: `README.md` and
  `docs/implementation/architecture-contract.md` at
  `91ab1976b9cd56985e2dbd5b1ab522081672a5cf`, plus the maintained scope revision
  and predecessor program listed in the source map below.
- Product thesis and intended effect: users should progress from `validate` to
  `investigate` to `improve` and use governed recursion only when the improvement
  machinery itself is a target.
- Protected capabilities: exact identity/provenance, invalid-execution neutrality,
  target currentness, candidate/application separation, externally driven use,
  zero-dependency low-level APIs, `0.2.x` compatibility until explicit migration,
  and consumer-to-libRSI dependency direction.
- Architecture strategy: own semantic contracts and deterministic transitions;
  expose replaceable protocols; ship thin local defaults and optional transport or
  provider adapters without rebuilding generic infrastructure platforms.
- Requested capability: complete reusable validation, investigation, improvement,
  application, and RSI workflows with durable outcomes and multiple control planes.
- Proportionality: the plan builds the semantic owners and minimum reference
  implementations needed for a useful package, while delegating generic models,
  optimizers, schedulers, storage platforms, and transports to mature adapters.
- Tradeoffs: batteries-included operation adds persistence and optional dependencies;
  strict identity/currentness increases schema discipline; staged compatibility
  delays interface stabilization but prevents premature public commitments.
- Uncertainty: the final open-source license and any hosted provider chosen for the
  optional adapter remain external decisions; neither blocks Blocks 3–25.

## 2. Target architecture and authority boundaries

```text
TargetSnapshot + Claim/Question/Goal/Constraint
                    ↓
        Knowledge + Experiment/Evidence
                    ↓
     deterministic Run/Event/Action engine
                    ↓
 Validation → Investigation → Improvement → governed RSI
                    ↓
       canonical Outcome and event projections
                    ↓
 Python / embedded facade / CLI / managed service / HTTP / MCP / host adapters
```

Canonical records and deterministic transitions own semantic truth. `KnowledgeStore`
owns reusable epistemic persistence; the runtime store owns run/event/action state.
Capability implementations execute work but cannot promote their own outputs to
truth, selection, application, or self-change authority. Software Factory and other
hosts import libRSI; libRSI never imports them. Transport/session state is never a
second lifecycle owner.

Managed standalone mode is a reference host over these same owners. It may use
an optional reasoner/executor provider to generate hypotheses and carry out
actions, but provider output remains a proposal or observation until canonical
validation, evidence, comparison, authority, and application policies act. An
embedded consumer may supply capabilities directly. Exactly one composition
owner starts each provider process; a Software Factory-managed composition
therefore does not let libRSI launch a competing Codex app-server.

## 3. Existing owners to reuse

| Concern | Existing owner | Treatment |
|---|---|---|
| Canonical identity and serialization | `src/librsi/identity.py`, `src/librsi/records.py` | Reuse and extend only through owning Blocks. |
| Hypotheses and evidence updates | `src/librsi/hypotheses.py` | Adapt behind generic aggregation without weakening exact references. |
| Command experiments | `src/librsi/experiments.py`, `src/librsi/ports.py` | Preserve as an adapter over generic experiment semantics. |
| Currentness and materiality | `src/librsi/checkpoints.py` | Reuse in target/runtime currentness owners. |
| Search lanes and review gates | `src/librsi/portfolios.py`, `reviews.py`, `selections.py` | Extend; do not create parallel governance ledgers. |
| Self-change seed policies | `src/librsi/selector_policies.py` | Generalize in Block 17 through ordinary intervention/evidence records. |
| Composition | `src/librsi/kernel.py` | Retain as the low-level deterministic API, not the public workflow facade. |
| Repository quality gates | `.github/workflows/ci.yml`, `pyproject.toml` | Reuse for all focused and mapped validation. |
| Historical implementation proof | `docs/implementation/implementation-status.md` | Preserve as evidence; canonical live status is in this tracker. |

## 4. Prior-work and source-adaptation map

The hashes below identify the exact predecessor/source bytes inspected at
`91ab1976b9cd56985e2dbd5b1ab522081672a5cf`. Later routing-only edits that point
those documents back to this canonical tracker do not replace or silently revise
the recorded source snapshot.

| Source or predecessor | Exact revision/hash | Disposition | Owning Block | Remaining work |
|---|---|---|---:|---|
| Architecture contract | `7fe76f9e6744e7049ea4f508ecd73a704e188dc63a1fbed5a99573a9d52c3190` | reuse | 0 | Preserve as the architecture authority. |
| Historical 0–25 tracker | `9d4d73b05db19ff1a57f1f2998399f2a65475d331580e6670a2a0f24490e346c` | replace as active route; preserve as historical source | 0–26 | Execute through this full-contract tracker. |
| Scope/dogfood amendment | `2a746a63a670f43abc3f937d6d05be9bae90969f9ccacce96bff5cd0063c1b0e` | adopt | 3–26 | Integrated into Block scope and acceptance below. |
| Server/MCP extension | `19e144439bfc912c1ad8d8d39dfcdc52cb1efa324578376cd6af26fbcfb39775` | adopt and renumber | 21 | Implement after runtime/outcome/CLI contracts stabilize. |
| Parallel plan | `8e09ae2417e8c16b2726af9767729985506b5712f26740e7618d18cac581d717` | advisory | 3–26 | Scheduling never changes range or acceptance. |
| Historical status ledger | `a59a6a283c163d886cba15b317ea532b32e5e4b4937a49857801ce9c94dcd289` | preserve evidence | 0–2 | Future status/evidence records follow this tracker. |

### Status and numbering migration

- Historical `verified` for predecessor Blocks 0–2 maps to canonical `accepted`.
- Historical `ready` for predecessor Block 3 maps to `not-started`; eligibility is
  derived from accepted dependencies and does not imply implementation work.
- Predecessor Blocks 0–20 retain their numbers.
- Predecessor Block 20A becomes Block 21.
- Predecessor Blocks 21, 22, 23, 24, and 25 become Blocks 22, 23, 24, 25, and 26.
- No accepted Block is renumbered, reopened, split, merged, or credited with new work.

## 5. Scope, non-goals, and proportionality

### In scope

- Canonical semantic records, epistemics, experiments, targets/currentness,
  knowledge, durable runtime transitions, capabilities, workflows, outcomes,
  application/rollback, self-change governance, and required public projections.
- Thin SQLite/local defaults, optional reasoner/server/MCP adapters, incremental
  Software Factory consumption, and deterministic non-software dogfoods.
- Embedded, externally driven, and managed standalone modes over the same
  engine, including target/objective submission and autonomous hypothesis,
  experiment, candidate, application, verification, and iteration workflows.

### Out of scope

- A generic agent framework, scheduler, worker fleet, tracing platform, artifact
  platform, vector database, MLOps suite, optimizer implementation, coding agent,
  API gateway, UI, notification service, or production multi-tenant control plane.
- Automatic application authority, hidden model/provider authority, or a second
  lifecycle/knowledge/evidence ledger created by an adapter or transport.
- Software Factory QA/supervision/delivery, Patent Studio domain behavior, a
  public Codex app-server proxy, or a second controller inside the service.

### Proportionality

Each Block must use the narrowest existing semantic owner and add only the reference
implementation required by its acceptance. External systems remain replaceable behind
protocols. A concrete failure may widen only its affected proof or owner; optional
hardening without a reproduced in-scope failure is omitted.

## 6. Block execution contract

1. The requested range is the complete current tracker, Blocks 0–26 and the
   observable completion outcome. Blocks 0–2 are accepted history; implementation
   resumes at Block 3.
2. Execute one eligible Block at a time in dependency order. A Block Stop is an
   internal checkpoint and never contracts this full-tracker request.
3. Before implementation-producing work, change the table row and Block status from
   `not-started` to `in-progress`; preserve unrelated work and inspect the live tree.
4. Reuse exact accepted records, fixtures, and validation evidence after a cheap
   currentness check. Do not rebuild or rerun unchanged producers for confidence.
5. Implement through the stated owner, run focused proof first, finish mutating
   review, freeze the candidate, then run mapped proof and exact-revision review.
6. Accept a Block only when every acceptance and negative-test condition has current
   evidence. Record the scoped commit and non-force push posture before advancing.
7. If input is genuinely non-delegable, isolate its descendant closure and continue
   every independent Block or subject; `blocked` is forbidden while safe work exists.
8. Licensing is the only forecast legal decision: prepare the Block 26 decision
   packet when the release candidate exists. Do not infer an open-source grant.
9. No Block may publish to PyPI, deploy a server, spend hosted-model budget, or apply
   to an authoritative external target without separate current authority.

### Continuation-first license gate

- Decision needed: the user must select the exact public license grant (the planned
  packet compares MIT and Apache-2.0) or explicitly select no license.
- Why it is non-delegable: choosing an open-source license grants legal rights to
  recipients and cannot be inferred from repository visibility or a request that the
  repository be public; distributed copies retain the grant after later changes.
- Earliest decision packet: prepare it in Block 26 after the public API, artifact
  contents, and compatibility/migration position are frozen.
- Exact blocked subset: without that answer, do not add a `LICENSE`, license
  classifier or reuse-right claim; do not accept the license-dependent Block 26
  acceptance clause or declare the tracker complete.
- Safe continuation: execute all work in Blocks 3–25 and all license-independent
  Block 26 work, including API/docs/build/examples/migration validation, artifact
  inspection, and preparation of the decision packet.
- Forbidden effects remain forbidden regardless of the answer: no PyPI publication,
  GitHub Release, production deployment, or public announcement without separate
  current authority.
- Authoritative revisit trigger: a direct user selection of the exact license or an
  explicit no-license choice. Until then, Block 26 remains `in-progress` or
  `completed-with-open-items`, and safe work continues rather than marking the whole
  program blocked.

### Supervised execution and monitoring

Each implementation thread for the remaining range uses one isolated
`supervise-tracker-runs` group bound to the exact libRSI repository revision,
tracker hash, requested range, and active Block. Supervisors observe and review
changed state but do not implement libRSI, execute provider calls, or mutate
consumer repositories. Software Factory and Patent Studio integration evidence
is reviewed in its owning repository; no monitor combines their authority or
content with libRSI merely to save threads.

### Completion-evidence template

```markdown
### Completion evidence

- Repository commit: `<sha>`
- External/domain revision or root: `<value or not-applicable with reason>`
- Inputs: `<paths, IDs, versions, hashes>`
- Outputs: `<paths, IDs, versions, hashes>`
- Focused validation: `<commands and results>`
- Mapped validation: `<commands and results>`
- Candidate freeze: `<commit/content root and currentness>`
- Remediation closure: `<finding/change/proof rows or not-applicable>`
- Resource posture: `<bounds and actual use>`
- Independent review: `<review identity/root or not-applicable>`
- Retained open work: `<items or none>`
- Decision/continuation posture: `<bounded decision state or not-applicable>`
- Post-block audit: `<accepted, reopened, or blocked with reason>`
- Git durability: `<commit and push posture>`
```

## 7. Status and required order

| Block | Scope | Depends on | Status |
|---:|---|---|---|
| 0 | Architecture contract and compatibility baseline | — | `accepted` |
| 1 | Canonical immutable records and identity | 0 | `accepted` |
| 2 | Hypothesis/experiment referential integrity | 1 | `accepted` |
| 3 | General epistemics and aggregation | 1, 2 | `accepted` |
| 4 | Generic experiments, metrics, and evaluation | 1, 3 | `accepted` |
| 5 | Targets, snapshots, and currentness | 1, 4 | `accepted` |
| 6 | Persistent knowledge and SQLite store | 1, 5 | `accepted` |
| 7 | Durable semantic Run/Event/Action engine | 1, 6 | `accepted` |
| 8 | Capability protocols and neutral dispatch | 7 | `accepted` |
| 9 | Provider-neutral reasoner contract | 3, 7, 8 | `accepted` |
| 10 | Validation workflow and result | 3–9 | `accepted` |
| 11 | Investigation workflow and result | 10 | `accepted` |
| 12 | Intervention and candidate lifecycle | 5, 11 | `accepted` |
| 13 | Goals, constraints, and evaluation contracts | 5, 12 | `completed` |
| 14 | Comparative evaluation and selection | 4, 12, 13 | `completed` |
| 15 | Complete improvement workflow and result | 10–14 | `completed` |
| 16 | Application, verification, and rollback | 15 | `completed` |
| 17 | Generalized RSI and self-change governance | 7, 16 | `completed` |
| 18 | Embedded/managed local runtime and high-level Python facade | 6, 8, 15–17 | `not-started` |
| 19 | Outcome serialization and external projections | 10, 11, 15–18 | `not-started` |
| 20 | CLI, target admission, and external-agent protocol | 7, 19 | `not-started` |
| 21 | Managed service, HTTP, and MCP projections | 7, 8, 19, 20 | `not-started` |
| 22 | Optional provider/Codex app-server integrations | 9, 18–20 | `not-started` |
| 23 | Software Factory consumer integration | 5, 8, 12, 15–20 | `not-started` |
| 24 | End-to-end embedded/external/managed dogfoods | 10, 11, 15–23 | `not-started` |
| 25 | Comprehensive cross-domain proof | 24 | `not-started` |
| 26 | Public API, docs, packaging, migration, release gate | 21–25 | `not-started` |

Required execution order for this single-writer run:

`0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22 → 23 → 24 → 25 → 26`

## Block 0 — Architecture contract, namespace plan, and legacy baseline

Status: `accepted`

### Objective

Freeze the architecture, ownership, control-plane, domain-neutrality, and `0.2.0`
compatibility contracts before semantic expansion.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: one maintained architecture contract and executable compatibility baseline.
- Potential capability loss or regression: premature doctrine could constrain useful implementation paths.
- Protected-capability effect: preserves all `0.2.0` low-level exports and host-neutrality.
- Architecture and operating-model effect: establishes canonical semantic ownership without implementing later workflows.
- Tradeoff and source evidence: accepted contract at `bd3815d51a326dc7f5ace8f54ce462c34e251605`; later scope revision narrows infrastructure ownership without reopening this Block.

### Inputs and dependencies

- Baseline `d96cc666c7800681dfdde2f991f841b09155dfe8`.

### Required work

- Preserved accepted work: architecture contract, namespace plan, module ownership map, and rooted compatibility fixtures.

### Scope and non-goals

- In scope: architecture and compatibility contract only.
- Not in scope: Block 1+ semantic implementation.

### Deliverables and recorded state

- `docs/implementation/architecture-contract.md` and `tests/fixtures/v020_contract.json` with compatibility tests.

### Resource and economy contract

Not applicable: accepted documentation and deterministic fixture proof are reused.

### QA and independent review

Accepted PR #3 and CI run `32520018410`; later work must preserve the baseline.

### Acceptance

- Architecture owners and invariants are explicit; compatibility tests and the pre-existing suite pass; no reverse Software Factory dependency exists.

### Negative tests

- Reject removal or drift of a legacy public export without an explicit migration contract.

### Completion evidence

- Repository commit: `bd3815d51a326dc7f5ace8f54ce462c34e251605`.
- Focused and mapped validation: PR #3 CI `32520018410`, Python 3.11–3.13.
- Post-block audit: accepted; detailed evidence remains in the historical status ledger.
- Git durability: merged and present in current `main` history.

### Stop

Stop before canonical record implementation.

## Block 1 — Canonical immutable domain records and identity model

Status: `accepted`

### Objective

Provide complete immutable semantic records with deterministic identity, lineage, and lossless serialization.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: durable canonical records instead of dictionary/hash placeholders.
- Potential capability loss or regression: stricter constructors can reject previously tolerated ambiguous input.
- Protected-capability effect: presentation metadata remains non-identity-bearing and compatibility wrappers remain additive.
- Architecture and operating-model effect: makes exact records the shared substrate for every later owner.
- Tradeoff and source evidence: accepted commits `1528c7e` and `0fc0fb2`; strictness is preferred over silent semantic coercion.

### Inputs and dependencies

- Accepted Block 0 contract.

### Required work

- Preserved accepted work in `identity.py` and `records.py`, including typed references, immutable values, schema versions, and reconstruction.

### Scope and non-goals

- In scope: generic record/identity substrate.
- Not in scope: migrating hypothesis and experiment policies, owned by Block 2.

### Deliverables and recorded state

- Canonical record family, deterministic serialization, and record-hardening regression tests.

### Resource and economy contract

Not applicable: reuse accepted exact fixtures and CI evidence.

### QA and independent review

PRs #5 and #7 supplied implementation and independent post-merge hardening.

### Acceptance

- Identity changes only with identity-bearing content; round trips preserve semantics; ambiguous values and reference mismatches fail closed.

### Negative tests

- Reject tampered roots, non-finite values, ambiguous coercions, mutable nested state, and reference-type/root mismatches.

### Completion evidence

- Repository commits: `1528c7ecc5eec0e44136ceb8b54e3fa09bb5bf74` and `0fc0fb2a2da70dabda4a5b2da2eacb09e357aede`.
- Focused and mapped validation: CI runs `32525534734` and `32551045555`.
- Post-block audit: accepted; no new work credited by this migration.
- Git durability: merged and present in current `main` history.

### Stop

Stop before policy migration or generic epistemic aggregation.

## Block 2 — Hypothesis and experiment referential integrity

Status: `accepted`

### Objective

Bind hypotheses, experiment criteria, execution input, observations, evidence, and target snapshots by exact immutable identity.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: criteria substitution and stale-evidence application become unrepresentable on the canonical path.
- Potential capability loss or regression: callers must echo exact input roots and supply complete canonical records.
- Protected-capability effect: invalid execution remains null evidence; legacy scalar APIs remain compatibility wrappers.
- Architecture and operating-model effect: establishes the exact epistemic/experiment boundary later generalization must preserve.
- Tradeoff and source evidence: accepted commits `73539e8` and `a394360`; additional caller discipline buys reproducible evidence lineage.

### Inputs and dependencies

- Accepted Block 1 records and identity semantics.

### Required work

- Preserved accepted canonical hypothesis creation/application and command experiment design/preparation/evaluation.

### Scope and non-goals

- In scope: referential integrity and compatibility wrappers.
- Not in scope: generic Claim aggregation or general metric/trial ontology.

### Deliverables and recorded state

- Exact hypothesis/evidence references, immutable command specs, correlated observations, and regression tests.

### Resource and economy contract

Not applicable: reuse accepted deterministic tests and current CI.

### QA and independent review

PRs #10 and #12 supplied implementation and independent exactness hardening.

### Acceptance

- Evaluation consumes only criteria in the exact spec; stale evidence, target mismatch, and observation/input mismatch fail closed; invalid runs preserve confidence.

### Negative tests

- Reject empty predictions, degenerate criteria, normalized-away argv/cwd differences, malformed specs, and mismatched exact roots.

### Completion evidence

- Repository commits: `73539e88f4add2bb62345b824f5df034810f450a` and `a3943609f283bce5d9c0ca248a53115a8b5c30c7`.
- Focused and mapped validation: CI runs `32554375281` and `32554825264`.
- Post-block audit: accepted; no Block 3 or 4 work is inferred.
- Git durability: merged and present in current `main` history.

### Stop

Stop before general epistemic aggregation.

## Block 3 — General epistemic model and pluggable aggregation

Status: `accepted`

### Objective

Make Claims and Hypotheses reusable outside improvement loops through explicit evidence relationships and replaceable aggregation policy.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: general claims, coexistence of conflicting evidence, and policy-selectable belief aggregation.
- Potential capability loss or regression: generic abstraction could weaken Block 2 exact identity or compatibility behavior.
- Protected-capability effect: exact hypothesis/evidence/target provenance and null-evidence neutrality remain mandatory.
- Architecture and operating-model effect: epistemic truth moves behind an `EvidenceAggregator` contract rather than one hard-coded scalar update.
- Tradeoff and source evidence: architecture contract sections 2 and 9 plus scope revision Block 3; use one built-in linear policy before optional models.

### Inputs and dependencies

- Accepted Blocks 1–2 and current `records.py`, `hypotheses.py`, and compatibility fixtures.

### Required work

- Define claim kinds/status and canonical evidence relationships.
- Add provenance/currentness validation and an `EvidenceAggregator` protocol.
- Move existing linear confidence behavior behind a built-in aggregator without changing compatibility outputs.

### Scope and non-goals

- In scope: semantic epistemics and aggregation.
- Not in scope: general experiment metrics/trials, persistence, reasoner calls, or workflow orchestration.

### Deliverables and recorded state

- Epistemic records/policies/protocols, public exports, focused tests, and migration-compatible built-in aggregation.

### Resource and economy contract

Use deterministic in-memory fixtures; no provider calls or broad dogfoods. Run focused epistemic tests before the full package suite.

### QA and independent review

Review exact provenance, compatibility, contradictory evidence, and aggregator authority at the frozen candidate revision.

### Acceptance

- Claims validate independently of improvement; conflicting evidence coexists with provenance; pluggable aggregation produces typed state; current linear behavior remains available.

### Negative tests

- Reject evidence for a different claim/target snapshot, unsupported relationship kinds, aggregator output with invalid state, and infrastructure failure treated as counterevidence.

### Completion evidence

- Repository commit: `a585aa5370dc6ece38c8bc1f0b6a89d6c389b609`.
- External/domain revision or root: not applicable; Block 3 is a deterministic
  in-memory library boundary.
- Inputs: authoritative base `a5fa63540a14e34cfdea156a56533e43336b928a`,
  accepted Blocks 1–2, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: `src/librsi/epistemics.py`, canonical `BeliefState` in
  `src/librsi/records.py`, the `HypothesisPolicy` aggregation adapter, public
  exports/composition, and `tests/test_block3_epistemics.py`.
- Focused validation: Python 3.12 focused Block 3 review suite, `14 passed`;
  referential-integrity and `0.2.0` compatibility tests remained green.
- Mapped validation: Python 3.12 Ruff and format checks passed; mypy passed all
  16 source files; full suite `71 passed` at `90.77%` branch coverage; sdist/wheel
  build and isolated wheel import smoke passed.
- Candidate freeze: content root
  `cca6fc7b78590bf265b4c2ca518ce43e20001f3f32ce17e70be6a76879f90b86`
  remained unchanged through mapped validation and final independent review.
- Remediation closure: independent review found and rechecked two fail-closed
  defects—replaceable aggregators can no longer reinterpret null/infrastructure
  evidence, and stale prior belief cannot be rebound to a newer target snapshot.
- Resource posture: deterministic in-memory fixtures only; no provider, storage,
  subprocess-experiment, hosted-model, or external-target effects.
- Independent review: Hubble, read-only, against base `a5fa63540a14e34cfdea156a56533e43336b928a`
  and the frozen candidate root; final disposition `accepted` with no material findings.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 3,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: Claims and Hypotheses aggregate conflicting,
    provenance-bound evidence through replaceable policy while null evidence stays neutral.
  - Paths compared: local hard-coded `hypotheses.py`; bounded-general epistemics
    seam; new architectural subsystem.
  - Selected level and owner: bounded-general `epistemics.py`, reusing
    `records.py` for canonical state and `hypotheses.py` only as compatibility adapter.
  - Protected-capability result: exact subject/snapshot/provenance, invalid-run
    neutrality, public low-level APIs, and legacy scalar outputs preserved by tests.
  - Rejected alternatives: the local path would leave Claim aggregation absent;
    a larger reasoner/store/workflow subsystem would be speculative Block 6–10 work.
  - Tradeoffs and uncertainty: one linear reference policy and strict single-snapshot
    aggregation are deliberate; Bayesian/domain policies remain replaceable implementations.
  - Frozen-candidate proof: commit `a585aa5370dc6ece38c8bc1f0b6a89d6c389b609`,
    candidate root above, `71 passed`, and accepted independent behavioral review.
- Retained open work: none within Block 3.
- Decision/continuation posture: not applicable; Block 4 is dependency-safe.
- Post-block audit: accepted; no metric, trial, persistence, reasoner, or workflow
  implementation crossed the Block 3 Stop.
- Git durability: implementation commit `a585aa5370dc6ece38c8bc1f0b6a89d6c389b609`
  was pushed non-force to `origin/codex/block-03-epistemics`; this evidence-only
  successor is the final Block 3 tracker checkpoint.

### Stop

Stop before generic metric, trial, and experiment execution semantics.

## Block 4 — Generic experiments, measurements, metrics, and evaluation

Status: `accepted`

### Objective

Represent domain-neutral experiments and deterministic evaluation beyond command success.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: explicit metrics, trials, validity, repeated measurement, baselines, candidates, and decision rules.
- Potential capability loss or regression: overgeneralization could turn libRSI into an experiment-tracking platform or break command exactness.
- Protected-capability effect: exact specs/input correlation and invalid-run neutrality remain intact.
- Architecture and operating-model effect: commands become one adapter over experiment ontology; external backends may execute/project without owning interpretation.
- Tradeoff and source evidence: architecture contract sections 2, 6, and 9 plus scope revision Block 4; ship semantics, not dashboards or registries.

### Inputs and dependencies

- Blocks 1 and 3; Block 2 command compatibility contract.

### Required work

- Implement `Metric`, `Measurement`, `Trial`, dispositions, decision rules, and experiment evaluation.
- Support baseline/candidate, repetitions, validity requirements, seeds, budgets, and minimum meaningful effects.
- Adapt current command execution to the generic spec without changing exact argv/cwd behavior.

### Scope and non-goals

- In scope: experiment ontology and deterministic evaluation.
- Not in scope: MLOps, dashboards, model/artifact registries, or generic backend infrastructure.

### Deliverables and recorded state

- Generic records/policies, command adapter, public exports, focused tests, and backend projection protocol if acceptance requires it.

### Resource and economy contract

Use small deterministic trial matrices; widen only when a supported metric/validity edge fails. No external experiment service is required.

### QA and independent review

Review criterion identity, invalid versus negative outcomes, repeated-trial semantics, and command compatibility before mapped validation.

### Acceptance

- Claims can be tested without candidate changes; repeated trials remain distinct; invalid trials do not count negative; baseline/candidate and required metric directions work; external execution can preserve canonical identity.

### Negative tests

- Reject malformed metrics, non-finite measurements, invalid decision rules, mixed spec/result identity, and passing execution that violates a guardrail.

### Completion evidence

- Repository commit: `49f2aac134c2891e16caaf9da6b3e6448eedbb36`.
- External/domain revision or root: not applicable; Block 4 is a deterministic
  experiment-semantics boundary with no external experiment service.
- Inputs: authoritative base `2e74e21429b50a68216f829f4d1fd75a1df69ccf`,
  accepted Blocks 1–3, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: canonical `Metric`, `DecisionRule`, extended `ExperimentSpec`, `Trial`,
  `Measurement`, and `TrialResult` records; `src/librsi/evaluation.py`; the
  command-experiment adapter; public exports/composition; and
  `tests/test_block4_evaluation.py`.
- Focused validation: Python 3.12 focused Block 4 suite, `24 passed`; command and
  `0.2.0` compatibility tests remained green in the full suite.
- Mapped validation: Python 3.12 Ruff and format checks passed; mypy passed all
  17 source files; full suite `95 passed` at `91.57%` branch coverage; sdist/wheel
  build and isolated installed-wheel import smoke passed.
- Candidate freeze: content root
  `e73ea466ed86945fedc786c7a3dc40829cf6604d9fce9a4969acf8b219e33acc`
  remained unchanged through mapped validation and final independent review.
- Remediation closure: four read-only review rounds found and rechecked exactness
  gaps. Evidence projection now replays exact trial results; every result uses the
  deterministic prepared-trial root and concrete trial/snapshot-bound observations;
  impossible valid-count rules and incomplete trial rosters fail closed; invalid
  observations cannot be declared valid; and neutral results retain provenance
  validation while remaining neutral in scoring.
- Resource posture: small deterministic in-memory matrices only; no subprocess was
  executed by the generic evaluator and no provider, database, hosted model,
  registry, dashboard, or external experiment service was used.
- Independent review: Hubble, read-only, against base
  `2e74e21429b50a68216f829f4d1fd75a1df69ccf` and the final frozen candidate root;
  final disposition `accepted` with no material findings.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 4,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: Claims and Hypotheses now support exact,
    repeated, validity-aware measurement against frozen metrics and decision rules,
    while command argv/cwd identity and invalid-run neutrality remain intact.
  - Paths compared: command-only expansion in `experiments.py`; bounded-general
    records plus evaluator and command adapter; experiment-platform subsystem.
  - Selected level and owner: bounded-general `evaluation.py`, canonical state in
    `records.py`, and `experiments.py` retained as the command-specific adapter.
  - Protected-capability result: spec/rule/trial/result/provenance identity,
    complete trial accounting, guardrail failure, external projection, and legacy
    command behavior are covered by focused and compatibility tests.
  - Rejected alternatives: the local path would keep non-command hypothesis tests
    impossible; a platform path would add speculative MLOps, backend, dashboard,
    registry, and persistence concerns owned by later blocks or explicit non-goals.
  - Tradeoffs and uncertainty: mean aggregation and deterministic threshold or
    baseline-delta rules are the reference semantics; richer statistical policies
    remain replaceable future implementations rather than implicit behavior.
  - Frozen-candidate proof: commit
    `49f2aac134c2891e16caaf9da6b3e6448eedbb36`, candidate root above, `95 passed`,
    and accepted independent adversarial review.
- Retained open work: none within Block 4.
- Decision/continuation posture: not applicable; Block 5 is dependency-safe.
- Post-block audit: accepted; no target currentness, persistence, MLOps, backend,
  dashboard, or registry implementation crossed the Block 4 Stop.
- Git durability: implementation commit
  `49f2aac134c2891e16caaf9da6b3e6448eedbb36` was pushed non-force to
  `origin/codex/block-04-experiment-evaluation`; this evidence-only successor is
  the final Block 4 tracker checkpoint.

### Stop

Stop before target lifecycle/currentness and knowledge persistence.

## Block 5 — Targets, snapshots, multi-component identity, and currentness

Status: `accepted`

### Objective

Represent exact opaque and multi-component targets and check evidence currentness without software-specific fields.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: exact target state for local, remote, mutable, immutable, single-, and multi-component targets.
- Potential capability loss or regression: software examples could leak repository fields into generic records.
- Protected-capability effect: evidence remains bound to exact target snapshots; targets remain distinct from knowledge and intent.
- Architecture and operating-model effect: establishes the target owner used by knowledge, intervention, runtime, and host adapters.
- Tradeoff and source evidence: architecture contract sections 2 and 4 plus scope revision Block 5; include an early non-software sentinel.

### Inputs and dependencies

- Blocks 1 and 4.

### Required work

- Implement target, snapshot, component, capability, comparison, and currentness semantics.
- Add deterministic multi-component and non-software fixtures without Git fields in core records.

### Scope and non-goals

- In scope: semantic target identity/currentness.
- Not in scope: target mutation, knowledge persistence, Git adapters, or a repository platform.

### Deliverables and recorded state

- Target/currentness module, multi-component fixture, non-software sentinel, and focused tests.

### Resource and economy contract

Use compact synthetic targets and exact roots; no repository corpus scan or external target is required.

### QA and independent review

Review domain neutrality and atomic snapshot comparison at the frozen revision.

### Acceptance

- Old evidence cannot appear current; opaque/unmutable and multi-component targets work; non-software currentness uses only generic semantics.

### Negative tests

- Reject duplicate components, mismatched target/snapshot references, partial multi-component comparison, and required Git-specific fields.

### Completion evidence

- Repository commit: `71e59844f8a0021502198ba8f995dec17e01353f`.
- External/domain revision or root: not applicable; Block 5 uses deterministic
  synthetic target records and no external target owner.
- Inputs: authoritative base `1285cb504e37a121442dce85ee2627d1e86af523`,
  accepted Blocks 1 and 4, architecture-contract sections 2 and 4, the early
  domain-neutrality revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: canonical `TargetCapabilities`, `TargetComponent`, composite
  `TargetRef`, complete `TargetSnapshot`, and truthful `TargetComparison` records;
  `src/librsi/targets.py`; public exports/composition; updated module documentation;
  and split behavior/validation test modules.
- Focused validation: Python 3.12 focused Block 5 suite, `17 passed`, covering the
  non-software sentinel, opaque target, complete composite snapshots, currentness,
  serialization, direct-construction failures, and tampered input.
- Mapped validation: Python 3.12 Ruff and format checks passed; mypy passed all
  18 source files; full suite `112 passed` at `92.18%` branch coverage; sdist/wheel
  build and isolated installed-wheel import smoke passed.
- Candidate freeze: content root
  `b334d47bb834303193a1cc8e5f5f6f3d15aa8448efd457656b0dc084de7fc0ec`
  remained unchanged through mapped validation and final independent review.
- Remediation closure: independent review found Python Boolean/integer equality
  could admit numeric component-currentness maps. Canonical comparison records now
  require exact Boolean values, with direct-construction and tampered-serialization
  regression proof; the reviewer rechecked and accepted the successor root.
- Resource posture: compact in-memory simulation, process, document, physical-system,
  configuration, and opaque-target fixtures only; no repository scan, database,
  subprocess, provider, target mutation, or external target operation.
- Independent review: Hubble, read-only, against base
  `1285cb504e37a121442dce85ee2627d1e86af523` and the final frozen candidate root;
  final disposition `accepted` with no material findings.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 5,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: exact opaque, atomic, and multi-component target
    state can be compared independently from knowledge, and old evidence cannot be
    promoted as current.
  - Paths compared: another local epistemics snapshot-root check; bounded-general
    target records plus a currentness owner; target registry/adapter/mutation platform.
  - Selected level and owner: bounded-general `targets.py`, reusing `records.py` for
    canonical topology and leaving epistemics as a consumer of target snapshots.
  - Protected-capability result: default target identity, lossless serialization,
    complete component accounting, deterministic ordering, and non-software use with
    no required Git/repository fields are preserved by focused and compatibility tests.
  - Rejected alternatives: the local path would omit target composition and atomic
    comparison; the platform path would cross into host adapters, registries, mutation,
    application, and persistence owned by later Blocks.
  - Tradeoffs and uncertainty: currentness is deliberately exact-root equality and
    capability availability is declarative only; semantic equivalence and capability
    execution require explicit future policy rather than implicit heuristics.
  - Frozen-candidate proof: commit
    `71e59844f8a0021502198ba8f995dec17e01353f`, candidate root above, `112 passed`,
    and accepted independent adversarial review.
- Retained open work: none within Block 5.
- Decision/continuation posture: not applicable; Block 6 is dependency-safe.
- Post-block audit: accepted; no target mutation, knowledge persistence, Git adapter,
  repository platform, or host capability execution crossed the Block 5 Stop.
- Git durability: implementation commit
  `71e59844f8a0021502198ba8f995dec17e01353f` was pushed non-force to
  `origin/codex/block-05-target-currentness`; this evidence-only successor is the
  final Block 5 tracker checkpoint.

### Stop

Stop before persistent knowledge storage or target application.

## Block 6 — Persistent knowledge and `KnowledgeStore`

Status: `accepted`

### Objective

Persist and retrieve reusable epistemic state with explicit target currentness, independently of runtime state.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: valid knowledge can be reused across runs while stale evidence remains queryable but noncurrent.
- Potential capability loss or regression: storage may become a second semantic authority or grow into a generic data platform.
- Protected-capability effect: canonical record roots and target currentness govern storage/retrieval.
- Architecture and operating-model effect: introduces a protocol plus minimal SQLite reference backend separate from runtime persistence.
- Tradeoff and source evidence: architecture contract sections 6 and 8 plus scope revision Block 6; no vector DB, graph platform, or dashboard.

### Inputs and dependencies

- Blocks 1 and 5.

### Required work

- Define `KnowledgeStore` persistence/query contracts for canonical knowledge records and relationships.
- Implement minimal transactional SQLite storage, deterministic reconstruction, filters, lineage, and currentness-aware retrieval.

### Scope and non-goals

- In scope: semantic knowledge storage/retrieval and SQLite reference implementation.
- Not in scope: runtime event state, analytics, embeddings, vector search, or hosted database operations.

### Deliverables and recorded state

- Knowledge protocol, SQLite backend/migrations, query/currentness tests, and backend substitution contract.

### Resource and economy contract

Use bounded temporary databases and batched fixtures; test one current and one stale lineage before mapped suite.

### QA and independent review

Review transactionality, reconstruction, currentness, schema migration, and separation from runtime state.

### Acceptance

- A second run can reuse current knowledge; stale knowledge remains labeled/queryable; SQLite needs no external service; another backend can satisfy the protocol.

### Negative tests

- Reject root/type tampering, cross-target currentness leakage, partial writes, duplicate semantic rows with divergent bytes, and runtime-state masquerading as knowledge.

### Completion evidence

- Repository commit: `0b1d43dfe468fea4265858e77dc081aa9c671c71`.
- External/domain revision or root: not applicable; Block 6 uses bounded temporary
  SQLite databases and no hosted database, external target, or runtime-state owner.
- Inputs: authoritative base `dedadd152039a2840c4204123a4040922bdc40d2`,
  accepted Blocks 1 and 5, architecture-contract sections 6 and 8, the KnowledgeStore
  scope revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: canonical `KnowledgeRelationship`; backend-neutral `KnowledgeStore`,
  `KnowledgeWrite`, `KnowledgeQuery`, `StoredKnowledge`, and currentness semantics;
  an exact rollback-safe SQLite schema/migration owner; a thin SQLite store backend;
  public exports and truthful module documentation; and split contract, behavior,
  integrity, and adversarial test modules.
- Focused validation: Python 3.13 focused Block 6 suite, `34 passed`, covering
  cross-run reuse, current/stale/unbound/incomparable retrieval, exact filters and
  relationships, backend substitution, schema migration, transaction rollback,
  resource closure, and raw-database tampering.
- Mapped validation: Python 3.13 Ruff and format checks passed; mypy passed all
  21 source files; full suite `146 passed` at `92.72%` branch coverage with
  `ResourceWarning` treated as error; sdist/wheel build and isolated installed-wheel
  SQLite knowledge smoke passed.
- Candidate freeze: content root
  `179bfbea82bdfd2107f6cab2d80ce5a61fbafe5430bd06c8d34a5f886114b09a`
  remained unchanged through final mapped validation and independent review.
- Remediation closure: three read-only review rounds found and rechecked two
  fail-closed defects and one successor edge. The complete owned v1 schema now
  validates inside a rollback boundary before version commit, reconstruction occurs
  before write commit, auxiliary projections cannot override canonical records, and
  SQL normalization preserves quoted literal bytes so case-altered `strftime`
  defaults fail during construction.
- Resource posture: compact in-memory and temporary-file SQLite fixtures only;
  no hosted service, provider, subprocess experiment, vector/graph platform,
  analytics system, external target effect, or runtime lifecycle state was used.
- Independent review: Hubble, read-only, against base
  `dedadd152039a2840c4204123a4040922bdc40d2` and the final frozen candidate root;
  final disposition `accepted` with both predecessor findings closed and no material
  successor findings.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 6,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: canonical knowledge can be reused across runs
    while stale target-bound state stays queryable and cannot appear current.
  - Paths compared: an in-memory local dictionary; a bounded-general KnowledgeStore
    contract with a thin SQLite reference; a vector, graph, analytics, or registry
    platform.
  - Selected level and owner: bounded-general `knowledge.py` contracts, exact schema
    ownership in `sqlite_schema.py`, and persistence behavior in
    `sqlite_knowledge.py`; canonical semantics remain in records/currentness owners.
  - Protected-capability result: exact roots, typed references, deterministic
    reconstruction, conservative target currentness, runtime separation, base-install
    zero dependencies, and replaceable backend composition are covered by focused and
    installed-wheel proof.
  - Rejected alternatives: an in-memory dictionary would not satisfy cross-run reuse
    or migration; a database platform would add speculative search, analytics,
    service, and registry authority explicitly excluded by the Block.
  - Tradeoffs and uncertainty: the reference backend validates all persisted
    projections and filters reconstructed canonical records for fail-closed semantics;
    exact schema v1 is deliberately strict, while indexed scale and richer backends
    remain replaceable implementations rather than core authority.
  - Frozen-candidate proof: commit
    `0b1d43dfe468fea4265858e77dc081aa9c671c71`, candidate root above, `146 passed`,
    installed-wheel reuse proof, and accepted independent adversarial review.
- Retained open work: none within Block 6.
- Decision/continuation posture: not applicable; Block 7 is dependency-safe.
- Post-block audit: accepted; no durable Run/Event/Action lifecycle, target mutation,
  hosted database, vector/analytics platform, or kernel-opened storage crossed the
  Block 6 Stop.
- Git durability: implementation commit
  `0b1d43dfe468fea4265858e77dc081aa9c671c71` was pushed non-force to
  `origin/codex/block-06-knowledge-store`; this evidence-only successor is the final
  Block 6 tracker checkpoint.

### Stop

Stop before durable run/event/action lifecycle implementation.

## Block 7 — Durable semantic Run/Event/State/Action engine

Status: `accepted`

### Objective

Provide one replayable, resumable, idempotent semantic runtime for every control plane.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: runs survive interruption and correlate exact actions/results through deterministic transitions.
- Potential capability loss or regression: runtime code could become a generic orchestrator or duplicate knowledge authority.
- Protected-capability effect: canonical records, budgets, failure classification, and authority state remain explicit and replayable.
- Architecture and operating-model effect: adds pure state transitions plus append-only/materialized SQLite durability.
- Tradeoff and source evidence: architecture contract sections 3 and 8 plus scope revision Block 7; no distributed worker, messaging, or tracing platform.

### Inputs and dependencies

- Blocks 1 and 6.

### Required work

- Implement Run, State, Event, Action, ActionResult, Transition, budgets, failure classes, and terminal outcomes.
- Implement pure `step` semantics, append-only events, materialized state, replay, resume, duplicate submission protection, and SQLite durability.

### Scope and non-goals

- In scope: authoritative semantic runtime and reference durability.
- Not in scope: generic task scheduling, worker fleets, provider execution, transports, or agent messaging.

### Deliverables and recorded state

- Runtime records/state machine/store, replay fixtures, interruption dogfood, and transition tests.

### Resource and economy contract

Use bounded transition traces and temporary SQLite; test pure state first, then durability/replay. No live workers.

### QA and independent review

Review event authority, transition validity, duplicate/idempotent submission, replay equivalence, and knowledge/runtime separation.

### Acceptance

- A run resumes after every transition; replay yields the same state; duplicate results cannot double-apply; invalid transitions fail closed; budgets and terminal states are explicit.

### Negative tests

- Reject stale/wrong action results, event gaps/reordering, terminal-state mutation, budget bypass, and conversational prose as lifecycle authority.

### Completion evidence

- Repository commit: `fc2a65b844d84e559d35ee2e00de2079d30e2d78`.
- External/domain revision or root: not applicable; Block 7 uses pure bounded traces
  and temporary SQLite databases, with no provider, worker, hosted store, external
  target, or capability execution.
- Inputs: authoritative base `780158c0249cdc116bd8af0e62f9bdf99c6d0473`,
  accepted Blocks 1 and 6, architecture-contract sections 3 and 8, the durable
  runtime scope revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: structured `librsi.runtime` records, budgets, failure classes, and terminal
  outcomes; pure deterministic request/result/complete/fail/cancel transitions;
  step and full-trace replay APIs; a replaceable `RuntimeStore` contract; an exact,
  rollback-safe, independently versioned SQLite runtime schema; append-only events,
  replay-checked materialized state, resume, and duplicate-transition protection;
  public exports and truthful package documentation; and split record, engine, store,
  and SQLite-integrity tests.
- Focused validation: Python 3.14 focused Block 7 suite, `38 passed`, covering resume
  after every transition, replay equivalence, exact duplicate result and transition
  no-ops, stale/wrong/divergent result rejection, terminal mutation, bound/unbound
  outcome correlation, action/failure/retry/resource budgets, multi-pending reservation
  accounting, alternative store substitution, migration rollback, raw tampering,
  same-file knowledge/runtime coexistence, and interruption rollback. The combined
  protected Blocks 6–7 suite passed `72` tests.
- Mapped validation: Python 3.14 Ruff and format checks passed; mypy passed all
  28 source files; full suite `184 passed` at `90.33%` branch coverage with
  `ResourceWarning` treated as error; sdist/wheel build and isolated Python 3.11
  installed-wheel runtime/SQLite resume and multi-pending budget smokes passed.
- Candidate freeze: content root
  `d4ca331ec1b317ab214bcf479b23d380632cde569e1819c3ad2b153f7c66edd0`
  remained unchanged through final mapped validation and accepted independent review;
  exactly 18 candidate files were included and unrelated untracked `uv.lock` was
  excluded and left untouched.
- Remediation closure: three read-only review rounds found and rechecked three
  fail-closed semantic edges. Exact failed, cancelled, and later-completed result
  resubmissions now remain idempotent after terminalization while divergent or unseen
  terminal submissions reject; all terminal outcomes match the run's exact intent and
  target snapshot; and successful results cannot make actual resource usage plus
  remaining pending reservations exceed a run budget.
- Resource posture: immutable bounded traces, in-memory/temporary-file SQLite, and one
  isolated installed-wheel environment only; no live worker, scheduler, provider,
  model, target mutation, subprocess experiment, transport, messaging, tracing, or
  automatic dispatch system was used or introduced.
- Independent review: Hubble, read-only, against base
  `780158c0249cdc116bd8af0e62f9bdf99c6d0473` and the final frozen candidate root;
  final disposition `accepted`, all three predecessor findings closed, no material
  successor findings, Block 6 protected, and the Block 7 Stop compliant.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 7,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: one control-plane-neutral semantic run can survive
    interruption, reject stale or duplicate authority, account for explicit budgets,
    and reconstruct exactly from its append-only event prefix.
  - Paths compared: a local mutable run object; a bounded-general pure runtime plus
    replaceable durable store; and a workflow, worker, scheduling, messaging, or
    orchestration platform.
  - Selected level and owner: canonical lifecycle records in `runtime/records.py`,
    pure authority transitions in `runtime/engine.py`, backend-neutral persistence in
    `runtime/store.py`, and thin exact SQLite ownership in `runtime/sqlite_schema.py`
    and `runtime/sqlite.py`.
  - Protected-capability result: canonical record identity, exact intent/target
    binding, deterministic replay, explicit terminal outcomes and budgets, append-only
    durability, knowledge/runtime separation, zero base dependencies, and structured
    wheel packaging are covered by focused, mapped, and installed-wheel proof.
  - Rejected alternatives: a mutable local object cannot resume or prove replay; a
    general orchestrator would add speculative dispatch, worker, scheduling,
    messaging, transport, provider, and tracing authority reserved for later Blocks or
    permanently host-owned infrastructure.
  - Tradeoffs and uncertainty: the SQLite reference validates the entire bounded
    history and materialized projection on every resume for fail-closed semantics;
    indexed scale, compaction, distributed coordination, and richer stores remain
    replaceable backend concerns rather than Block 7 core authority.
  - Frozen-candidate proof: commit
    `fc2a65b844d84e559d35ee2e00de2079d30e2d78`, candidate root above, `184 passed`,
    installed-wheel replay/resume proof, and accepted independent adversarial review.
- Retained open work: none within Block 7.
- Decision/continuation posture: not applicable; Block 8 is dependency-safe.
- Post-block audit: accepted; no capability resolution, automatic dispatch, provider
  execution, worker fleet, generic scheduler, transport, messaging, or tracing crossed
  the Block 7 Stop.
- Git durability: implementation commit
  `fc2a65b844d84e559d35ee2e00de2079d30e2d78` was pushed non-force to
  `origin/codex/block-07-runtime`; this evidence-only successor is the final Block 7
  tracker checkpoint.

### Stop

Stop before capability resolution and automatic dispatch.

## Block 8 — Capability protocols and control-plane-neutral dispatch

Status: `accepted`

### Objective

Drive the same runtime through automatic, external, or hybrid capability execution without semantic divergence.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: granular replaceable capabilities and structured pending actions for missing authority.
- Potential capability loss or regression: a dispatcher or optimizer could become a second lifecycle/selection authority.
- Protected-capability effect: action/result/state equivalence and explicit automatic/external/human-reserved/unavailable postures.
- Architecture and operating-model effect: capabilities implement actions while the Block 7 runtime remains authoritative.
- Tradeoff and source evidence: architecture contract sections 3 and 5 plus scope revision Block 8; one object may implement several protocols without a monolith.

### Inputs and dependencies

- Block 7, with Block 5 non-software target fixture.

### Required work

- Define Inspector, Retriever, Reasoner, Experimenter, Implementer, Reviewer, Applier, and Verifier protocols.
- Implement capability resolution/dispatch and external `next/submit` equivalence.
- Exercise one capability against the non-software sentinel.

### Scope and non-goals

- In scope: capability contracts, availability/authority, and deterministic dispatch.
- Not in scope: provider adapters, optimizer algorithms, distributed orchestration, or authoritative selection/application decisions.

### Deliverables and recorded state

- Capability module, dispatcher, managed/external/hybrid equivalence tests, and non-software dogfood.

### Resource and economy contract

Use deterministic fake capabilities and bounded action traces; no provider or process execution is required.

### QA and independent review

Review authority boundaries, equivalent state roots across modes, and absence of domain/provider types in core protocols.

### Acceptance

- Semantically equivalent results yield equivalent state in all modes; missing capabilities return structured actions; capability presence never grants epistemic/application authority.

### Negative tests

- Reject mismatched result schemas, unavailable capability auto-execution, human-reserved dispatch, domain leakage, and dispatcher lifecycle mutation outside runtime transitions.

### Completion evidence

- Repository commit: `5f2e1ef7b6e071f88f5c8be82ab06741292abecc`.
- External/domain revision or root: not applicable; Block 8 uses deterministic fake
  capability objects and bounded immutable traces, with no provider, process, target
  mutation, network, worker, or hosted service.
- Inputs: authoritative base `5c995aec534867acd228a4ea1949e7277c284570`,
  accepted Blocks 5 and 7, architecture-contract sections 3 and 5, the capability
  scope revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: structured `librsi.capabilities` package; granular Inspector, Retriever,
  Reasoner, Experimenter, Implementer, Reviewer, Applier, and Verifier protocols;
  explicit action-kind routes and automatic, external, human-reserved, and unavailable
  resolutions; deterministic provider registry; pure pending-action plans; one-frontier
  automatic dispatch; external and explicit reserved-authority submission through the
  Block 7 engine; public exports and truthful documentation; and split contract,
  equivalence, authority, and non-software dogfood tests.
- Focused validation: Python 3.14 focused Block 8 suite, `18 passed`, covering all
  protocols, one object implementing multiple protocols, exact route validation,
  missing route/provider resolution, managed/external/hybrid state equivalence,
  explicit external/human/unavailable authority, wrong schemas/actions and raised
  implementations, terminal frontier stopping, non-promotion of successful capability
  results, and the synthetic heat-treatment process sentinel. The combined protected
  Blocks 6–8 suite passed `90` tests.
- Mapped validation: Python 3.14 Ruff and format checks passed; mypy passed all
  33 source files; full suite `202 passed` at `90.62%` branch coverage with
  `ResourceWarning` treated as error; sdist/wheel build included the structured
  capabilities and runtime packages; isolated Python 3.11 installed-wheel automatic
  dispatch smoke passed.
- Candidate freeze: content root
  `3561fe619586f4560b9dd64c9b9f452a488ad8df836481ef411c64a4246c4dd6`
  remained unchanged through final mapped validation and independent review; exactly
  13 candidate files were included and unrelated untracked `uv.lock` was excluded and
  left untouched.
- Resource posture: deterministic in-memory fake capabilities, bounded action traces,
  one synthetic non-software snapshot, and an isolated installed-wheel environment;
  no model/provider SDK, subprocess, target effect, optimizer, scheduler, worker,
  transport, messaging bus, tracing platform, or workflow engine was used or added.
- Independent review: Hubble, read-only, against base
  `5c995aec534867acd228a4ea1949e7277c284570` and the frozen candidate root; final
  disposition `accepted` with no material findings, independent adversarial probes
  passed, Blocks 6–7 protected, successor seams clean, and the Block 8 Stop compliant.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 8,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: the same exact pending actions and results can be
    driven automatically, externally, or in hybrid mode without creating a second
    lifecycle, epistemic, selection, or application authority.
  - Paths compared: hard-coded execution inside the runtime; a bounded-general set of
    granular capability protocols plus neutral dispatcher; and a provider, optimizer,
    worker, scheduling, messaging, tracing, or orchestration platform.
  - Selected level and owner: structural host contracts in
    `capabilities/protocols.py`, explicit routing views in `capabilities/records.py`,
    deterministic implementation lookup in `capabilities/registry.py`, and dispatch
    convenience in `capabilities/dispatcher.py`; all state mutation remains owned by
    `RuntimeEngine.submit`.
  - Protected-capability result: identical state/transition semantics across modes,
    explicit missing and reserved authority, exact action/result correlation, terminal
    frontier safety, non-software neutrality, knowledge non-promotion, base-install
    zero dependencies, and structured packaging are covered by focused and mapped proof.
  - Rejected alternatives: embedding execution in the runtime would couple hosts and
    control planes; a general execution platform would add speculative providers,
    optimizers, workers, scheduling, transport, messaging, and tracing explicitly
    outside this Block and mostly outside libRSI ownership.
  - Tradeoffs and uncertainty: one `advance()` call executes only the currently
    automatic frontier in canonical pending order; callers explicitly repeat frontiers
    or submit external/reserved results, preserving boundedness and avoiding a hidden
    scheduler. Provider-specific schemas and structured reasoning remain later seams.
  - Frozen-candidate proof: commit
    `5f2e1ef7b6e071f88f5c8be82ab06741292abecc`, candidate root above, `202 passed`,
    installed-wheel dispatch proof, and accepted independent adversarial review.
- Retained open work: none within Block 8.
- Decision/continuation posture: not applicable; Block 9 is dependency-safe.
- Post-block audit: accepted; no reasoner implementation, composed workflow, provider
  adapter, optimizer, worker/scheduler, transport, messaging, or tracing platform
  crossed the Block 8 Stop.
- Git durability: implementation commit
  `5f2e1ef7b6e071f88f5c8be82ab06741292abecc` was pushed non-force to
  `origin/codex/block-08-capability-dispatch`; this evidence-only successor is the
  final Block 8 tracker checkpoint.

### Stop

Stop before structured reasoning implementations or composed workflows.

## Block 9 — Provider-neutral reasoner contract and structured reasoning

Status: `accepted`

### Objective

Represent cognitive work as validated proposals without making a model or external agent an epistemic authority.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: provider-neutral reflection, hypothesis, experiment-design, explanation, intervention, decomposition, and revision requests/results.
- Potential capability loss or regression: free-form narration could bypass typed validation or promote claims directly.
- Protected-capability effect: exact provenance/currentness and proposal-versus-authority separation remain explicit.
- Architecture and operating-model effect: reasoners become capability implementations usable by managed and external-host modes.
- Tradeoff and source evidence: architecture contract sections 5 and 9 plus scope revision Block 9; optional optimizers stay behind proposal contracts.

### Inputs and dependencies

- Blocks 3, 7, and 8.

### Required work

- Define typed reasoning requests/results and validation for each supported reasoning kind.
- Map managed and externally supplied responses through the same ActionResult transition path.
- Retain lineage from inputs and reasoner proposal to later evidence or intervention decisions.

### Scope and non-goals

- In scope: structured reasoning semantics and capability boundary.
- Not in scope: a hosted provider adapter, prompt optimizer, agent framework, or truth promotion.

### Deliverables and recorded state

- Reasoning records/protocols/validators, external-host fixture, malformed-response regressions, and public exports.

### Resource and economy contract

Use deterministic fake reasoners; no live model call is required. Batch request-kind validation in one fixture matrix.

### QA and independent review

Review proposal authority, schema validation, provenance, and managed/external equivalence.

### Acceptance

- No provider type leaks into core; an external host can complete reasoning without an SDK; malformed output cannot corrupt state; narration cannot validate a claim.

### Negative tests

- Reject stale/mismatched requests, unsupported result kinds, missing lineage, malformed structured payloads, and direct knowledge promotion.

### Completion evidence

- Repository commit: `e6f3a3cebffa2b23233487994f4ea7283a658c3b`.
- External/domain revision or root: not applicable; Block 9 uses deterministic fake
  reasoners, exact immutable records, and bounded in-memory action traces, with no live
  provider, model call, target mutation, process execution, network, worker, or hosted
  service.
- Inputs: authoritative base `fdeed6986923ae2ca75959281dcbff98751b262d`,
  accepted Blocks 3, 7, and 8, architecture-contract sections 5 and 9, the Block 9
  scope revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: structured `librsi.reasoning` package split across strict per-kind schemas,
  canonical request/result records, exact runtime action/result codecs, a provider-free
  backend protocol and managed Reasoner adapter, pre-transition result validation, and
  downstream Evidence/Intervention lineage guards; additive action-kind result
  validators in the generic capability registry; public exports and truthful module
  documentation; and split record, dispatch, lineage, and adversarial tests.
- Focused validation: Python 3.14 focused Block 9 suite, `39 passed`, covering all seven
  reasoning kinds, strict malformed-schema matrices, canonical serialization, exact
  request/input/currentness binding, managed/external transition equivalence, stale and
  mismatched requests, external and managed malformed responses, direct claim/evidence
  promotion, failure shapes, non-authoritative narration, complete downstream lineage,
  wrong-family routes, and malicious no-op host validators. The combined protected
  Blocks 6–9 suite passed `129` tests.
- Mapped validation: Python 3.14 Ruff and format checks passed; mypy passed all 39 source
  files; full suite `241 passed` at `90.92%` branch coverage with `ResourceWarning`
  treated as error; rebuilt sdist/wheel each contained all six structured reasoning
  modules; isolated Python 3.11 installed-wheel proof confirmed that libRSI's canonical
  validator rejects free-form output even when an additive host validator is a no-op.
- Candidate freeze: content root
  `917163618f8293795b6e300e845aeac90058d3828437c3dd3415a2dabdd9cb1e`
  remained unchanged through final mapped validation and independent review; exactly
  18 candidate files were included and unrelated untracked `uv.lock` was excluded and
  left untouched.
- Resource posture: deterministic in-memory fake reasoners, closed JSON-shaped proposal
  fixtures, bounded runtime traces, an isolated build environment, and one installed-
  wheel Python 3.11 environment; no provider/model SDK, prompt optimizer, agent
  framework, subprocess capability, target effect, scheduler, worker, transport,
  messaging, tracing, validation workflow, or investigation workflow was used or added.
- Independent review: Hubble, read-only, against base
  `fdeed6986923ae2ca75959281dcbff98751b262d` and the final frozen candidate root; final
  disposition `accepted`. Review-found gaps allowing optional-validator bypass and
  omission of the exact request root from downstream lineage were remediated and
  independently reprobed; the canonical validator is now nonreplaceable on the reserved
  `reason` path, host validators are additive only, proposal/request/input/currentness
  lineage is complete, Blocks 6–8 remain protected, successor seams are clean, and the
  Block 9 Stop is compliant.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 9,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: managed implementations and SDK-free external hosts
    can perform seven kinds of cognitive work through the same exact runtime action and
    result while every output remains a validated, lineage-bearing proposal rather than
    evidence, truth, knowledge promotion, selection, or application authority.
  - Paths compared: a free-form callback or narration field; a bounded-general package
    of canonical records, closed schemas, codecs, adapters, and validation/lineage
    guards; and a provider SDK, prompt optimizer, agent framework, or composed workflow.
  - Selected level and owner: structural semantics in `reasoning/records.py` and
    `reasoning/schemas.py`, runtime correlation in `reasoning/actions.py`, replaceable
    execution in `reasoning/adapters.py`, and nonreplaceable authority/currentness plus
    downstream provenance in `reasoning/validation.py` and the reserved dispatcher path.
  - Protected-capability result: exact identity/currentness, proposal-versus-authority
    separation, malformed-output atomicity, provider neutrality, external-host parity,
    zero base dependencies, complete request/proposal/input lineage, Block 7 sole state
    mutation, and Block 8 routing equivalence are covered by focused and mapped proof.
  - Rejected alternatives: free-form responses cannot establish a stable validation or
    provenance contract; a provider/optimizer/agent/workflow platform would introduce
    provider types and orchestration authority explicitly outside this Block.
  - Tradeoffs and uncertainty: schemas are deliberately closed and may require explicit
    compatible extension as new reasoning kinds mature; provider metadata may remain
    non-authoritative metadata, while the semantic result identity stays provider-free.
    The exact action kind `reason` is reserved so canonical validation cannot be replaced
    accidentally; custom cognitive actions use distinct kinds and explicit validators.
  - Frozen-candidate proof: implementation commit
    `e6f3a3cebffa2b23233487994f4ea7283a658c3b`, candidate root above, `241 passed`,
    installed-wheel adversarial proof, and accepted independent exact-root review.
- Retained open work: none within Block 9.
- Decision/continuation posture: not applicable; Block 10 is dependency-safe.
- Post-block audit: accepted; no validation/investigation workflow, provider adapter,
  prompt optimizer, agent framework, hosted model integration, candidate generation,
  intervention execution, worker/scheduler, transport, messaging, or tracing platform
  crossed the Block 9 Stop.
- Git durability: implementation commit
  `e6f3a3cebffa2b23233487994f4ea7283a658c3b` was pushed non-force to
  `origin/codex/block-09-structured-reasoning`; this evidence-only successor is the final
  Block 9 tracker checkpoint.

### Stop

Stop before composing validation or investigation workflows.

## Block 10 — First-class validation workflow and `ValidationResult`

Status: `accepted`

### Objective

Validate a claim through current knowledge and evidence-gathering actions without requiring a goal or intervention.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: a useful declarative `validate` workflow with structured supported, contradicted, bounded, and inconclusive outcomes.
- Potential capability loss or regression: workflow convenience could duplicate epistemic/runtime state or assume software tests.
- Protected-capability effect: current evidence is reused, evidence gaps are explicit, and all conclusions cite canonical provenance.
- Architecture and operating-model effect: first vertical composition of targets, knowledge, epistemics, experiments, runtime, capabilities, and workflow-owned outcomes.
- Tradeoff and source evidence: architecture contract sections 10–11 and scope revision Block 10; include an early non-software validation dogfood.

### Inputs and dependencies

- Blocks 3–9 and the Block 5 non-software sentinel.

### Required work

- Implement validation planning, knowledge reuse/currentness, evidence-gap actions, evidence evaluation, claim-state update, and `ValidationResult`.
- Expose low-level stepped and convenience workflow entry points over the same state machine.
- Add deterministic software-neutral and non-software end-to-end validation fixtures.

### Scope and non-goals

- In scope: claim-only validation workflow and result.
- Not in scope: open-ended investigation, candidate generation, intervention, or application.

### Deliverables and recorded state

- Validation workflow/state, result contract, public API, persisted run fixture, and CI dogfoods.

### Resource and economy contract

Check current knowledge before requesting execution; run the smallest evidence plan and stop when sufficiency or budget is reached.

### QA and independent review

Review evidence sufficiency/currentness, workflow/runtime ownership, outcome lineage, and domain neutrality.

### Acceptance

- Validation needs no goal/intervention; sufficient current evidence avoids work; outcome classes remain distinct; provenance is complete; non-software validation uses generic code.

### Negative tests

- Reject stale evidence as current, unsupported success claims, software-only assumptions, duplicate actions, and result synthesis from narrative alone.

### Completion evidence

- Repository commit: `cb51e49f434230316652a43535ecdb0131d7c830`.
- External/domain revision or root: not applicable; Block 10 used canonical immutable
  records, deterministic in-memory and SQLite fixtures, and a synthetic physical-process
  sentinel without live target mutation, provider/model execution, or external service.
- Inputs: authoritative base `7ead49ccd03c15b59ac327e1325ffc0b96b3cdd5`,
  accepted Blocks 3–9, architecture-contract sections 10–11, the Block 10 scope
  revision, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: a structured `librsi.validation` package split across canonical request,
  evidence-batch, progress, update, and result records; action/result codecs and a
  nonreplaceable dispatcher validator; an owned canonical sufficiency policy; and a
  bounded workflow with start, step, submit, resume, managed, and convenience entry
  points over the Block 7 runtime. Knowledge lookup now filters and revalidates exact
  subject, evidence type, validity, and currentness. Public exports and documentation
  describe the store-revalidation contract and the four result dispositions.
- Focused validation: Python 3.14 Block 10 suite, `46 passed`, covering sufficient
  current-knowledge short-circuiting, stale/admissibility filtering, all four outcome
  classes, exact gap planning, bounded multi-frontier work, persisted restart from each
  transition, non-software managed execution, direct/managed/external equivalence,
  canonical result and belief identity, action/result codecs, duplicate rejection,
  narrative non-authority, and pre-effect rejection of forged policy, run, frontier,
  evidence-origin, and intervention-oriented state. The combined protected Blocks 6–10
  suite passed `175` tests.
- Mapped validation: Python 3.14 Ruff and format checks passed; mypy passed all 44 source
  files; the full suite passed `287` tests at `90.61%` branch coverage with
  `ResourceWarning` treated as error. The focused `46` tests passed independently on
  Python 3.11, 3.12, and 3.13. Isolated sdist and wheel builds succeeded, and a fresh
  Python 3.11 environment installed the wheel and completed a generic target-bound
  validation with canonical Run identity and exact evidence provenance.
- Candidate freeze: content root
  `6d573e5fbc5ec40c88b78a637302f8a72aa526c4cae5aa75970393230e426c0d`
  remained unchanged through final mapped validation and independent review; exactly 16
  candidate files were included. The unrelated untracked `uv.lock` was excluded and
  remained untouched at 134,695 bytes with mtime `1787379167`.
- Resource posture: current knowledge is queried before action issuance; one exact gap
  action is pending at a time; execution stops at sufficiency, explicit unavailability,
  failure, or the declared action budget. Tests use bounded fake capabilities, temporary
  SQLite stores, an isolated artifact build, and one installed-wheel environment; no
  intervention, candidate, target application, provider, scheduler, transport, or
  generic workflow platform was introduced.
- Independent review: Hubble, read-only, against base
  `7ead49ccd03c15b59ac327e1325ffc0b96b3cdd5` and each frozen candidate; final
  disposition `accepted` at the root above. Successive adversarial probes found and
  drove remediation of interrupted-state reconstruction, invalid dispatcher evidence,
  incomplete knowledge admissibility/currentness, replaceable Run/belief/result state,
  substituted persisted gaps/outcomes, policy subclass/equality/time-of-check bypasses,
  forged direct progress/evidence origins/run budgets, and managed effects occurring
  before reconciliation. Final direct and managed paths share resume-based canonical
  frontier reconciliation before runtime mutation or any host effect; all earlier
  findings and Blocks 6–9 protections were independently reprobed closed.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 10,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: a caller can now validate one exact claim using
    current reusable knowledge and the smallest bounded evidence plan, receive a
    supported, contradicted, bounded, or inconclusive result, persist and resume the
    run, and choose external or managed collection without changing semantic outcome.
  - Paths compared: a one-shot helper over caller-supplied evidence; the selected
    bounded-general validation package over canonical knowledge, epistemics,
    capabilities, and runtime; and a general workflow/agent engine spanning validation,
    investigation, and intervention.
  - Selected level and owner: identity and outcome semantics in
    `validation/records.py`, canonical sufficiency in `validation/policy.py`, exact
    capability correlation in `validation/actions.py`, and lifecycle composition plus
    restart reconciliation in `validation/workflow.py`.
  - Protected-capability result: currentness, exact evidence provenance,
    reused-versus-gathered origin, invalid-execution neutrality, runtime sole mutation
    authority, provider neutrality, low-level zero-dependency use, external-host parity,
    and software/non-software domain neutrality are covered by focused and mapped proof.
  - Rejected alternatives: a one-shot helper cannot expose or resume evidence gaps and
    would conceal runtime/provenance drift; a general workflow or agent engine would
    duplicate lifecycle authority and prematurely cross the investigation/intervention
    boundary.
  - Tradeoffs and uncertainty: submission with reused evidence must receive the same
    `KnowledgeStore` so exact roots can be revalidated; alternate sufficiency semantics
    require a future versioned policy contract rather than silent injection. This
    explicit discipline is retained to keep validation identity stable.
  - Frozen-candidate proof: implementation commit
    `cb51e49f434230316652a43535ecdb0131d7c830`, candidate root above, `287 passed`,
    installed-wheel validation proof, and accepted independent exact-root review.
- Retained open work: none within Block 10.
- Decision/continuation posture: not applicable; Block 11 is dependency-safe.
- Post-block audit: accepted; no multi-hypothesis investigation, candidate generation,
  intervention proposal/application, hosted provider, optimizer, worker/scheduler,
  transport, messaging, tracing, or second lifecycle/evidence authority crossed the
  Block 10 Stop.
- Git durability: implementation commit
  `cb51e49f434230316652a43535ecdb0131d7c830` was pushed non-force to
  `origin/codex/block-10-validation-workflow`; this evidence-only successor is the final
  Block 10 tracker checkpoint.

### Stop

Stop before multi-hypothesis investigation or intervention generation.

## Block 11 — Investigation and scientific-understanding workflow

Status: `accepted`

### Objective

Investigate a question through competing hypotheses, adaptive experiments, bounded search, and evidence-bound synthesis.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: questions can branch, falsify, refine, and retain unresolved alternatives instead of terminating on one hypothesis.
- Potential capability loss or regression: search heuristics could masquerade as truth or create a duplicate lane/runtime owner.
- Protected-capability effect: portfolio lanes reuse canonical evidence, action, budget, and lineage semantics.
- Architecture and operating-model effect: composes validation and reasoner capabilities into an investigation workflow and `InvestigationResult`.
- Tradeoff and source evidence: architecture contract section 10 and predecessor Block 11; reuse `PortfolioPolicy` before adding scheduling machinery.

### Inputs and dependencies

- Block 10 and the Block 9 reasoner contract.

### Required work

- Implement question state, hypothesis alternatives/lineage, experiment prioritization/redesign, branch retirement, stopping policies, and evidence-bound answer synthesis.
- Reuse sequential/parallel portfolio primitives and canonical runtime budgets.

### Scope and non-goals

- In scope: epistemic investigation and structured result.
- Not in scope: interventions, candidate implementation, generic optimizer algorithms, or application.

### Deliverables and recorded state

- Investigation workflow/result, branch fixtures, inconclusive-redesign dogfood, and public API.

### Resource and economy contract

Reuse existing evidence; cap branches/experiments by declared run budgets; widen only after a concrete surviving alternative requires it.

### QA and independent review

Review branch lineage, falsification behavior, stopping, evidence citations, and absence of search-as-authority.

### Acceptance

- Falsifying one hypothesis leaves viable alternatives; inconclusive evidence can redesign an experiment; runs stop on explicit sufficiency/budget/no-action conditions; conclusions cite evidence.

### Negative tests

- Reject unsupported branch promotion, evidence leakage between hypotheses, endless branch expansion, and conclusion synthesis without current supporting evidence.

### Completion evidence

- Delivered a structured `librsi.investigation` package rather than a monolithic helper:
  `records.py` owns request, complete frontier, branch, experiment-batch, finding, and
  result records; `policy.py` owns canonical hypothesis, portfolio, evidence, budget,
  redesign, retirement, and stopping semantics; `actions.py` owns dedicated reasoner and
  experimenter codecs plus exact pre-transition validation; `workflow.py` owns restartable
  composition over the Block 7 runtime; `__init__.py` exposes the supported public surface.
- Behavioral proof: competing hypotheses begin at a neutral canonical belief, reuse only
  current admissible knowledge with exact provenance, retain isolated evidence, support
  sequential and deterministic parallel lane activation, redesign after inconclusive
  evidence within budget, retire on explicit causes, and project findings only from exact
  supported hypothesis statements and evidence. Direct, managed, persisted, and resumed
  paths share the same action and result semantics.
- Authority proof: experiment proposals use a closed observation-only schema with exact
  built-in strings, bounded measurement identifiers, and criteria derived from the
  canonical epistemic relationship owner. A complete typed `InvestigationFrontier`
  accompanies each specialized action. `derive_investigation_action()` is the single
  authority for branch choice, design-versus-experiment phase, sequence, and budget
  eligibility; public builders, codecs, workflow replay, and failed results require its
  exact output. Generic `CapabilityDispatcher` routes and submissions fail closed for
  investigation actions, leaving `InvestigationWorkflow.submit()` as the sole owner.
- Validation: Ruff formatting/checks and mypy passed. The focused Block 11 suite passed
  `36` tests; the protected Blocks 6–11 suite passed `211`; the full suite passed `323`
  with `90.26%` branch coverage. Isolated sdist and wheel builds succeeded; the wheel
  contained `py.typed` and all five investigation modules. Fresh installed-wheel
  environments passed all `36` focused tests on Python 3.11, 3.12, and 3.13 and imported
  `InvestigationFrontier`, `InvestigationWorkflow`, and `derive_investigation_action`.
- Candidate freeze: content root
  `1655bd50e2eca74731f4ab5d04f442dba142d3e2836c41f92cf3d07144dea7b2`
  remained unchanged through final mapped validation, release proof, and independent
  review; exactly 17 candidate files were included. The unrelated untracked `uv.lock` was
  excluded and remained untouched at 134,695 bytes with mtime `1787379167`.
- Independent review: Hubble, read-only, against base
  `b5fc49873aa61ec6db714f69852338b417a6a8ea` and successive exact frozen candidates; final
  disposition `accepted` at the root above. Adversarial probes found and drove remediation
  of target-change spelling/value/container smuggling, noncanonical provider criteria,
  exact-string subclass spoofing, generic-dispatch prevalidation effects, incomplete or
  altered failure rosters, out-of-order action submission, and full-roster failed-action
  substitution. All reproductions and Blocks 6–10 protections were independently reprobed
  closed; no actionable finding remained.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 11,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: a caller can now investigate one exact question through
    competing falsifiable hypotheses, bounded adaptive observations, current reusable
    evidence, explicit unresolved alternatives, deterministic persistence/resume, and
    evidence-bound findings without granting target-change authority.
  - Paths compared: a single-question one-shot helper; the selected bounded-general
    investigation package composed over Question, Hypothesis, Evidence, ExperimentSpec,
    PortfolioPolicy, reasoner/experimenter capabilities, knowledge, and runtime; and a
    general search/agent/optimizer platform spanning intervention and application.
  - Selected level and owner: semantic state in `investigation/records.py`, canonical
    epistemic/search policy in `investigation/policy.py`, exact capability/action authority
    in `investigation/actions.py`, and lifecycle/replay composition in
    `investigation/workflow.py`.
  - Protected-capability result: evidence currentness and provenance, neutral initial
    belief, portfolio ownership, runtime sole mutation authority, provider neutrality,
    external/managed parity, deterministic replay, and software/non-software neutrality are
    preserved by mapped tests and exact-root review.
  - Rejected alternatives: a one-shot helper cannot preserve competing lanes, bounded
    redesign, persistence, or explicit unresolved state; a general optimizer/agent engine
    would duplicate lifecycle and portfolio authority and prematurely cross the
    intervention/application boundary.
  - Tradeoffs and uncertainty: callers resuming knowledge-backed investigations must supply
    the same `KnowledgeStore` so reused roots can be revalidated. Policy changes require a
    versioned semantic contract rather than injectable heuristics. These constraints retain
    stable identity and fail-closed replay.
  - Frozen-candidate proof: implementation commit
    `f1dc143243b0250b505a24f975315b6e8a7e2502`, candidate root above, `323 passed`,
    installed-wheel Python 3.11/3.12/3.13 proof, and accepted independent exact-root review.
- Resource posture: knowledge reuse precedes new actions; hypothesis, experiment, redesign,
  action, and failure counts remain bounded; one exact action is pending at a time; tests
  use synthetic capabilities, temporary SQLite stores, and temporary build/install
  environments. No provider, worker, scheduler, transport, messaging, filesystem/Git
  effect, or target mutation was added to the library core.
- Retained open work: none within Block 11.
- Decision/continuation posture: not applicable; Block 12 is dependency-safe.
- Post-block audit: accepted; no intervention, candidate, evaluation-contract,
  comparative-selection, application, target-change, hosted provider, generic optimizer,
  worker/scheduler, transport, messaging, tracing, or second runtime/epistemic/portfolio
  owner crossed the Block 11 Stop.
- Git durability: implementation commit
  `f1dc143243b0250b505a24f975315b6e8a7e2502` was pushed non-force to
  `origin/codex/block-11-investigation-workflow`; this evidence-only successor is the final
  Block 11 tracker checkpoint.

### Stop

Stop before proposing or implementing target changes.

## Block 12 — Generic intervention and candidate lifecycle

Status: `accepted`

### Objective

Represent proposed change and prospective candidate state without conflating either with authoritative target application.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: domain-extensible interventions, implementation handoffs, candidates, and exact lineage.
- Potential capability loss or regression: domain payloads could leak into core fields or candidate creation could imply application.
- Protected-capability effect: target currentness, constraints, evidence rationale, and candidate/application separation remain enforced.
- Architecture and operating-model effect: an Implementer capability creates candidates behind a universal semantic envelope.
- Tradeoff and source evidence: architecture contract sections 2 and 10 plus scope revision Block 12; include the non-software sentinel without core schema changes.

### Inputs and dependencies

- Blocks 5 and 11; capability contracts from Block 8.

### Required work

- Implement intervention specification, implementation result, candidate snapshot/lifecycle, evidence rationale, risks, validation plan, and rollback expectations.
- Support absent implementers through complete handoffs and extensible domain payloads.
- Add one non-software intervention/candidate fixture.

### Scope and non-goals

- In scope: proposal-to-candidate semantics and implementation capability boundary.
- Not in scope: comparative selection, authoritative application, or domain-specific implementation engines.

### Deliverables and recorded state

- Intervention/candidate records and policy, Implementer contract integration, handoff schema, and deterministic fixtures.

### Resource and economy contract

Use synthetic implementers/candidates; no external target mutation. Reuse exact target snapshots and evidence roots.

### QA and independent review

Review lineage, extensibility, currentness, absent-capability handoff, and candidate/application separation.

### Acceptance

- Useful interventions can be emitted without an implementer; candidate state differs from authoritative target state; domain payloads need no core modification; lineage is exact.

### Negative tests

- Reject stale-target implementation, candidate without intervention/evidence lineage, domain fields in generic identity, and candidate status promoted to applied.

### Completion evidence

- Capability level selected: the middle structured level—a universal intervention,
  request/result/handoff, candidate-only policy, and restartable workflow. A thin DTO
  handoff would not preserve currentness or lifecycle semantics; a domain execution
  framework would cross the host-effect boundary and was intentionally omitted.
- Material implementation: commit `43aacf0e4900edc98f7a3d392b3a656f3ecae3fc`
  adds the structured `librsi.interventions` package (`records`, `actions`, `policy`,
  and `workflow`), exact Implementer dispatch integration, compatibility projections,
  package documentation, and separated record/action/dispatch/workflow/adversarial
  tests.
- Exact accepted candidate root:
  `4c51c5ecc2d05c5cd08d6d5f23a65125f637f8d5da7e9e7ec188932945da01ad`
  over 18 paths relative to base
  `6f5c3b4c2ccdcda78042371e14c04bbc5375adcb`, excluding the unrelated untracked
  `uv.lock`.
- Independent semantic review: accepted the exact root after verifying canonical
  RuntimeEngine replay across started, waiting, submitted-success, completed, failed,
  cancelled, and retry-budget states; explicit dispatcher currentness before provider
  execution; exact result/failure/outcome settlement; non-software extensibility; and
  the absence of comparison, application, or domain implementation authority.
- Validation: Ruff format/check passed; mypy passed across 54 source files; the focused
  Block 12 suite passed 59 tests; the full suite passed 382 tests at 90.63% branch
  coverage. The built wheel installed independently and passed all 59 focused tests on
  Python 3.11, 3.12, and 3.13.
- Acceptance reconciliation: an intervention can be emitted as a complete serializable
  candidate-only handoff without an Implementer; managed and external implementations
  traverse the same exact action/result/runtime path; stale or unobserved dispatch fails
  before provider invocation; candidate state must differ from the unchanged
  authoritative baseline; domain payloads remain confined to `specification`; and
  evidence, constraints, artifacts, action/result correlation, and lifecycle lineage are
  exact.
- Stop reconciliation: Block 12 introduces no evaluation-contract operationalization,
  candidate comparison/acceptance, target application, or domain-specific engine.

### Stop

Stop before evaluation-contract operationalization, candidate comparison, or application.

## Block 13 — Goals, objectives, constraints, guardrails, and evaluation contracts

Status: `completed`

### Objective

Translate declarative improvement intent into typed measurable evaluation contracts without confusing goals with claims.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: natural-language and typed goals gain explicit metrics, baselines, constraints, guardrails, and stopping rules.
- Potential capability loss or regression: a reasoner could fabricate success criteria or operationalization could become domain-specific.
- Protected-capability effect: typed contracts, exact baselines, and structured need-for-information govern evaluation.
- Architecture and operating-model effect: introduces the intent/evaluation owner consumed by selection and improvement.
- Tradeoff and source evidence: architecture contract sections 2 and 10 plus scope revision Block 13; reasoners propose, typed contracts decide.

### Inputs and dependencies

- Blocks 5 and 12, with metrics from Block 4 and reasoner proposals from Block 9.

### Required work

- Implement Goal, Objective, Constraint, Guardrail, Baseline, EvaluationContract, and operationalization actions/results.
- Support typed minimize/maximize/target/no-regression/must-satisfy semantics and unmeasurable-intent outcomes.

### Scope and non-goals

- In scope: declarative intent and measurable contracts.
- Not in scope: optimizer algorithms, candidate generation, comparative selection, or application.

### Deliverables and recorded state

- Intent/evaluation records/policies, operationalization workflow slice, and typed/natural-language fixtures.

### Resource and economy contract

Use deterministic proposed contracts; no live reasoner required. Stop operationalization when criteria are sufficient or a named fact is missing.

### QA and independent review

Review Goal-versus-Claim separation, baseline identity, guardrail meaning, and proposal authority.

### Acceptance

- Natural-language goals can be operationalized; typed goals remain exact; constraints/stops are explicit; unmeasurable intent yields structured pending action rather than invented criteria.

### Negative tests

- Reject non-finite metrics, missing baselines where required, contradictory constraints, untyped fabricated criteria, and goal treated as evidence.

### Completion evidence

- Capability comparison: rejected a thin prose-to-metrics converter because it would
  let proposed wording become authority; selected the structured middle level with
  exact Goal/Baseline/Objective/Constraint/Guardrail/StoppingRule records and a
  restartable proposal-only operationalization workflow; deferred optimizer/problem-
  modeling machinery to the comparison/search owner in Block 14.
- Added the structured `librsi.intent` package split across records, policy, action
  codecs/validation, and canonical runtime workflow modules. Natural-language and
  typed paths converge on the same `EvaluationContract`; unmeasurable intent returns
  named missing facts, and no contract/result can treat a Goal as Claim or Evidence.
- Added exact minimize/maximize/target objectives, no-regression/must-satisfy
  guardrails, finite baseline values, feasibility/contradiction checks, explicit stop
  rules, stale-currentness gates, pre-mutation proposal-policy validation, managed and
  external dispatch equivalence, runtime replay/resume, and exact duplicate idempotency.
- Added a non-software fermenter fixture and 40 focused tests covering typed and
  proposed operationalization, missing-information outcomes, foreign/stale proposal
  rejection, fabricated criterion subclasses, contradictory objective/guardrail
  ranges, malformed dispatcher results, failure settlement, and divergent duplicates.
- Validation: Ruff and mypy clean; full suite `422 passed` at `90.31%` branch coverage;
  built wheel focused suite `40 passed` on Python 3.11, 3.12, and 3.13.
- Independent review: accepted exact candidate root
  `2c19bbca304dd6c93ce82de733ff0f121051ad33576be7e9576485dc17c8ec01`
  after three adversarial rounds; all authority, feasibility, replay, idempotency, and
  exact-type findings were closed. Implementation commit: `cb6b268`.
- The unrelated untracked `uv.lock` remained excluded and byte/mtime-identical
  (`134695`, `1787379167`). No candidate ranking, selection, optimizer, acceptance, or
  application authority was introduced.

### Stop

Stop before ranking or accepting candidates.

## Block 14 — Comparative evaluation, candidate selection, and search boundary

Status: `completed`

### Objective

Select the evidence-supported candidate, Pareto set, or none through explicit evaluation contracts and guardrails.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: actual baseline/candidate comparison, uncertainty, minimum effects, risk, multi-objective decisions, and none-accepted outcomes.
- Potential capability loss or regression: optimizer output or passing execution could bypass evidence/guardrail semantics.
- Protected-capability effect: independent review remains configurable governance, and selection provenance is exact.
- Architecture and operating-model effect: libRSI owns comparison/acceptance while replaceable search capabilities only propose candidates.
- Tradeoff and source evidence: architecture contract sections 5, 6, and 10 plus scope revision Block 14; do not reimplement mature optimization algorithms.

### Inputs and dependencies

- Blocks 4, 12, and 13.

### Required work

- Implement candidate evaluation/comparison, uncertainty, guardrails, meaningful effect, Pareto representation, risk policy, ranking, and none-accepted decision.
- Define a proposal-only search/candidate-generation capability boundary where needed.

### Scope and non-goals

- In scope: deterministic comparison, selection, and provenance.
- Not in scope: optimizer algorithms, implementation, application, or mandatory independent review for every low-risk case.

### Deliverables and recorded state

- Evaluation/selection records and policy, search protocol boundary, comparison matrices, and regression tests.
- Capability framing: a thin pass/fail or aggregate-score selector was rejected because it would conceal objective, uncertainty, and guardrail semantics. The selected structured level owns typed evidence-bound multi-objective comparison, minimum meaningful effects, explicit uncertainty and risk, Pareto and none-accepted outcomes, and exact selection provenance while keeping candidate generation proposal-only. A full optimizer/search platform was rejected as duplicative and outside this Block's authority.

### Resource and economy contract

Batch candidates through one evaluation contract; reject invalid trials before ranking; widen only for an explicit unresolved objective/guardrail conflict.

### QA and independent review

Review no-regression, none-accepted, uncertainty, Pareto, and proposal-versus-selection authority.

### Acceptance

- Passing commands cannot prove improvement; guardrail failures reject candidates; none accepted is valid; parallel lanes compare through one contract.

### Negative tests

- Reject incomparable baselines, invalid-trial promotion, hidden guardrail violation, opaque aggregate scores, and optimizer self-acceptance.

### Completion evidence

- Accepted exact candidate root: `ab4bc3c176326459eb35f97d9b5d87806a235935eebd7eb574d36d9a9893714e`.
- Implementation commit: `6afbcc9cd4e5f11984bf390c07f0282f6f582694` (`feat: add comparative candidate selection`).
- Independent semantic review: accepted after adversarial reproduction and correction of direct-record authority bypass, reversed ranking/order identity forks, sparse per-metric evidence promotion, and untyped review-governance bypass. The accepted review re-ran all prior probes and found no remaining material Block 14 defect.
- Local validation: Ruff lint and format checks clean; mypy clean across 64 source files; full suite `468 passed` at `90.55%` branch coverage.
- Built-wheel matrix: the focused 46-test Block 14 suite passed from the built wheel on Python 3.11, 3.12, and 3.13.
- Public surface: structured `librsi.comparison` records, policy/statistics, and proposal-only search modules are exported without adding a runtime dependency, optimizer algorithm, application authority, or domain-specific core field.
- Workspace hygiene: the unrelated untracked `uv.lock` remained excluded and byte/mtime-identical (`134695`, `1787379167`).

### Stop

Stop before the complete iterative improvement workflow or authoritative application.

## Block 15 — Complete improvement workflow and `ImprovementResult`

Status: `completed`

### Objective

Compose goals, investigation, interventions, candidates, experiments, and selection into a bounded evidence-driven improvement engine.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: declarative `improve` executes complete iterative search and returns an evidence-backed result or no-useful-improvement outcome.
- Potential capability loss or regression: convenience may hide budgets, fabricate improvement, or hard-code software assumptions.
- Protected-capability effect: exact baselines/currentness, guardrails, failure-driven learning, and application-default-off remain visible.
- Architecture and operating-model effect: first full improvement composition over the shared runtime and workflow-owned outcome substrate.
- Tradeoff and source evidence: architecture contract section 10 and scope revision Block 15; acceptance includes both software-oriented and non-software deterministic dogfoods.

### Inputs and dependencies

- Blocks 10–14 and canonical runtime/capabilities.

### Required work

- Implement operationalize/baseline/investigate/hypothesize/intervene/implement/experiment/select/learn/repeat/stop lifecycle.
- Add iteration, experiment, retry, and resource budgets plus diminishing-return, failure-broadening, and promising-branch narrowing.
- Produce `ImprovementResult` and maintain software-oriented and non-software deterministic end-to-end dogfoods.

### Scope and non-goals

- In scope: improvement through accepted candidate selection and complete application handoff.
- Not in scope: authoritative application, provider infrastructure, or self-change governance.

### Deliverables and recorded state

- Improvement workflow/state/result, declarative and stepped APIs, budget policies, and two cross-domain dogfoods.
- Capability framing selected the structured middle layer: typed records, policy, action codecs, and a restartable workflow that composes the existing operationalization, investigation, intervention, experiment, and comparison authorities. A one-shot facade would conceal lifecycle and budget state; a full optimizer/application orchestrator would exceed this block and collapse host authority into the library.

### Resource and economy contract

Reuse current knowledge and baselines; enforce declared budgets; run focused vertical fixtures before mapped suite; stop on sufficiency, no productive action, or diminishing return.

### QA and independent review

Review whole-loop state transitions, guardrail/selection authority, failure recovery, budget enforcement, and domain neutrality.

### Acceptance

- A synthetic improvement needs no manual policy sequencing; failed candidates return to investigation; falsified hypotheses can be replaced; success and no-improvement results are complete; both domain dogfoods pass.

### Negative tests

- Reject success without baseline/comparison, budget bypass, repeated blind retry, candidate failure reported as hypothesis falsification, and software ontology in generic workflow code.

### Completion evidence

- Accepted exact candidate root: `4f0efff254b18f8cbe25c7010fb2c10814c732cc5dedbe75fe412b06eb7cfa13`.
- Implementation commit: `89b77fbf6b7815222a45997ebe04126c40f43c5f` (`feat: add bounded improvement workflow`).
- Independent semantic review: accepted after repeated adversarial reproduction and correction of action/replay authority splits, retry and aggregate budget bypasses, noncanonical directives, discontinuous predecessor chains, direct-constructor policy bypass, and reintroduction of a historically falsified hypothesis after an intervening cycle. The accepted review replayed the complete lifecycle and found no remaining material Block 15 defect.
- Local validation: Ruff lint and format checks clean; mypy clean across 71 source files; full suite `510 passed` at `90.04%` branch coverage.
- Built-wheel matrix: sdist/wheel build included `py.typed` and all seven structured improvement modules; the focused 42-test Block 15 suite passed from the installed wheel on Python 3.11, 3.12, and 3.13.
- Public surface: typed improvement request/budget/iteration/result records, canonical policy and replay authority, action codecs, declarative `improve`, and restartable stepped workflow are exported without provider, application, self-change, or domain-specific authority.
- Workspace hygiene: the unrelated untracked `uv.lock` remained excluded and byte/mtime-identical (`134695`, `1787379167`).

### Stop

Stop before authoritative target application.

## Block 16 — Application, post-application verification, and rollback

Status: `completed`

### Objective

Apply an accepted candidate only through explicit authority/currentness gates, verify the actual produced target state, and roll back failed outcomes.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: optional authoritative transition, exact post-application verification, rollback, and complete handoff when no Applier exists.
- Potential capability loss or regression: execution success could be mistaken for improvement or application authority could be inferred.
- Protected-capability effect: `apply=False` default, explicit capability authority, target currentness, and evidence/application failure separation.
- Architecture and operating-model effect: separates candidate selection from authoritative target mutation and verification owners.
- Tradeoff and source evidence: architecture contract sections 2 and 10; additional lifecycle complexity prevents unsafe implicit application.

### Inputs and dependencies

- Block 15 and Block 8 Applier/Verifier capability contracts.

### Required work

- Implement proposed-to-verified/rolled-back lifecycle, application request/handoff, currentness preconditions, actual-result snapshot capture, verification, and rollback actions.
- Preserve application/infrastructure failure separately from epistemic evidence.

### Scope and non-goals

- In scope: generic application lifecycle and capability-mediated effects.
- Not in scope: domain-specific deployment systems, automatic external authority, or self-change risk policy.

### Deliverables and recorded state

- Application records/state transitions, handoff schemas, deterministic fake target/applier/verifier/rollback fixtures, and public result fields.
- Capability framing selected the structured middle layer: application-specific typed records, policy, action codecs, canonical replay, and a restartable workflow compose the existing runtime plus `CapabilityRegistry` Applier/Verifier routes. A direct provider call would bypass durable authority/currentness and replay; a deployment orchestrator or new capability registry would duplicate existing owners and exceed this Block.
- Post-application verification reuses the existing comparative-selection authority: the Verifier supplies an exact actual-state `CandidateTrialBatch`, while libRSI derives the `CandidateAssessment` and verified/rejected disposition from the original `EvaluationContract`, guardrails, and `RiskPolicy`. Host booleans and narration have no verification authority.
- The shared runtime remains target-snapshot fixed by default. Application Runs alone declare their exact `ApplicationRequest` as identity-bound same-target transition authority, and successful `Outcome` records retain that authority while naming the produced or restored authoritative snapshot.

### Resource and economy contract

Use disposable synthetic targets; default all mapped tests to `apply=False`; execute mutation/rollback only inside bounded fixtures.

### QA and independent review

Review authority, currentness, actual-produced-state verification, rollback, and evidence classification at the frozen revision.

### Acceptance

- `apply=False` returns a consumable result; compatible Applier supports `apply=True`; failed verification rolls back; application failure is not counterevidence; stale targets reject application.

### Negative tests

- Reject absent/reserved Applier execution, stale application, assumed output snapshots, duplicate apply, verification of the wrong state, and rollback without exact prior state.

### Completion evidence

- Repository implementation commit:
  `743ecee51fc7f08c55bcd990f8d54dffd5ad014e`.
- External/domain revision or root: not applicable; Block 16 uses deterministic
  in-memory targets and fake capability implementations, with no live deployment,
  provider, network, repository mutation, or external authority.
- Inputs: accepted Block 15, the Block 8 Applier/Verifier capability boundary,
  architecture-contract sections 2 and 10, and tracker capability-frame SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: structured `librsi.application` records, action codecs, replay validation,
  comparative verification policy, and restartable workflow; exact application
  requests and handoffs; explicit apply-disabled results; same-target transition
  authority in the shared runtime; actual produced-state receipts; contract-derived
  verification; exact rollback settlement; and public exports and documentation.
- Focused validation: `31 passed` with `93.36%` branch coverage across the application
  package. The protected runtime and v0.2 compatibility set passed `26` tests. Cases
  cover disabled and enabled application, absent or reserved capabilities, stale and
  duplicate requests, exact produced-state capture, wrong-state verification,
  contract-derived acceptance/rejection, verifier infrastructure failure, successful
  and failed rollback, replay, restart, result substitution, missing terminal result,
  application failure classification, ordinary Run snapshot fixation, and explicit
  same-target transition authority.
- Mapped validation: Ruff formatting and lint passed across `src` and `tests`; mypy
  passed all 77 source files; the full suite passed `541` tests at `90.30%` branch
  coverage; sdist/wheel build succeeded and included the complete structured
  application package plus `py.typed`; isolated installed-wheel runs passed the 31
  Block 16 tests on Python 3.11, 3.12, and 3.13.
- Candidate freeze: content root
  `0f568517c6106f545dcec9cbf4cd12d107e23de3ae8c1e4a6e0a96a1b33c13e6`
  remained unchanged through final independent review. Exactly 14 candidate files
  were included; unrelated untracked `uv.lock` was excluded and remained unchanged at
  SHA-256 `ea9a2eb3afc46401f2356ef098e005ec87ac33e27475e43bcd86eb4131ea960e`.
- Resource posture: deterministic in-memory fake target, Applier, Verifier, and
  rollback capabilities; bounded trial batches; isolated build and installed-wheel
  environments; no live target, provider, subprocess capability, deployment system,
  worker, scheduler, transport, or hosted service.
- Independent review: Hubble, read-only, against the exact frozen candidate root;
  final disposition `accepted`. The first review found a host-authoritative boolean
  verifier, stale baseline Outcome identity, and terminal progress-result
  substitution. The corrected candidate removed the boolean authority, derives
  assessment from the original evaluation and risk contracts over the actual produced
  snapshot, binds Outcome to the produced or restored authoritative state, and rejects
  substituted or missing terminal results. Independent probes reconfirmed all three
  corrections plus ordinary-Run fixation, explicit transition authority, currentness,
  replay, and domain neutrality.
- Product-capability review:
  - Trigger: consequential posture.
  - Frame identity: `docs/tracker.md`, Block 16,
    `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
  - Capability added or preserved: a host can consume an apply-disabled handoff or
    perform an explicitly authorized application, while libRSI owns exact currentness,
    actual-state identity, comparative verification semantics, rollback settlement,
    replay, and the separation between operational failure and counterevidence.
  - Paths compared: a direct capability call with a host boolean; the selected
    structured lifecycle composing the existing runtime and capability registry; and a
    deployment/orchestration subsystem. The structured lifecycle was selected because
    it adds the missing durable semantics without duplicating either effect execution
    or workflow ownership.
  - Selected level and owner: immutable identity and lineage in `application/records.py`,
    capability correlation in `application/actions.py`, assessment authority in
    `application/policy.py`, replay in `application/replay.py`, lifecycle settlement in
    `application/workflow.py`, and narrowly explicit same-target transition authority
    in the canonical runtime.
  - Protected-capability result: `apply=False` remains the default; ordinary Runs remain
    snapshot fixed; an Applier cannot claim verification; actual produced snapshots
    cannot be assumed; infrastructure failure is not evidence; and every accepted,
    rejected, restored, or unsettled result names the exact authoritative state.
  - Rejected alternatives: host booleans and narration cannot reproduce evaluation
    contracts or provide epistemic authority; direct calls omit durable
    authority/currentness and replay; a deployment platform exceeds the generic
    library boundary and would duplicate existing host responsibilities.
  - Tradeoffs and uncertainty: authoritative transitions require an additional
    identity-bound Run field and typed lifecycle records. The field is omitted from
    identity data when unset, preserving existing roots, and remains restricted to the
    same target and exact authority lineage. Self-change risk policy remains deferred
    to Block 17.
  - Frozen-candidate proof: implementation commit above, exact candidate root above,
    `541 passed`, isolated installed-wheel proof on three Python versions, and accepted
    independent exact-root review.
- Retained open work: none within Block 16. Meta-target classification and self-change
  governance remain exclusively in Block 17.
- Decision/continuation posture: not applicable; Block 17 is dependency-safe.
- Post-block audit: accepted; no meta-targeting, self-change governance, deployment
  platform, provider integration, hosted execution, or repository automation crossed
  the Block 16 Stop.

### Stop

Stop before meta-targeting or self-change governance.

## Block 17 — Generalized RSI, meta-targeting, and self-change governance

Status: `completed`

### Objective

Use the ordinary improvement machinery against explicitly declared improvement-system targets under stronger activation and rollback governance.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: governed self-change of reasoners, experiment planners, search/aggregation/selection policies, resource allocation, and host machinery.
- Potential capability loss or regression: self-evaluation could authorize itself or weaken future decision quality.
- Protected-capability effect: historical replay, forward shadow, independent evaluation, currentness, activation gates, and rollback are mandatory for configured self-change classes.
- Architecture and operating-model effect: generalizes `SelectorPolicy` through ordinary intervention/candidate/evidence/outcome records rather than a second RSI system.
- Tradeoff and source evidence: architecture contract sections 2 and 10; stronger governance increases cost only for self-affecting targets.

### Inputs and dependencies

- Blocks 7–16 and existing `selector_policies.py` guarantees.

### Required work

- Define explicit meta-target classification and risk/governance policy.
- Generalize historical, shadow, independent review, activation, currentness, and rollback through ordinary records/actions.
- Produce `RSIResult` and deterministic accepted/rejected/rollback self-change fixtures.

### Scope and non-goals

- In scope: self-change semantics and governance composition.
- Not in scope: ungoverned self-modification, a second epistemic/experiment engine, hosted autonomous execution, or release/deployment.

### Deliverables and recorded state

- Meta-target/governance records and policies, workflow integration, result contract, compatibility mapping, and CI dogfoods.
- Capability framing selected a structured composition under `librsi.rsi`: explicit
  meta-target declarations and configured class/risk rules; typed historical,
  forward-shadow, and independent-review commands and derived gates; canonical replay
  and restartable workflow state; an identity-bound activation approval; and an
  `RSIResult` that wraps the ordinary application result. A selector-only helper would
  leave other self-affecting targets and runtime provenance uncovered. A second
  experiment, selection, application, or orchestration engine would duplicate existing
  semantic owners and violate the architecture contract.
- Historical and forward-shadow hosts supply exact `CandidateTrialBatch` records, and
  independent reviewers supply exact `CandidateReview` records. libRSI derives every
  gate from the original evaluation contract, configured risk policy, exact candidate,
  actor separation, and current baseline; host booleans and narration have no
  activation authority.
- Actual target mutation, produced-state verification, and rollback remain exclusively
  owned by the Block 16 application lifecycle. Block 17 adds only the stronger approval
  lineage required before that ordinary lifecycle may activate an explicitly declared
  self-change.

### Resource and economy contract

Use deterministic policy candidates and replay fixtures; no live self-modification or provider call. Run low-risk ordinary improvement proof before meta-governance cases.

### QA and independent review

Independent review is required for activation semantics, self-review separation, currentness, risk classification, and rollback proof.

### Acceptance

- Self-change uses ordinary records/outcomes; targeting is explicit; configured governance cannot be bypassed; current selector-policy guarantees survive; failed activated candidates roll back.

### Negative tests

- Reject implicit meta-targeting, candidate self-acceptance, same-actor review where independence is required, activation without every gate, stale evidence, and irreversible no-rollback policy changes.

### Completion evidence

- Repository implementation commit:
  `859b51160a391d684e647b905e27ec1f2e348620`.
- External/domain revision or root: not applicable. Block 17 uses deterministic
  in-memory candidate, governance, and target fixtures; no live model, provider,
  repository mutation, deployment, or self-modification authority was exercised.
- Inputs: accepted Blocks 7–16, the existing hypothesis/experiment/comparison and
  ordinary improvement/application engines, `selector_policies.py` compatibility
  guarantees, architecture-contract sections 2 and 10, and tracker capability-frame
  SHA-256
  `e189c53ff767433bd4fad712808d25d3e5adde421fdf0c241948a60f83cd472e`.
- Outputs: structured `librsi.rsi` records, action codecs, policy, replay, and restartable
  workflow; cross-cutting `librsi.governance` requirement/authority records; explicit
  meta-target classes and configured risk tiers; distinct historical replay and
  forward-shadow assessments; independent-actor review; canonical activation approval;
  `RSIResult`; and ordinary application, actual-state verification, and rollback reuse.
  Classified requirements are identity-bound through `ImprovementRequest` and
  `ApplicationHandoff`. Enabled application resolves the requirement's registered
  authority class and requires the exact concrete `SelfChangeApproval`, candidate,
  requirement, and current snapshot before any provider effect. Unclassified ordinary
  records omit the optional fields and preserve their prior identity.
- Focused validation: `36 passed` with `92.41%` branch coverage across `librsi.rsi`.
  Cases cover explicit targeting and configured class/risk derivation; distinct
  historical and forward-shadow evidence; candidate-author/reviewer separation;
  accepted, rejected, inconclusive, and operational-failure governance; activation
  disabled; approval/currentness/replay/result substitution; managed/external
  equivalence; verified activation; application failure; successful and failed rollback;
  direct `apply_improvement` missing-authority rejection; and unregistered subclass and
  equality-spoof authority rejection before provider effects and on canonical decode.
- Mapped validation: Ruff formatting and lint passed across `src` and `tests`; mypy
  passed all `85` source files; the protected Block 16 application and v0.2 compatibility
  set passed `36` tests; and the full suite passed `577` tests at `90.31%` branch
  coverage. The full suite includes the ordinary hypothesis/evidence/experiment,
  comparison, improvement, application, persistence, and compatibility layers. Its `24`
  warnings are the pre-existing deprecated compatibility-wrapper warnings.
- Artifact validation: sdist and wheel builds succeeded; the wheel contains
  `librsi.governance`, the structured `librsi.rsi` package, `librsi.records`, and
  `py.typed`. Isolated installed-wheel runs passed all `36` Block 17 tests on Python
  3.11, 3.12, and 3.13.
- Candidate freeze: content root
  `c4259d7b8da9ec60cc5ca37c64a83b63c885306fb895c797e25bb6ba31121ef6`
  remained unchanged through final independent review. Exactly `23` candidate paths
  were committed; unrelated untracked `uv.lock` was excluded and remained unchanged at
  size `134695`, mtime `1787379167`, and SHA-256
  `ea9a2eb3afc46401f2356ef098e005ec87ac33e27475e43bcd86eb4131ea960e`.
- Independent semantic review: ACCEPT on the exact root above after two adversarial
  remediation cycles. Review reproduced zero-effect rejection of a forged
  `self_change_approval` subclass, confirmed canonical deserialization rejected it,
  preserved legitimate managed/external equivalence, found no additional material
  defect, and accepted the Block 18 Stop.
- Product capability review: capability gain is explicit, restartable, auditable
  self-change governance over the existing hypothesis-to-application machinery.
  Regression risk from self-approval or ordinary-path bypass is controlled by distinct
  actors, evidence-derived gates, exact currentness/rollback, identity-bound handoffs,
  and canonical registered authority classes. The additional governance cost applies
  only to explicitly classified self-affecting targets.
- Retained open work: none within Block 17. Batteries-included local defaults and the
  high-level facade remain exclusively in Block 18.
- Decision/continuation posture: not applicable; Block 18 is dependency-safe.
- Post-block audit: accepted; no batteries-included defaults, public facade
  consolidation, hosted execution, provider integration, deployment platform, or
  repository automation crossed the Block 17 Stop.

### Stop

Stop before batteries-included local defaults and public facade consolidation.

## Block 18 — Embedded/managed local runtime and high-level Python facade

Status: `not-started`

### Objective

Make local validation, investigation, improvement, and stepped execution useful
with minimal configuration through one engine that supports embedded and
managed-local composition while retaining replaceability.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: `LibRSI`, `local`, `for_repo`, embedded and managed
  local composition, workflow methods, SQLite, local
  command/filesystem/artifact defaults, and structured logging.
- Potential capability loss or regression: defaults could become mandatory infrastructure or make repositories fundamental.
- Protected-capability effect: low-level `RSIKernel`, external-host execution, independent component substitution, and generic targets remain supported.
- Architecture and operating-model effect: assembles thin reference adapters around the canonical engine; it does not create another engine.
- Tradeoff and source evidence: architecture contract sections 6–7 and scope revision Block 18; minimal setup is worth optional/local dependencies only when independently replaceable.

### Inputs and dependencies

- Blocks 6, 8, and 15–17.

### Required work

- Implement the high-level facade and local constructors over canonical workflows/runtime.
- Ship minimal SQLite, command, filesystem inspection, artifact-directory, and event/logging defaults behind protocols.
- Define one composition contract used by embedded callers and the later managed
  service; host selection cannot change canonical run/action/result semantics.
- Preserve expert/low-level APIs and support per-component replacement.

### Scope and non-goals

- In scope: local reference composition, embedded/managed host equivalence, and
  Python usability.
- Not in scope: generic repository automation, artifact/logging platforms, distributed orchestration, or mandatory server/provider dependencies.

### Deliverables and recorded state

- Facade/default modules, optional dependency boundaries, executable local examples, substitution tests, and updated low-level documentation.

### Resource and economy contract

Use temporary directories/databases/processes; reuse canonical workflow fixtures; no network or provider calls.

### QA and independent review

Review facade/runtime equivalence, dependency minimality, component replacement, repo convenience isolation, and legacy API reachability.

### Acceptance

- A trivial local workflow needs minimal setup; each default is substitutable; existing kernel APIs remain; README-ready examples use the facade rather than manual internals.

### Negative tests

- Reject hidden global state, mandatory repo fields, mandatory optional
  dependencies, facade/host-specific lifecycle semantics, two process owners,
  and local execution outside configured authority.

### Completion evidence

Pending.

### Stop

Stop before stabilizing external outcome projections or CLI schemas.

## Block 19 — Structured Outcome serialization, events, and external consumption

Status: `not-started`

### Objective

Stabilize versioned canonical projections for every workflow outcome across Python, JSON, events, and persistence.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: consumers receive complete, versioned results without understanding internal policy calls.
- Potential capability loss or regression: premature schema freeze could constrain real workflows or projection code could become semantic authority.
- Protected-capability effect: exact run/target/intent/evidence/intervention/application identity and cross-mode equivalence remain canonical.
- Architecture and operating-model effect: completes projections over workflow-owned result contracts introduced in Blocks 10, 11, 15, and 17.
- Tradeoff and source evidence: architecture contract section 11 and scope revision Block 19; stage result contracts early and freeze complete projections only after workflow use.

### Inputs and dependencies

- Blocks 10, 11, and 15–18.

### Required work

- Complete `Outcome`, `ValidationResult`, `InvestigationResult`, `ImprovementResult`, and `RSIResult` fields, schema versions, JSON/event/persistent projections, and reconstruction.
- Prove managed/external/hybrid semantic equivalence and migration/currentness behavior.

### Scope and non-goals

- In scope: semantic outcome contracts and stable projections.
- Not in scope: reporting dashboards, transport protocols, notification systems, or alternate lifecycle state.

### Deliverables and recorded state

- Outcome module/schemas, projection adapters, golden fixtures, compatibility tests, and consumer documentation.

### Resource and economy contract

Reuse canonical dogfood outcomes; compare exact semantic roots and exclude presentation-only differences; avoid regenerating unchanged workflows.

### QA and independent review

Review completeness, versioning, round trips, currentness, cross-mode equivalence, and projection-versus-authority separation.

### Acceptance

- Consumers need no internal policy knowledge; JSON round trips preserve identity; schema versions are explicit; all control modes project equivalent outcomes.

### Negative tests

- Reject unknown/incompatible schemas, missing lineage/currentness, transport metadata changing roots, lossy projection, and projection writes that mutate canonical state.

### Completion evidence

Pending.

### Stop

Stop before CLI, HTTP, or MCP transport stabilization.

## Block 20 — CLI, target admission, and external-agent protocol

Status: `not-started`

### Objective

Drive durable libRSI workflows and target submissions through structured
commands and JSON without inferring state from prose.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: target/objective/evaluation-contract submission plus
  start/status/next/submit/resume/outcome operations for validation,
  investigation, improvement, and governed RSI.
- Potential capability loss or regression: CLI state or prose could diverge from the canonical runtime or silently accept stale results.
- Protected-capability effect: explicit run/action/result identity, schema validation, restartability, and external-host neutrality.
- Architecture and operating-model effect: CLI is a projection over runtime/service contracts, not a controller.
- Tradeoff and source evidence: architecture contract section 12 and predecessor Block 20; structured JSON adds interface work but enables robust Codex/agent driving.

### Inputs and dependencies

- Blocks 7 and 19, with workflow APIs exposed only when implemented.

### Required work

- Add CLI entrypoint and structured validate/investigate/improve/status/next/submit/resume/outcome commands.
- Add a structured `target submit` contract that binds the target snapshot,
  objective, evaluation contract, capabilities, evidence/currentness baseline,
  application authority, and resource limits before managed work may begin.
- Bind input/output schemas to canonical records and runtime transitions.
- Add interruption/restart, stale submission, and wheel-installed CLI dogfoods.

### Scope and non-goals

- In scope: local CLI/external-agent projection and standalone target admission.
- Not in scope: HTTP/MCP, natural-language agent orchestration, shell inference, or application authority.

### Deliverables and recorded state

- CLI module/entrypoint, JSON schemas/examples, subprocess dogfoods, and packaging metadata.

### Resource and economy contract

Use temporary local stores and subprocess invocations; one maintained command matrix covers workflow and lifecycle commands.

### QA and independent review

Review schema/runtime equivalence, restartability, error determinism, stale rejection, and no prose-derived state.

### Acceptance

- A complete run is externally driven through JSON; a target can be admitted
  without prose-derived state; controller restart loses no state; `next`
  supplies exact context/schema; stale/invalid submission fails closed.

### Negative tests

- Reject unknown commands/schemas, wrong run/action IDs, duplicate advancement,
  malformed JSON, unsupported workflow claims, missing evaluation/application
  authority, and CLI-only state.

### Completion evidence

Pending.

### Stop

Stop before HTTP/MCP compatibility or hosted-provider adapters.

## Block 21 — Managed libRSI service, HTTP, and MCP projections

Status: `not-started`

### Objective

Expose the canonical runtime through one transport-independent service facade
that supports externally driven and managed standalone execution, plus
maintained HTTP and MCP projections.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: explicit durable target/run handles, managed
  validate/investigate/improve/RSI operations, remote lifecycle operations,
  knowledge queries, capability inspection, local stdio MCP, and maintained
  remote MCP transport.
- Potential capability loss or regression: transport sessions could become state authority, network access could imply application authority, or premature schemas could freeze incomplete semantics.
- Protected-capability effect: one runtime/store/outcome model, explicit capability authority, restartability, secret minimization, and optional dependencies.
- Architecture and operating-model effect: `LibRSIService` delegates to canonical owners; HTTP/MCP remain thin replaceable transports.
- Tradeoff and source evidence: architecture contract section 12, scope revision Block 20A, and historical server extension; compatibility waits for Blocks 19–20.

### Inputs and dependencies

- Blocks 7, 8, 19, and 20; expose each workflow only when its canonical API exists.

### Required work

- Implement transport-independent service operations for runs, actions/results, outcomes, knowledge queries, and capability inspection.
- Implement managed-service orchestration that repeatedly selects the next
  canonical action, dispatches only configured capabilities/providers, submits
  typed results, and stops on an outcome, explicit bound, unavailable
  capability, or authority gate. It may not invent a second scheduler or
  lifecycle.
- In managed mode, generate multiple supported competing hypotheses, design
  discriminating experiments and counterexamples, classify results as
  supported/refuted/inconclusive, construct and compare interventions, select
  one/many/none, apply only when authorized, verify, and iterate until the
  evaluation contract or bounded stop is met.
- Add versioned HTTP/JSON endpoints using a mature optional framework.
- Add maintained MCP tools/resources over the service for stdio and the current maintained remote transport.
- Enforce explicit run handles, restart, duplicate/stale safety, authority distinctions, bounded requests, structured errors, health/readiness, and graceful shutdown.

### Scope and non-goals

- In scope: optional service/HTTP/MCP projections, bounded managed-local host,
  and basic operational hooks.
- Not in scope: an API gateway, generic workflow service, distributed scheduler, UI, notification platform, observability platform, or full multi-tenant control plane.

### Deliverables and recorded state

- Service facade, optional server/MCP extras, entrypoints, schemas, capability report, HTTP/MCP/restart dogfoods, and security boundary documentation.

### Resource and economy contract

Use disposable local servers, temporary stores, loopback binding, bounded requests, and one semantic-equivalence fixture; no deployment or public endpoint.

### QA and independent review

Independent review covers shared-runtime authority, network/application permissions, secret projection, restart, duplicate submission, optional packaging, and transport neutrality.

### Acceptance

- One service facade backs HTTP and MCP; externally driven and managed runs are
  semantically equivalent; stdio and maintained remote MCP work; target/run
  handles survive restart; all projections share canonical outcomes;
  capabilities/authority are inspectable; stale/duplicate results fail safely.

### Negative tests

- Reject session-only state, a managed-service second controller, autonomous
  work without a bound objective/evaluation contract, anonymous remote mutation
  in configured protected mode, secret leakage, oversized requests,
  unsupported capability simulation, transport-root divergence, and
  unavailable or unauthorized Applier execution.

### Completion evidence

Pending.

### Stop

Stop before production deployment, general platform features, or provider-specific adapters.

## Block 22 — Optional reasoner, Codex app-server, optimizer, and backend integrations

Status: `not-started`

### Objective

Prove stable capability contracts with one maintained hosted-model reasoner
adapter, a Codex app-server adapter, and only justified optional backend
integrations.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: managed structured reasoning, Codex-powered
  hypothesis/experiment/candidate work, and validated replaceability of
  selected optimizer/backend contracts.
- Potential capability loss or regression: provider types, credentials, optimizer scores, or workflow engines could leak authority into core semantics.
- Protected-capability effect: base install remains provider-free; external-agent mode remains first-class; proposals never become truth/selection/application automatically.
- Architecture and operating-model effect: optional extras implement existing protocols without modifying canonical records.
- Tradeoff and source evidence: architecture contract sections 5–6 and scope revision Block 21; add only adapters required by a real dogfood.

### Inputs and dependencies

- Blocks 9 and 18–20; current provider SDK/spec selected at implementation time.

### Required work

- Implement `ExternalAgentReasoner` and one maintained hosted-model reasoner extra through typed reasoning tasks.
- Implement an optional Codex app-server reasoner/executor extra through the
  domain-neutral typed client from `estill01/utils`; pin exact protocol/client
  compatibility and keep app-server behind libRSI capability interfaces.
- Make provider process ownership explicit: standalone libRSI may own its local
  process; an embedding host may inject a provider; Software Factory-managed
  libRSI must never start a competing process.
- Add optimizer/experiment/orchestrator projections only when one named dogfood validates a stable contract.
- Keep credentials/configuration outside canonical records and provide deterministic fake/offline contract tests.

### Scope and non-goals

- In scope: optional adapters proving capability/backend substitution,
  including `librsi[codex]` or its package-equivalent extra.
- Not in scope: a model gateway, optimizer implementation, agent framework, workflow platform, credential manager, or mandatory network dependency.

### Deliverables and recorded state

- Optional extras/adapters, provider contract tests, configuration/secret docs, and at most the dogfood-justified backend adapters.

### Resource and economy contract

Offline fake tests are the normal path. Any live hosted-model test requires separate credential/spend authority and a bounded call budget; absence does not block deterministic contract acceptance.

### QA and independent review

Review dependency isolation, provider-neutral schemas, credential hygiene, proposal authority, and parity with external-agent mode.

### Acceptance

- Base install needs no SDK; an optional extra enables maintained Codex
  reasoning/execution; provider swaps do not alter epistemic schema;
  external-agent execution remains equivalent.

### Negative tests

- Reject provider objects in canonical records, credential
  serialization/logging, model output truth promotion, provider-completion as
  evidence/acceptance, two app-server process owners, optimizer self-selection,
  and base-import failure without extras.

### Completion evidence

Pending.

### Stop

Stop before adding ecosystem adapters without a named contract or dogfood need.

## Block 23 — Software Factory consumer integration

Status: `not-started`

### Objective

Prove that Software Factory consumes libRSI capabilities and outcomes for ordinary and governed self-improvement targets without reverse dependency.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: sophisticated software targets, multi-repository snapshots, candidate/worktree handling, improvement, and application verification through libRSI contracts.
- Potential capability loss or regression: Software Factory ontology, ledgers, or control state could leak into libRSI or be duplicated.
- Protected-capability effect: dependency remains Software Factory → libRSI; implementation correctness and improvement validity remain separately represented.
- Architecture and operating-model effect: incremental Q1–Q5 adapters reuse Software Factory's existing persistence/effect owners and libRSI's semantic owners.
- Tradeoff and source evidence: architecture contract section 5 and scope revision Block 22; thin adapters expose bad abstractions early without coupling repositories.

### Inputs and dependencies

- Blocks 5, 8, 12, and 15–20; authoritative Software Factory checkout and its existing stores/adapters.

### Required work

- Map Software Factory target/revision state, capabilities, candidates/worktrees, experiments, application, and verification to libRSI records/actions/results.
- Complete one ordinary target-repository improvement run and one governed Software Factory self-target run or safe application-disabled equivalent.
- Preserve existing Factory telemetry, learning, evidence, and effect owners; return canonical libRSI evidence/outcomes.

### Scope and non-goals

- In scope: consumer-side adapters and deterministic integration dogfoods in the appropriate repositories.
- Not in scope: importing Software Factory from libRSI, copying Factory schemas into libRSI, replacing Factory execution infrastructure, or production application.

### Deliverables and recorded state

- libRSI software helpers only where generic/lightweight, Software Factory adapter commits, cross-repository version pin, and integration fixtures/evidence.

### Resource and economy contract

Use disposable target repositories and current accepted fixtures; run focused contract tests before either mapped suite; no production target or provider spend.

### QA and independent review

Review both repositories at exact commits, dependency direction, owner reuse, target/candidate/evidence mapping, application boundary, and dogfood outcome.

### Acceptance

- Software Factory imports libRSI only; one ordinary repo run works; multi-repo identity works; candidate evidence returns for epistemic evaluation; correctness and improvement validity remain distinct.

### Negative tests

- Reject reverse imports, duplicate ledgers/schemas, stale revision mapping, worktree-as-authoritative target, implementation success as improvement proof, and ungoverned self-application.

### Completion evidence

Pending.

### Stop

Stop before claiming full architecture proof or modifying unrelated Software Factory programs.

## Block 24 — End-to-end embedded, external, and managed dogfoods

Status: `not-started`

### Objective

Prove the complete architecture through maintained deterministic workflows, interruption, control modes, application/rollback, parallel search, and self-change.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: system-level evidence that independently tested owners compose into one correct product.
- Potential capability loss or regression: broad tests could become one-time demonstrations, duplicate fixtures, or mask owner-specific failures.
- Protected-capability effect: control-plane equivalence, durability, application-default-off, rollback, and stronger self-change gates are exercised together.
- Architecture and operating-model effect: converges existing incremental dogfoods into the maintained terminal system matrix.
- Tradeoff and source evidence: predecessor Block 23 and scope revision Block 23; reuse earlier fixtures and extend only missing combinations.

### Inputs and dependencies

- Blocks 10, 11, and 15–23.

### Required work

- Maintain validation-only, investigation-only, externally driven improvement, managed-equivalent improvement, interruption/resume, application-disabled, apply/verify/rollback, parallel search, and RSI/self-change scenarios.
- Add a maintained managed-standalone dogfood that accepts a target/objective,
  generates at least two materially competing hypotheses, runs discriminating
  experiments, retains inconclusive evidence honestly, compares interventions,
  selects one/many/none, applies only under an explicit authority envelope,
  verifies the result, and iterates or stops for a typed reason.
- Run the same scenario externally driven and through the managed service and
  compare canonical roots/outcomes, including a Codex-provider fake and an
  injected-provider composition with no competing process owner.
- Reuse earlier vertical fixtures and assert canonical roots/outcomes across control planes.

### Scope and non-goals

- In scope: deterministic end-to-end CI proof of already-owned capabilities.
- Not in scope: a new framework, production deployment, per-provider matrix, or performance benchmarking platform.

### Deliverables and recorded state

- Maintained dogfood suite, rooted fixtures, exact scenario/output matrix, and CI integration.

### Resource and economy contract

Run affected scenarios first; batch the final deterministic matrix once at the frozen candidate; use no live provider, remote service, or production target.

### QA and independent review

Review scenario completeness, reuse, semantic equivalence, exact outcomes, failure assertions, and absence of test-only alternate architecture.

### Acceptance

- Every required scenario is a maintained CI test/dogfood and passes against the same canonical engine and current package artifacts.

### Negative tests

- Reject one-time/manual proof, managed/external root drift, single-hypothesis
  theater, nondiscriminating experiments, inconclusive evidence promoted as
  support, nonresumable interruption, implicit application, failed rollback,
  losing-lane promotion, two process owners, and self-change gate bypass.

### Completion evidence

Pending.

### Stop

Stop before final cross-domain audit and public release cleanup.

## Block 25 — Comprehensive cross-domain agnosticism proof

Status: `not-started`

### Objective

Demonstrate that the complete validation, investigation, and improvement engine remains domain-neutral after every software and product integration.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: one deterministic non-software adapter completes the same generic workflow and Outcome family as software targets.
- Potential capability loss or regression: a superficial fixture could miss hidden Git/software assumptions or introduce domain branches in core code.
- Protected-capability effect: generic Target, Intervention, Candidate, Evidence, capability, runtime, and Outcome semantics remain unchanged.
- Architecture and operating-model effect: final audit of the continuously maintained non-software sentinel across the completed system.
- Tradeoff and source evidence: architecture contract section 4 and scope revision Block 24; a small deterministic target is sufficient when it traverses the real engine.

### Inputs and dependencies

- Block 24 and the non-software sentinel lineage from Blocks 5, 8, 10, 12, and 15.

### Required work

- Extend one maintained deterministic non-software adapter through validation, investigation, improvement, and structured outcomes.
- Audit generic modules for software/Git types and prove target-specific behavior remains behind capabilities/adapters.

### Scope and non-goals

- In scope: comprehensive domain-neutrality proof.
- Not in scope: many-domain breadth, physical deployment, generic simulation infrastructure, or domain-specific product features.

### Deliverables and recorded state

- Non-software adapter/dogfoods, generic-code dependency audit, exact outcome comparison, and CI mapping.

### Resource and economy contract

Reuse the existing sentinel and exact outcomes; widen the static audit only on a concrete software-type leak; no external system needed.

### QA and independent review

Independent review compares generic versus adapter ownership and verifies the real engine—not a test-only shortcut—executes every workflow.

### Acceptance

- Generic workflow code requires no software/Git type; interventions/candidates and outcomes are unchanged; target-specific behavior is wholly adapter-owned.

### Negative tests

- Reject repository fields in generic records, software-only workflow branches, adapter authority leakage, and non-software fixtures bypassing canonical runtime/evaluation.

### Completion evidence

Pending.

### Stop

Stop before release-facing API/version/docs changes.

## Block 26 — Public API, documentation, packaging, migration, and release gate

Status: `not-started`

### Objective

Make the redesigned architecture the accurate, typed, installable, migration-ready public product surface.

### Target-product capability delta

- Posture: `consequential`.
- Intended capability gain: clear `validate → investigate → improve → governed recurse` documentation, stable exports, optional extras, executable examples, migration guidance, and release evidence.
- Potential capability loss or regression: premature removal, misleading claims, accidental dependency growth, or an unauthorized license/release action.
- Protected-capability effect: low-level compatibility is preserved or explicitly migrated; examples match the wheel; no planned-only capability is advertised.
- Architecture and operating-model effect: consolidates product-facing namespace/package/CLI/service surfaces after semantic proof.
- Tradeoff and source evidence: architecture contract sections 1, 7, and 14 plus predecessor Block 25; cleanup occurs last to avoid documentation/schema churn.

### Inputs and dependencies

- Blocks 21–25, accepted compatibility contract, and a complete release candidate.
- Non-delegable legal input: the exact selection defined by the continuation-first
  license gate; it blocks only the license-dependent acceptance subset after all
  license-independent Block 26 work is complete.

### Required work

- Finalize package organization/exports, facade-first README/API examples, type docs, versioning, metadata, extras, CLI/server entrypoints, changelog, and `0.2.x` migration guide.
- Execute examples from the built wheel and reconcile documentation against current capabilities.
- Prepare the license decision packet with MIT and Apache-2.0 implications and add only the selected license.
- Build and validate release artifacts; publication remains excluded without separate authority.

### Scope and non-goals

- In scope: release-ready source, docs, package artifacts, migration, and license once authorized.
- Not in scope: PyPI publication, GitHub Release creation, production deployment, marketing claims beyond evidence, or backward-compatibility promises not tested.

### Deliverables and recorded state

- Public docs/examples, migration/changelog, license decision packet and selected
  license when authorized, versioned build metadata, wheel/sdist, install smoke
  evidence, and terminal completion audit.

### Resource and economy contract

Reuse Block 24–25 outcomes; render/build/test docs once after content freeze; rerun only invalidated examples or package checks.

### QA and independent review

Independent review covers API/docs truthfulness, migration/compatibility, optional dependency isolation, license exactness, artifact contents, and terminal matrix.

### Acceptance

- Wheel/sdist, Ruff, mypy, tests, branch coverage, and installed examples pass; docs
  claim only current capability; migration is explicit; public product positioning
  matches validated workflows.
- License-dependent subset: a direct user selection is recorded, the selected
  license text/classifier/reuse claims are exact, or an explicit no-license choice is
  reflected without claiming open-source reuse. This subset alone may remain open
  while every safe acceptance item above is completed.

### Negative tests

- Reject stale examples, missing/extra exports, base install pulling optional stacks, planned-only claims, unselected license grant, source-tree-only imports, and artifact/version mismatch.

### Completion evidence

Pending.

### Stop

Stop before PyPI publication, GitHub Release creation, production deployment, or any external announcement not separately authorized.

## 8. Program source map

| Block | Current source basis |
|---:|---|
| 0 | Architecture contract and historical Block 0 acceptance evidence. |
| 1 | Historical Block 1 contract, `records.py`, `identity.py`, and accepted evidence. |
| 2 | Historical Block 2 contract, exactness tests, and accepted evidence. |
| 3 | Historical Block 3 plus scope revision Block 3. |
| 4 | Historical Block 4 plus scope revision Block 4. |
| 5 | Historical Block 5 plus early domain-neutrality amendment. |
| 6 | Historical Block 6 plus KnowledgeStore scope amendment. |
| 7 | Historical Block 7 plus semantic-runtime/reference-durability amendment. |
| 8 | Historical Block 8 plus capability/search authority amendment. |
| 9 | Historical Block 9 plus external optimizer/reasoner boundary. |
| 10 | Historical Block 10 plus non-software validation/result-contract amendment. |
| 11 | Historical Block 11 and architecture investigation contract. |
| 12 | Historical Block 12 plus non-software candidate amendment. |
| 13 | Historical Block 13 and typed operationalization contract. |
| 14 | Historical Block 14 plus search-versus-selection amendment. |
| 15 | Historical Block 15 plus two-domain improvement acceptance. |
| 16 | Historical Block 16 and candidate/application architecture contract. |
| 17 | Historical Block 17 and self-change architecture contract. |
| 18 | Historical Block 18 plus thin-defaults amendment. |
| 19 | Historical Block 19 plus incremental workflow-result amendment. |
| 20 | Historical Block 20 and external-agent projection contract. |
| 21 | Historical Block 20A extension plus deferred-transport amendment. |
| 22 | Historical Block 21 plus optional backend amendment. |
| 23 | Historical Block 22 plus incremental Q1–Q5 amendment. |
| 24 | Historical Block 23 plus incremental-dogfood amendment. |
| 25 | Historical Block 24 plus continuous-sentinel amendment. |
| 26 | Historical Block 25 and public product-positioning amendment. |

## 9. Program verification matrix

| Block | Current verification basis |
|---:|---|
| 0 | Accepted architecture/compatibility CI and current regression suite. |
| 1 | Accepted canonical record CI and semantic hardening suite. |
| 2 | Accepted exact hypothesis/experiment CI and hardening suite. |
| 3 | Focused epistemic/aggregation tests plus full compatibility/package suite. |
| 4 | Metric/trial/evaluation and command-adapter tests plus full suite. |
| 5 | Target/currentness and non-software sentinel tests plus full suite. |
| 6 | Knowledge round-trip/currentness/migration tests plus full suite. |
| 7 | Transition/replay/resume/idempotence tests plus full suite. |
| 8 | Managed/external/hybrid capability equivalence tests plus full suite. |
| 9 | Structured reasoner validation/equivalence tests plus full suite. |
| 10 | Software-neutral and non-software validation dogfoods plus full suite. |
| 11 | Branch/falsification/redesign investigation dogfoods plus full suite. |
| 12 | Candidate/handoff/currentness and non-software tests plus full suite. |
| 13 | Operationalization/evaluation-contract tests plus full suite. |
| 14 | Comparison/guardrail/Pareto/none-accepted tests plus full suite. |
| 15 | Software-oriented and non-software improvement dogfoods plus full suite. |
| 16 | Apply-disabled/apply/verify/rollback fixtures plus full suite. |
| 17 | Self-change governance/activation/rollback dogfoods plus full suite. |
| 18 | Local facade/default substitution and installed-example tests. |
| 19 | Outcome round-trip/version/cross-mode equivalence tests. |
| 20 | Installed CLI JSON/restart/stale-submission dogfoods. |
| 21 | Service/HTTP/MCP/restart/authority/transport-neutrality tests. |
| 22 | Offline provider contract/dependency/secret-isolation tests. |
| 23 | Cross-repository adapter and Software Factory dogfoods at exact commits. |
| 24 | Complete deterministic end-to-end scenario matrix in CI. |
| 25 | Real-engine non-software validation/investigation/improvement audit. |
| 26 | Full quality gates, artifact inspection, installed examples, docs/API/license review. |

## 10. Final completion definition

The program is complete only when Blocks 0–26 are accepted at exact current pushed
revisions; every verification-matrix row is current; the built package and public
examples are rehydrated independently; Software Factory and the non-software target
produce current observable outcomes through the same semantic engine; no transport,
provider, optimizer, or host became a duplicate authority; retained open work is
genuinely reserved or excluded; and no publication, deployment, license, or
authoritative external application crossed its declared boundary.
