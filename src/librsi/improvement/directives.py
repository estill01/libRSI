"""Canonical search-directive derivation shared by every improvement authority."""

from __future__ import annotations

from ..records import RecordRef
from .records import ImprovementIteration, SearchDirective

_SEARCH_REASONS = {
    "initial": "begin with declared competing hypotheses",
    "narrow": "refine a promising branch",
    "broaden": "replace falsified or unproductive hypotheses",
}


def canonical_search_directive(
    *,
    iteration: int,
    direction: str,
    previous_iteration: RecordRef | None,
) -> SearchDirective:
    """Construct the sole canonical directive for declared frontier fields."""

    if direction not in _SEARCH_REASONS:
        raise ValueError(f"unsupported search direction: {direction}")
    if iteration == 1:
        if direction != "initial" or previous_iteration is not None:
            raise ValueError("the first search directive must be the initial frontier")
    elif direction == "initial" or previous_iteration is None:
        raise ValueError("later search directives require a prior iteration and learned direction")
    elif (
        not isinstance(previous_iteration, RecordRef)
        or previous_iteration.record_type != "improvement_iteration"
    ):
        raise TypeError("later search directives require an ImprovementIteration predecessor")
    return SearchDirective(
        iteration=iteration,
        direction=direction,
        reason=_SEARCH_REASONS[direction],
        previous_iteration=previous_iteration,
        lineage=() if previous_iteration is None else (previous_iteration,),
    )


def next_search_directive(
    previous: ImprovementIteration | None,
) -> SearchDirective:
    """Derive the canonical next directive from its exact predecessor."""

    if previous is not None and type(previous) is not ImprovementIteration:
        raise TypeError("search direction history requires an ImprovementIteration predecessor")
    return canonical_search_directive(
        iteration=(1 if previous is None else previous.proposal.request.directive.iteration + 1),
        direction="initial" if previous is None else previous.next_direction,
        previous_iteration=None if previous is None else previous.ref,
    )
