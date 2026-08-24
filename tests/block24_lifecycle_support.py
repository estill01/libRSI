from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from embedded_service_contract import (  # type: ignore[import-untyped]
    ConformanceFixture,
    HostShape,
)

from librsi import CapabilityRegistry, CapabilityRoute, LibRSI, ManagedBounds
from librsi.conformance.lifecycle import LifecycleObservation, LifecycleProjection
from librsi.service import LibRSIService
from tests.block20_support import target_admission, validation_request
from tests.block21_support import (
    AutomaticValidationExperimenter,
    automatic_validation_admission,
    automatic_validation_registry,
)

LifecycleMode = Literal["succeed", "fail", "wait"]


@dataclass(frozen=True, slots=True)
class SystemLifecycleRequest:
    mode: LifecycleMode


SUCCESS = SystemLifecycleRequest("succeed")
FAILURE = SystemLifecycleRequest("fail")
WAITING = SystemLifecycleRequest("wait")


def _event(host: str, operation: str, state_root: str | None = None) -> dict[str, object]:
    return {"host": host, "operation": operation, "state_root": state_root}


def embedded_executor(request: object) -> LifecycleObservation:
    if type(request) is not SystemLifecycleRequest:
        raise TypeError("embedded lifecycle request is invalid")
    if request.mode == "succeed":
        registry = automatic_validation_registry(AutomaticValidationExperimenter())
        client = LibRSI(capability_registry=registry)
        try:
            run = client.start(validation_request()).run()
            assert run.terminal and run.result is not None
            return LifecycleObservation.succeeded(
                value=run.result,
                event=_event("embedded", "validation", run.state.root),
            )
        finally:
            client.close()
    if request.mode == "fail":
        client = LibRSI()
        try:
            try:
                client.start(object())  # type: ignore[arg-type]
            except TypeError as error:
                return LifecycleObservation.failed(
                    error=str(error),
                    event=_event("embedded", "invalid-request"),
                )
            raise AssertionError("invalid embedded request unexpectedly succeeded")
        finally:
            client.close()
    client = LibRSI(
        capability_registry=CapabilityRegistry(
            routes=(CapabilityRoute("validation-evidence", "experimenter", "external"),)
        )
    )
    try:
        run = client.start(validation_request())
        assert not run.terminal
        return LifecycleObservation.running(
            value=run.state,
            event=_event("embedded", "waiting", run.state.root),
        )
    finally:
        client.close()


def embedded_lifecycle_fixture() -> ConformanceFixture:
    return ConformanceFixture(
        host_factory=lambda lineage: LifecycleProjection(
            shape=HostShape.EMBEDDED,
            lineage=lineage,
            execute=embedded_executor,
        ),
        successful_request=SUCCESS,
        failing_request=FAILURE,
        cancellable_request=WAITING,
    )


def service_lifecycle_fixture(root: Path) -> ConformanceFixture:
    sequence = itertools.count(1)

    def executor(request: object) -> LifecycleObservation:
        if type(request) is not SystemLifecycleRequest:
            raise TypeError("service lifecycle request is invalid")
        directory = root / f"service-{next(sequence)}"
        if request.mode == "succeed":
            provider = AutomaticValidationExperimenter()
            service = LibRSIService.local(
                directory,
                registry=automatic_validation_registry(provider),
            )
            try:
                admission = automatic_validation_admission()
                workflow = validation_request()
                service.submit_target(admission)
                service.validate(workflow, admission_id=admission.admission_id)
                execution = service.run_managed(
                    workflow.validation_id,
                    ManagedBounds(max_actions=2),
                )
                assert execution.terminal
                outcome = service.get_outcome(workflow.validation_id)
                return LifecycleObservation.succeeded(
                    value=outcome["data"]["projection"],
                    event=_event("service", "validation", execution.state_root),
                )
            finally:
                service.close()
        service = LibRSIService.local(directory)
        try:
            if request.mode == "fail":
                try:
                    service.start(object(), admission_id="invalid")  # type: ignore[arg-type]
                except TypeError as error:
                    return LifecycleObservation.failed(
                        error=str(error),
                        event=_event("service", "invalid-request"),
                    )
                raise AssertionError("invalid service request unexpectedly succeeded")
            admission = target_admission()
            workflow = validation_request()
            service.submit_target(admission)
            started = service.validate(workflow, admission_id=admission.admission_id)
            return LifecycleObservation.running(
                value=started["data"],
                event=_event("service", "waiting", started["state_root"]),
            )
        finally:
            service.close()

    return ConformanceFixture(
        host_factory=lambda lineage: LifecycleProjection(
            shape=HostShape.SERVICE,
            lineage=lineage,
            execute=executor,
        ),
        successful_request=SUCCESS,
        failing_request=FAILURE,
        cancellable_request=WAITING,
    )
