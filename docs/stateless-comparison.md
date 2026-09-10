# Stateless comparison for distributed hosts

Hosts that already own durable state and execution can compare completed trials
without constructing `AdaptiveLoop`, a local profile, or a libRSI runtime store:

```sh
python -m librsi.comparison < request.json > response.json
```

Generate a measured, offline numeric request with the maintained example:

```sh
python examples/stateless_comparison.py --request > request.json
python -m librsi.comparison < request.json > response.json
```

It compares x=1 and x=3 against x=0 using actual distance from 4, sharing the
measurement implementation with the embedded example. It demonstrates the wire
contract, not improved production quality or statistical generalization.

This zero-dependency process reads one JSON document from stdin, recomputes the
ordinary `ComparativeSelectionPolicy.select` decision, writes one JSON document
to stdout, and exits. It performs no experiments, provider calls, application,
rollback, scheduling, or persistence. Repeating an identical request in another
process returns the same result. This is a lower-level integration, not a
distributed `AdaptiveLoop` implementation. A stateful adaptive loop still needs
qualified `LearningStore` and `RuntimeStore` implementations and a host that
serializes/fences every operation on each profile.

## Request and response

The request has exactly these fields. Every record is its complete canonical
`to_dict()` representation, including root and lineage; references alone do not
replace the records:

```python
request = {
    "schema": "librsi.comparison.request.v1",
    "selection_id": selection_id,
    "current_snapshot": current_snapshot.to_dict(),
    "contract": evaluation_contract.to_dict(),
    "risk_policy": risk_policy.to_dict(),
    "batches": [batch.to_dict() for batch in candidate_trial_batches],
}
```

Use `from librsi.comparison.external import evaluate_request` and
`response = evaluate_request(request)` when a process transport is unnecessary.

The response contains `schema: "librsi.comparison.response.v1"`,
`status: "succeeded"`, `request_root` (the canonical digest of the complete
request), `activation_authorized: false`, and the full canonical
`SelectionDecision` in `decision`. Assessment and selection are recomputed by
the existing owner. The transport does not trust a supplied acceptance flag.
Rejected or inconclusive evidence is a successfully evaluated request, not an
execution failure. Its decision may select no candidate. Multiple incomparable
objectives may produce a Pareto set instead of a single winner.

The current snapshot must exactly equal the contract baseline, and every batch
must use the same contract. The library checks canonical record integrity,
candidate uniqueness, experiment/evidence comparability, configured independent
review, uncertainty, objectives, and guardrails through its ordinary decoders
and policies. It does not independently observe the host's current state or
authenticate the supplied measurements. Content hashes are not authority or
proof of measurement quality.

Malformed requests exit with code 2 and a JSON failure containing
`error.code: "invalid_comparison_request"`. The process does not echo input or
exception details. The Python function raises for invalid inputs. The process
accepts at most 8 MiB and 32 batches, rejects duplicate JSON keys and nonfinite
numbers, and uses no configuration files. Hosts must also bound wall time,
memory, output, and experiment costs through their executor.

## Host ownership

Before dispatch, hydrate the current baseline, contract, risk policy and trial
evidence under the host's normal visibility and governing context. Store the
request and response as ordinary host artifacts/results, retaining exact record
roots alongside host provenance. Pin the installed libRSI revision or wheel
hash in the execution environment; a version label alone does not identify a
source revision of an unpublished candidate.

Before adopting any recommendation, the actual host effect owner must rehydrate
and validate current evidence and its applicability under the required authority.
A `selected` decision neither grants activation nor proves a held-out comparison
that the host did not conduct. Preserve the difference between candidate
preparation, measured improvement, independent review, and authorized activation.
Independent workers may evaluate requests concurrently because this operation
has no active-strategy pointer. They must not create independent local strategy
stores and treat those as a shared source of truth.
