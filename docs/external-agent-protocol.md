# External-agent protocol

The `librsi` CLI is a structured projection over libRSI's canonical records and
append-only runtime. It does not infer state from prose, execute shell commands,
or grant application authority.

Before starting managed work, submit one canonical `TargetAdmission`. The
admission binds an exact target snapshot, one objective within its evaluation
contract, capability postures, current sourced evidence, the required type of
application authority, and hard resource ceilings. The
`application_requirement` describes authority that a later governed workflow
must present; submitting an admission does not itself grant that authority.

```console
librsi --data-dir .librsi target submit --input admission.json
librsi --data-dir .librsi validate --request validation.json --admission target-1
librsi --data-dir .librsi next validation-1
librsi --data-dir .librsi submit validation-1 --input result.json --authority external
librsi --data-dir .librsi outcome validation-1
```

`investigate`, `improve`, and `rsi` use the same `--request` and `--admission`
shape. `status`, `next`, `resume`, and `outcome` accept the canonical run ID.
Every successful command emits exactly one JSON object on stdout. Errors emit
one `librsi.external-error/v1` object on stderr and exit with status 2.

`data.terminal` follows the canonical run status, including failure and supported
cancellation. Status responses include recorded `failures` when present. Successful
workflow outcomes retain their existing `data.projection` shape. If a failed or
cancelled workflow has no domain result, `outcome` instead returns
`data.projection: null` together with `workflow`, `status`, the canonical runtime
`outcome`, and recorded `failures`. This reports operational termination without
inventing a successful improvement or evidence. Repeated managed execution of a
terminal run performs no further actions.

For example, a successful target submission uses the common envelope and does
not claim a run or runtime state:

```json
{
  "$schema": "librsi.external-agent/v1",
  "schema_version": 1,
  "operation": "target.submit",
  "run_id": null,
  "state_root": null,
  "data": {
    "admission_id": "target-1",
    "admission_root": "0000000000000000000000000000000000000000000000000000000000000000",
    "target_snapshot_root": "1111111111111111111111111111111111111111111111111111111111111111"
  }
}
```

The roots above are illustrative placeholders; emitted roots are hashes of the
exact canonical records.

The successful envelope is `librsi.external-agent/v1`. Its `state_root` is the
root of the authoritative runtime state, never a CLI-owned shadow state. A
`next` response includes the exact pending action, target snapshot, evaluation
constraints, evidence references, admitted capability posture, and a result
schema whose ID and action root are bound to that one action.

Python callers can inspect the maintained schemas directly:

```python
from librsi import (
    action_result_schema,
    external_response_schema,
    target_admission_schema,
)
```

`target_admission_schema(admission)` is bound to one exact canonical admission;
`action_result_schema(action)` is bound to one exact pending action. Both are
closed Draft 2020-12 schemas suitable for validating the corresponding JSON
document before canonical decoding. Result schemas also bind the action-kind
payload record, contextual request/command references, output record types, and
failure shape. Canonical decoding and the workflow validator then enforce
record roots and derived cross-record relationships before runtime mutation.

Canonical input documents may be produced with `serialize_record(record)`.
Unknown schemas, missing fields, extra noncanonical fields, wrong action/run
identities, duplicate advancement, stale snapshots, and mismatched authority
fail closed. Local durability uses separate admission, runtime, and knowledge
SQLite stores under `--data-dir`; reopening the controller or invoking another
CLI process reconstructs the same frontier from those canonical stores.

HTTP, MCP, natural-language orchestration, hosted providers, and application
authority are intentionally outside this protocol layer.
