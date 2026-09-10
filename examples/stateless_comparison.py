"""Measured numeric comparison without stores or activation.

Emit a request with --request, or print the advisory response by default.
The numeric target and measurement code are shared with the embedded example.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from embedded_improvement import compare, error, improvement_request

from librsi import (
    CandidateSnapshot,
    Evidence,
    InterventionImplementationRequest,
    InterventionSpec,
    TargetSnapshot,
)
from librsi.comparison.external import REQUEST_SCHEMA, evaluate_request


def request_payload() -> dict[str, Any]:
    request = improvement_request()
    hypothesis = request.initial_hypotheses[0]
    evidence = Evidence(
        evidence_type="support",
        data={"baseline_error": error(0), "probe_error": error(1)},
        subject_refs=(hypothesis.ref,),
        source_refs=(request.baseline.ref,),
        target_snapshot=request.baseline,
        weight=1,
    )
    batches = []
    for x in (1, 3):
        intervention = InterventionSpec.create(
            intervention_id=f"numeric-x-{x}",
            baseline=request.baseline,
            kind="parameter-change",
            specification={"x": x},
            rationale=("Compare a smaller and larger change in the measured direction",),
            supporting_refs=(hypothesis.ref,),
            evidence=(evidence,),
            expected_effects={"error": "decrease"},
            risks=("Change may be insufficient",),
            constraints=(),
            validation_plan={"repetitions": 2},
            rollback_expectations={"restore": request.baseline.revision},
        )
        candidate = CandidateSnapshot.prepared(
            request=InterventionImplementationRequest.for_intervention(
                intervention,
                candidate_id=f"x={x}",
            ),
            snapshot=TargetSnapshot(
                target=request.baseline.target,
                revision=f"x={x}",
                state={"x": x},
            ),
        )
        batches.append(compare(request.contract, candidate).to_dict())
    return {
        "schema": REQUEST_SCHEMA,
        "selection_id": "stateless-numeric-example",
        "current_snapshot": request.baseline.to_dict(),
        "contract": request.contract.to_dict(),
        "risk_policy": request.risk_policy.to_dict(),
        "batches": batches,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", action="store_true", help="Emit the canonical request only")
    args = parser.parse_args()
    payload = request_payload()
    print(json.dumps(payload if args.request else evaluate_request(payload), allow_nan=False))
