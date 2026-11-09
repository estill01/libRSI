# Consumer integration contract

This contract maps a consumer-owned system into libRSI without reversing the
dependency or transferring effect authority. A consumer imports public libRSI
contracts; libRSI never imports, edits, tests, pins, or discovers the consumer.

## Canonical mapping

| Consumer concept | libRSI contract | Owner boundary |
|---|---|---|
| component identity, locator, revision, observed state | `ComponentState` projected by `map_composite_snapshot` to `TargetRef` and `TargetSnapshot` | consumer observes; libRSI canonicalizes |
| atomic multi-component baseline | composite `TargetSnapshot` with exact component snapshots and roots | consumer supplies the complete snapshot; libRSI never fills missing components |
| available operations | `TargetCapabilities` and `CapabilityRegistry` routes | host implements effects and selects posture |
| proposed workspace/change | `InterventionSpec` → `InterventionImplementationRequest` → `CandidateSnapshot` | implementer prepares only a candidate; the authoritative baseline is unchanged |
| experimental observation | `ExperimentSpec`, `Observation`, `Evidence`, and `CandidateTrialBatch` | host executes; libRSI evaluates exact returned records |
| selection/application handoff | `SelectionDecision`, `ApplicationHandoff`, `ApplicationRequest`, and `ApplicationCommand` | libRSI selects under policy; host alone applies when explicitly authorized |
| actual post-effect state | `ApplicationReceipt`, `VerificationResult`, and `ApplicationResult` | host observes actual state; libRSI distinguishes correctness from improvement validity |
| governed self-change | `MetaTargetDeclaration`, `SelfChangeGovernanceResult`, `SelfChangeApproval`, and `RSIResult` | application remains disabled unless exact governance and activation authority exist |

`ComponentState` is a transient projection input, not a durable libRSI record or a
replacement consumer schema. The helper sorts exact component identities before
creating canonical records, so caller enumeration order cannot change snapshot identity.
Candidate preparation or implementation success is never improvement evidence.
Evidence must cite the exact candidate experiment and target snapshot; a
`CandidateTrialBatch` returns the exact baseline/candidate trials and derived
`Evaluation` without converting implementation success into improvement proof.
Verification must evaluate the actual host-observed state. Stale component roots
invalidate the whole atomic baseline while retaining per-component currentness
diagnostics.

## Downstream adoption handoff

A consumer repository should:

1. pin an accepted libRSI revision and declare the supported public-contract version;
2. own adapters for snapshot observation, persistence, subprocess/filesystem/provider
   effects, application, verification, rollback, credentials, and process lifecycle;
3. map complete caller-observed state into canonical inputs without adding product
   fields to libRSI records or treating candidate workspaces as authoritative targets;
4. run the public reference scenarios or equivalent consumer-local conformance tests;
5. return exact adapter revision, libRSI revision, target/candidate roots, experiment
   and evidence roots, application/verification outcome roots, focused commands, and
   failure/rollback evidence to its own acceptance owner; and
6. treat adoption, deployment, and production authority as downstream decisions—not
   evidence that this libRSI Block is complete.

`tests/block23_reference_consumer.py` is the executable in-repository reference. It
uses only public libRSI imports for an ordinary two-component target and an
application-disabled governed self-target-shaped run. It creates no external
checkout, process, provider call, or production effect.

## Reusable adaptive strategy loop

For a consumer whose change target is a strategy configuration or prompt, choose
the execution contract that matches the host:

| Execution model | Public API |
| --- | --- |
| One serialized owner for ordinary tasks and learning | `AdaptiveLoop` with `LearningStore`; local implementation `LocalLearningStore` |
| Concurrent ordinary tasks with one learning owner | `ConcurrentAdaptiveLoop` with `ConcurrentLearningStore`; local implementation `LocalConcurrentLearningStore` |

The [adaptive operation contract](adaptive-operation.md) defines the executor/scorer,
proposer, independent reviewer, profile isolation and scheduling responsibilities.
The [public template](../examples/adaptive_strategy.py) demonstrates measured
proposals, interruption/reopen, native acceptance and subsequent use.

The [concurrent operation contract](concurrent-adaptive-operation.md) adds durable
task admissions, snapshot-pinned completion and publication after native verification.
Hosts may use `run_task()` or split `admit_task()` and `complete_task()` around their
own executor. A separate `task_adapter` may own serving resources while retaining the
learning adapter's execution/scoring identity. The consumer owns transport, model
isolation, external idempotency, scheduling and request lifetimes.

The local concurrent backend requires one shared instance and a dedicated schema-2
profile directory; it rejects a second local owner and does not implicitly migrate
serialized profiles. Custom stores must qualify their concurrency and durability
guarantees independently. Both facades use the same native acceptance, application,
verification and rollback workflows.
