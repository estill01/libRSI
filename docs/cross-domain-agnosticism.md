# Cross-domain agnosticism proof

Block 25 maintains one deterministic fermenter adapter as the final
non-software sentinel. The adapter is deliberately physical-process-specific;
the library is not. It implements the existing `Reasoner`, `Experimenter`, and
improvement-cycle provider ports and supplies only typed action results.

The dogfood in `tests/test_block25_cross_domain_agnosticism.py` drives the same
canonical `ValidationWorkflow`, `InvestigationWorkflow`, `ImprovementWorkflow`,
`RuntimeEngine`, comparative evaluation, selection policy, and Outcome projection
used by every other target. No test-only workflow or evaluator exists.

## Ownership boundary

| libRSI owns | The fermenter adapter owns |
| --- | --- |
| requests, actions, run state, transitions, evidence validation, belief updates, hypothesis portfolio state, evaluation, selection, results, outcomes, and projections | physical measurements, physical causal labels, bounded setpoint proposal data, and trial observations |
| whether evidence is admissible and what it supports | collecting the requested physical observation |
| whether a candidate satisfies objectives and guardrails | producing the requested baseline/candidate measurements |
| whether a run stops and which candidate is selected | no acceptance, application, Outcome, or lifecycle authority |

The improvement result remains proposal-only. Its handoff has `apply=False`, and
the adapter cannot authorize or perform a target effect.

## Maintained proof

The fixture completes these paths with one adapter instance:

1. claim validation gathers two current physical-process observations and derives
   a supported `ValidationResult` and `Outcome`;
2. investigation retains two competing physical hypotheses, uses observation-only
   discriminating experiments, rejects the oxygen-transfer hypothesis, and
   supports the thermal-transfer hypothesis;
3. improvement reuses the same investigation machinery, prepares a typed bounded
   intervention candidate, runs the normal six-trial comparative evaluator,
   applies the normal objective and contamination guardrail policy, and selects
   one candidate without applying it; and
4. all three canonical results project through the same public
   `OutcomeProjection` codec with no semantic drift.

Two complete executions must be byte-identical. The frozen roots are:

| Workflow | Result root | Outcome root | Projection root |
| --- | --- | --- | --- |
| validation | `321c6d8f8a6a4830ec2a596fa5590bf9f3e4e28b77a41a8d49e26b44124d094b` | `87c0c16b1c7abc5a3f428c42ffde577c9af777d42bdf9eff0b5fc3ff8d01ea2e` | `c9ad9bc76522ed30bf38c1fe465c0cc7044a3378287c0e1368077eba10bf5e67` |
| investigation | `c27aced0b9da03ea80576360e70b9fc13f29096a7d80121b5e65cdec7e8c6d67` | `158babfe98b35dadc2f21d4b015d0ae2d820efa2affe413add23976f3ea8b674` | `49abc7b406e7c6dde81c068a4559a086f1b39715137b05c4b221953812d04767` |
| improvement | `be4cb50aa60e6bc20298a43f528a7630d5f5814cb9152aae9a5e922f1dab20f9` | `fef522467c64b3ca51fbeaada63d4d73f15fcab12c2649ea777ecbee2a827e3d` | `6d7d73c84e6a244125a612c5fbde6a6fca6b1a087fa24701a9924788fb5c72de` |

## Generic-code dependency audit

`tests/block25_domain_audit.py` parses all 102 generic semantic, governance,
runtime, external-agent protocol, and managed-service source modules. The roster
includes identity, checkpoints, kernel, governance, protocol/controller, service,
SQLite semantic stores, and every validation/investigation/improvement owner.

The excluded roots are the explicit host/adapter boundary: `facade` composition,
`local` effects, providers, CLI/HTTP/MCP transports, shared-utility conformance,
the empty expert extension namespace, and package entrypoint/aggregation modules.
Those roots can describe software-shaped hosts without making that ontology a
requirement of the generic engine. The audit rejects:

- Git, repository/repo, worktree, patch, build-command, pull-request, commit-root,
  commit-id, or source-tree identifiers and fields in generic code, including
  camelCase names, string-indexed fields, and reflective field access;
- target-kind comparisons, set membership, or structural matches that create
  software-only branches; and
- static or dynamic imports from host adapters, providers, CLI, HTTP, MCP, or
  local-effect modules into generic semantic ownership.

The exact accepted generic-source aggregate root is
`913027cc09d5f976bbdffd8bd72a9e24da066f1cb39f3b67115f44539ebe8456`.
Any generic source change intentionally invalidates that root and requires the
cross-domain proof to be reviewed again. Negative tests inject each prohibited
leak class and prove the audit fails closed. Runtime negatives independently
prove that an adapter-supplied Outcome, forged comparative `Evaluation`,
noncanonical runtime frontier, and improvement application-authority payload are
all rejected before selection or authoritative run-state mutation.

The suite is part of the ordinary `tests/` discovery used by the maintained CI
matrix. It uses no external process, provider, repository, or physical system.
