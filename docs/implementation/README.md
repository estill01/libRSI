# libRSI Internal Implementation Program

These documents are maintainer/implementer planning and execution records, not end-user documentation.

## Canonical documents

- [`architecture-contract.md`](architecture-contract.md) — maintained architecture, namespace ownership, control-plane, domain-neutrality, persistence, and compatibility contract established by Block 0.
- [`architecture-expansion-implementation-tracker.md`](architecture-expansion-implementation-tracker.md) — primary architecture/refactor implementation program, Blocks 0–25.
- [`server-mcp-implementation-block.md`](server-mcp-implementation-block.md) — maintained Block 20A extension covering the libRSI service/API/server and MCP server surface.
- [`parallel-implementation-plan.md`](parallel-implementation-plan.md) — dependency graph, workstreams, merge waves, interface-freeze points, and parallel execution guidance.
- [`implementation-status.md`](implementation-status.md) — mutable status ledger with ownership, branches/PRs, implementation commits, verification evidence, dates, and update notes for the implementation Blocks, including Block 20A.

## Maintenance rule

Architecture/acceptance requirements belong in the implementation tracker, architecture contract, or a maintained extension Block document. Actual progress claims belong in `implementation-status.md` and should cite exact commits/PRs and retained verification evidence.

A Block is not `verified` merely because its code has been committed or merged; its maintained acceptance criteria must be checked against the current authoritative implementation.
