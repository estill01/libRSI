# Migrating from 0.2.x to 0.3.0

Version `0.3.0` is additive at the tested compatibility boundary. Existing `0.2.0`
exports and deterministic fixtures remain available, but the facade and canonical typed
records are the recommended integration path.

## Recommended replacements

| 0.2.x pattern | 0.3.0 path | Why |
|---|---|---|
| Direct policy composition for ordinary use | `LibRSI.local`, `LibRSI.for_repo`, or plain `LibRSI` | one composition owns persistence and capability wiring without hiding canonical actions |
| `HypothesisPolicy.propose` | `HypothesisPolicy.create` | binds a typed target, causal model, predictions, and immutable identity |
| `HypothesisPolicy.apply_evidence` | `HypothesisPolicy.apply` | validates exact hypothesis/evidence subject lineage |
| `ExperimentPolicy.command_input` | `design_command` then `prepare_command` | criteria and execution input are identity-bound before execution |
| `evaluate_command_result` | `evaluate_command(spec=..., observation=...)` | prevents evaluation-time criterion substitution and requires exact input echo |
| Product-specific orchestration around policies | validation, investigation, improvement, application, and `RSIWorkflow` requests | shares one runtime, result family, replay, and authority model |
| Unstructured model text | `ReasoningRequest` and validated `ReasoningResult` through `StructuredReasoner` | keeps model output proposal-only and lineage-complete |

The four scalar hypothesis/experiment methods remain deprecated wrappers for the
compatibility window and preserve their `0.2.0` roots. They are not removed in `0.3.0`.

## Effects and persistence

Do not migrate host-owned effects into semantic records. Supply implementations through
the granular Inspector, Retriever, Reasoner, Experimenter, Implementer, Reviewer,
Applier, and Verifier protocols. Select automatic, external, human-reserved, or
unavailable posture explicitly for each exact action kind.

Knowledge and runtime history are independent contracts. If adopting the included
SQLite stores, let each owner create and migrate its own schema. Never treat a resumed
runtime state as reusable knowledge or a knowledge record as runtime authority.

## Application and self-change

An accepted candidate is only an `ApplicationHandoff`. Application stays disabled by
default and requires currentness plus explicit host authority. Verification evaluates
the actual state returned by the host; rollback remains a separate action.

For self-change, declare the exact meta-target and class/risk rule, then use `RSIRequest`.
Historical replay, forward shadow, independent review, and activation approval remain
distinct gates. Calling ordinary application APIs does not bypass the approval carried
by a classified handoff.

## Optional dependencies

Public extras are `openai`, `providers`, `server`, `mcp`, and `service`. There is no
public `codex` extra in `0.3.0`: that exact utils-backed producer is unpublished and
unlicensed, and its adapter remains an internal interface-only lane. Do not replace it
with the unrelated registry project sharing its name/version.

Before changing a consumer, run its existing `0.2.x` fixtures, adopt one surface at a
time, and retain exact target, action, result, outcome, and application/verification
roots as migration evidence.
