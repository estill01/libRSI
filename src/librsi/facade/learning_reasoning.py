"""One durable bounded host reasoning call, shared by reflection and proposals."""

from __future__ import annotations

from ..reasoning import (
    ReasoningBackend,
    ReasoningRequest,
    ReasoningResult,
    ReasoningResultValidator,
    make_reasoning_action,
    make_reasoning_action_result,
    make_reasoning_failure,
    reasoning_result_from_action_result,
)
from ..records import Outcome
from ..runtime import RuntimeEngine, RuntimeFailure
from .learning_host import LearningHost
from .learning_requests import reasoning_run
from .learning_workflows import recorded_action


def reason(
    host: LearningHost, backend: ReasoningBackend, request: ReasoningRequest
) -> ReasoningResult | Outcome:
    run = reasoning_run(request)
    state = host.store.runtime.resume(run.run_id)
    if state is None:
        update = RuntimeEngine.start(run)
        assert update.transition is not None
        state = host.store.runtime.append(update.transition)
    if state.run != run:
        raise ValueError("reasoning run inputs have drifted")
    if state.status == "active" and not state.results:
        action = make_reasoning_action(
            run=run,
            action_id=request.request_id,
            request=request,
            budget_reservation={"calls": 1},
        )
        update = RuntimeEngine.request(state, action)
        assert update.transition is not None
        state = host.store.runtime.append(update.transition)
    if state.status == "waiting":
        action = state.pending_actions[0]

        def execute(item):
            try:
                proposal = backend.respond(request)
                result = make_reasoning_action_result(
                    action=item, result=proposal, resource_usage={"calls": 1}
                )
                if request.kind == "hypothesis-generation":
                    hypotheses = proposal.content["hypotheses"]
                    if not 2 <= len(hypotheses) <= host.policy.max_candidates:
                        raise ValueError("proposal count exceeds the candidate allowance")
                    roots = set()
                    for hypothesis in hypotheses:
                        model = hypothesis["causal_model"]
                        if set(model) != {"configuration"}:
                            raise ValueError("strategy proposal must contain only configuration")
                        configuration = model["configuration"]
                        host.adapter.validate_configuration(configuration)
                        snapshot = host.store.snapshot(configuration)
                        if snapshot == host.baseline or snapshot.root in roots:
                            raise ValueError("proposals must be distinct revisions of the baseline")
                        roots.add(snapshot.root)
                return result
            except Exception as error:
                return make_reasoning_failure(
                    action=item,
                    resource_usage={"calls": 1},
                    failure=RuntimeFailure(
                        classification="invalid-result"
                        if isinstance(error, (ValueError, TypeError, KeyError))
                        else "execution",
                        message=str(error) or type(error).__name__,
                        retryable=False,
                    ),
                )

        result = recorded_action(host.store, host.pass_id, action, execute)
        ReasoningResultValidator().validate(state, result)
        update = RuntimeEngine.submit(state, result)
        assert update.transition is not None
        state = host.store.runtime.append(update.transition)
    if state.status == "failed":
        assert state.outcome is not None
        return state.outcome
    proposal = reasoning_result_from_action_result(state.results[-1])
    if state.status != "completed":
        update = RuntimeEngine.complete(
            state,
            Outcome(
                intent=request.ref,
                status="proposed",
                target_snapshot=host.baseline,
                conclusions=(
                    "Bounded strategy revisions proposed; acceptance remains unevaluated"
                    if request.kind == "hypothesis-generation"
                    else "Bounded reflection proposed; acceptance remains unevaluated",
                ),
                lineage=(proposal.ref,),
            ),
        )
        assert update.transition is not None
        host.store.runtime.append(update.transition)
    return proposal
