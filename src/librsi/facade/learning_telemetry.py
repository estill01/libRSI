"""Scoped host-call measurements, not resource accounting or quality evidence."""

from __future__ import annotations

from time import perf_counter, process_time


def clock() -> tuple[float, float]:
    return perf_counter(), process_time()


def elapsed(start: tuple[float, float], *, scope: str) -> dict[str, object]:
    return {
        "scope": scope,
        "wall_seconds": max(0.0, perf_counter() - start[0]),
        "process_cpu_seconds": max(0.0, process_time() - start[1]),
        "provider_usage": None,
        "child_cpu_seconds": None,
        "additive": False,
    }
