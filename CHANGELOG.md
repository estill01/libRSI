# Changelog

All notable changes are recorded here. Version `0.3.0` is a release candidate and has
not been published or tagged by this tracker run.

## 0.3.0 - Unreleased

### Added

- A facade-first `LibRSI` composition for local, embedded, managed, and external action
  loops over the same canonical runtime.
- Typed validation, competing-hypothesis investigation, intervention, comparative
  evaluation, improvement, application/verification/rollback, and governed self-change
  workflows.
- Replaceable knowledge/runtime persistence, capability routing, provider-neutral
  reasoning, stable external outcome projections, CLI, HTTP, MCP, and consumer
  conformance surfaces.
- Deterministic non-software and complete system dogfoods proving domain neutrality and
  embedded/managed/external semantic equivalence.

### Changed

- The recommended entry surface is `LibRSI`; the deterministic policy kernel remains
  available under `librsi.expert` and through the retained top-level compatibility
  exports.
- Public extras contain only published third-party dependencies. The exact utils-backed
  Codex and conformance packages remain internal CI inputs and are absent from release
  dependency metadata.
- Optional HTTP and MCP package exports and `--help` entrypoints load their third-party
  stacks lazily, so the base wheel remains zero-dependency.
- libRSI-owned source and distribution artifacts now carry the MIT License; separately
  owned unpublished utils artifacts remain excluded from the public distribution.

### Compatibility

- The `0.2.0` public export fixture and deterministic identity fixtures remain passing.
- Deprecated scalar hypothesis/experiment wrappers remain available for the `0.2.x`
  migration window; new integrations should use canonical typed records and the facade.

## 0.2.0

- Initial deterministic policy, record, hypothesis, experiment, selection, review, and
  selector-governance library.
