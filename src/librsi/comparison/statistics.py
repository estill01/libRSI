"""Small deterministic statistical primitives owned by comparative selection."""

from __future__ import annotations

import math
from collections.abc import Sequence

from .records import UncertaintyInterval


def mean_interval(
    values: Sequence[float],
    *,
    confidence_multiplier: float,
) -> UncertaintyInterval:
    """Return a visible mean +/- multiplier * standard-error interval."""

    items = tuple(float(item) for item in values)
    if not items or any(not math.isfinite(item) for item in items):
        raise ValueError("mean intervals require finite samples")
    if not math.isfinite(confidence_multiplier) or confidence_multiplier < 0.0:
        raise ValueError("confidence multiplier must be finite and nonnegative")
    estimate = sum(items) / len(items)
    if len(items) == 1:
        margin = 0.0
    else:
        variance = sum((item - estimate) ** 2 for item in items) / (len(items) - 1)
        margin = confidence_multiplier * math.sqrt(variance / len(items))
    return UncertaintyInterval(
        estimate=estimate,
        lower=estimate - margin,
        upper=estimate + margin,
        sample_count=len(items),
    )


def favorable_effect(
    baseline: UncertaintyInterval,
    candidate: UncertaintyInterval,
    *,
    direction: str,
) -> UncertaintyInterval:
    """Express effect so larger is always better, retaining conservative bounds."""

    if direction == "increase":
        estimate = candidate.estimate - baseline.estimate
        lower = candidate.lower - baseline.upper
        upper = candidate.upper - baseline.lower
    elif direction == "decrease":
        estimate = baseline.estimate - candidate.estimate
        lower = baseline.lower - candidate.upper
        upper = baseline.upper - candidate.lower
    elif direction == "target":
        estimate = -abs(candidate.estimate - baseline.estimate)
        distances = (
            -abs(candidate.lower - baseline.estimate),
            -abs(candidate.upper - baseline.estimate),
        )
        lower = min(distances)
        upper = 0.0 if candidate.lower <= baseline.estimate <= candidate.upper else max(distances)
    else:
        raise ValueError(f"unsupported metric direction: {direction}")
    return UncertaintyInterval(
        estimate=estimate,
        lower=lower,
        upper=upper,
        sample_count=min(baseline.sample_count, candidate.sample_count),
    )
