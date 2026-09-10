# libRSI Internal Implementation Program

These documents are maintainer/implementer planning and execution records, not end-user documentation.

The stable canonical program entry point is [`../tracker.md`](../tracker.md). It
contains the active full-contract Block queue, live statuses, accepted-history
mapping, source map, verification matrix, and terminal outcome. The documents in
this directory are retained as exact architectural sources, historical contracts,
evidence, and scheduling guidance; none is a competing active queue.

## Canonical documents

- [`adaptive-operation-20260906.md`](adaptive-operation-20260906.md) — exact accepted adaptive-operation predecessor, Blocks 0–2; historical after the proposal-learning successor was authored.

- [`architecture-contract.md`](architecture-contract.md) — maintained architecture, namespace ownership, control-plane, domain-neutrality, semantic/infrastructure boundaries, persistence, and compatibility contract established by Block 0 and later maintained revisions.
- [`architecture-expansion-implementation-tracker.md`](architecture-expansion-implementation-tracker.md) — preserved predecessor architecture/refactor program, historical Blocks 0–25; its requirements are consolidated into the canonical tracker.
- [`scope-boundaries-and-early-dogfood-revision.md`](scope-boundaries-and-early-dogfood-revision.md) — **normative planning amendment** that narrows infrastructure scope, promotes incremental Software Factory consumption, adds early non-software dogfoods, stages Outcome contracts earlier, treats external optimizers/backends as replaceable capabilities, and defers HTTP/MCP compatibility commitment until projected semantic contracts stabilize.
- [`server-mcp-implementation-block.md`](server-mcp-implementation-block.md) — preserved Block 20A extension, consolidated as canonical Block 21.
- [`parallel-implementation-plan.md`](parallel-implementation-plan.md) — dependency graph, workstreams, merge waves, interface-freeze points, and parallel execution guidance. Read it together with the scope/dogfood revision; the revision controls where it narrows older scheduling guidance.
- [`implementation-status.md`](implementation-status.md) — preserved detailed evidence ledger through predecessor Block 2; live status is owned by `docs/tracker.md`.

## Planning authority

`docs/tracker.md` is the primary Block inventory, status, and acceptance source. The architecture contract defines stable architectural invariants. The predecessor tracker, maintained revision, extension, parallel plan, and evidence ledger are source inputs whose dispositions and exact hashes are recorded in the canonical tracker.

For the current program, `scope-boundaries-and-early-dogfood-revision.md` is authoritative on these points:

- libRSI owns semantic integrity, not generic infrastructure platforms;
- mature optimizers, orchestrators, experiment platforms, coding agents, and storage systems are replaceable implementations behind libRSI contracts;
- domain neutrality is tested continuously beginning with Block 5 rather than first checked at canonical Block 25 (predecessor Block 24);
- Software Factory consumption begins incrementally as Blocks 5/8/12/15/16 stabilize, while canonical Block 23 remains its final integration acceptance gate;
- workflow-specific result contracts emerge with Blocks 10/11/15/17, while Block 19 stabilizes external projections;
- canonical Block 21 (predecessor Block 20A) server/MCP is a late compatibility projection over stable runtime/outcome/agent schemas rather than a semantic critical-path dependency.

## Maintenance rule

Current architecture/acceptance requirements, progress claims, completion evidence,
and status changes belong in `docs/tracker.md`. The architecture contract retains
stable invariants; revision, extension, predecessor-plan, and status-ledger documents
remain preserved source or historical evidence and must not be updated as a competing
live queue.

A Block is not `accepted` merely because its code has been committed or merged; its maintained acceptance criteria—including applicable later maintained revisions—must be checked against the current authoritative implementation.
