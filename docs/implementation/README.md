# libRSI Internal Implementation Program

These documents are maintainer/implementer planning and execution records, not end-user documentation.

## Canonical documents

- [`architecture-contract.md`](architecture-contract.md) — maintained architecture, namespace ownership, control-plane, domain-neutrality, semantic/infrastructure boundaries, persistence, and compatibility contract established by Block 0 and later maintained revisions.
- [`architecture-expansion-implementation-tracker.md`](architecture-expansion-implementation-tracker.md) — primary architecture/refactor implementation program, Blocks 0–25.
- [`scope-boundaries-and-early-dogfood-revision.md`](scope-boundaries-and-early-dogfood-revision.md) — **normative planning amendment** that narrows infrastructure scope, promotes incremental Software Factory consumption, adds early non-software dogfoods, stages Outcome contracts earlier, treats external optimizers/backends as replaceable capabilities, and defers HTTP/MCP compatibility commitment until projected semantic contracts stabilize.
- [`server-mcp-implementation-block.md`](server-mcp-implementation-block.md) — maintained Block 20A extension covering the libRSI service/API/server and MCP server surface under the revised thin-transport boundary.
- [`parallel-implementation-plan.md`](parallel-implementation-plan.md) — dependency graph, workstreams, merge waves, interface-freeze points, and parallel execution guidance. Read it together with the scope/dogfood revision; the revision controls where it narrows older scheduling guidance.
- [`implementation-status.md`](implementation-status.md) — mutable status ledger with ownership, branches/PRs, implementation commits, verification evidence, dates, and update notes for the implementation Blocks, including Block 20A.

## Planning authority

The implementation tracker remains the primary Block inventory and acceptance source. The architecture contract defines stable architectural invariants. Maintained revision documents may explicitly amend Block scope or ordering without rewriting the historical tracker wholesale.

For the current program, `scope-boundaries-and-early-dogfood-revision.md` is authoritative on these points:

- libRSI owns semantic integrity, not generic infrastructure platforms;
- mature optimizers, orchestrators, experiment platforms, coding agents, and storage systems are replaceable implementations behind libRSI contracts;
- domain neutrality is tested continuously beginning with Block 5 rather than first checked at Block 24;
- Software Factory consumption begins incrementally as Blocks 5/8/12/15/16 stabilize, while Block 22 remains its final integration acceptance gate;
- workflow-specific result contracts emerge with Blocks 10/11/15/17, while Block 19 stabilizes external projections;
- Block 20A server/MCP is a late compatibility projection over stable runtime/outcome/agent schemas rather than a semantic critical-path dependency.

## Maintenance rule

Architecture/acceptance requirements belong in the implementation tracker, architecture contract, a maintained revision, or a maintained extension Block document. Actual progress claims belong in `implementation-status.md` and should cite exact commits/PRs and retained verification evidence.

A Block is not `verified` merely because its code has been committed or merged; its maintained acceptance criteria—including applicable later maintained revisions—must be checked against the current authoritative implementation.
