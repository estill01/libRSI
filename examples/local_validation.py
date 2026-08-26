"""Run with: python examples/local_validation.py"""

from __future__ import annotations

from tempfile import TemporaryDirectory

from librsi import Evidence, LibRSI

with TemporaryDirectory(prefix="librsi-validation-") as workspace, LibRSI.local(workspace) as lib:
    claim = lib.claim("The local package can be imported", kind="behavioral")
    snapshot = lib.snapshot()
    evidence = tuple(
        Evidence(
            evidence_type="support",
            data={"sample": sample},
            subject_refs=(claim.ref,),
            source_refs=(claim.ref,),
            target_snapshot=snapshot,
            weight=1.0,
        )
        for sample in (1, 2)
    )
    result = lib.validate(claim, target_snapshot=snapshot, evidence=evidence)

print(result.disposition)
