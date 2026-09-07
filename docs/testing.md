# Testing libRSI

Install the development dependencies with `python -m pip install -e '.[dev]'`.
The internal provider/consumer integration tests additionally need the exact shared
utility artifacts installed by CI; they are not public runtime dependencies.

For routine edits, run the fast regression lane, then tests directly affected by
the change (including slow tests when the workflow itself changes):

```bash
python -m pytest -m "not slow" --durations=15
python -m pytest tests/test_block7_runtime_store.py --durations=15
```

The second command is an example for changes to runtime storage, not an extra
step for every edit. Aim for one to two minutes for the fast lane on a small
development machine. Inspect the reported slowest tests if it grows. The `slow`
marker is assigned to measured expensive modules in `tests/conftest.py` and to
individual expensive scenarios in otherwise cheap modules. Newly added tests run
in the fast lane unless deliberately classified. Check indirect fixture callers:
a warm full-suite timing can hide an expensive setup that a smaller run must repeat.

Bare `python -m pytest` still runs **every test**. Run the full coverage check for
broad runtime changes and before release, or use the CI workflow's manual trigger:

```bash
python -m pytest -n 2 --dist=loadfile --cov=librsi --cov-branch --cov-report=term-missing --durations=25
```

The full suite retains the 90% global coverage gate, with branch measurement
enabled. A passing fast lane
does not establish full-suite success or coverage. Reuse completed validation for
unchanged code instead of rerunning it at each documentation or commit checkpoint.
The full command uses two `pytest-xdist` workers within one run. Each test executes
once, module-scoped fixtures stay together, and `pytest-cov` combines both workers'
data before checking the global threshold. This uses two available CPU cores
without creating additional CI coverage jobs. Omit `-n 2 --dist=loadfile` on a
single-core machine or when debugging a test in one process.

## CI cadence

| Trigger | Python 3.11 | Python 3.12 and 3.13 |
| --- | --- | --- |
| Pull request | Fast regression | Fast regression |
| Push to main | Full regression with coverage | Fast regression |
| Weekly or manual | Full regression with coverage | Full regression without coverage |

Lint, formatting, and type checks remain enabled. The Python 3.11 job continues to
build, audit, and smoke-test the installed release artifacts. Expensive workflow
regressions can therefore be discovered after merge unless the relevant tests or
manual full CI run were completed on the branch; use those checks for changes to
adoption, recovery, rollback, persistence, or shared workflow behavior.

## Timing and profiling

Use a single representative test before optimizing the runtime. For example:

```bash
python -m cProfile -o /path/to/profile.prof -m pytest -q \
  tests/test_adaptive_loop.py::test_failed_verification_rolls_back_actual_strategy
python -c 'import pstats; pstats.Stats("/path/to/profile.prof").strip_dirs().sort_stats("cumulative").print_stats(25)'
```

Profiling and coverage add overhead; compare equivalent commands and distinguish
test fixture reuse from improvements to actual application runtime. Preserve
independent runs for determinism, restart, and isolation checks. Assertions on the
same immutable result can share a fixture.

## Avoiding repeated work across workflows

Governance, facade, controller, service, and projection tests use the same prepared
improvement in `tests/block17_support.py`. That helper caches immutable serialized
prerequisites by their complete serialized context and governance requirement
(including metadata), with a maximum of 16 entries. Each caller decodes a fresh
result. Tests still execute their own workflow and effects; independent
determinism checks still run independently. A preparation-isolation test checks
that changing one caller's result cannot contaminate another.

The runtime also avoids rebuilding shared record subtrees during one encode or
decode. Decoding checks the complete input, including metadata, and caches only
successfully validated records; claimed roots alone never establish equality.
The decoder retains at most 256 records and 512 small scalar fingerprints.
Canonical JSON uses the native encoder after strict input validation, retaining
the stack-safe fallback for deeply nested values and the existing wire format.

One SQLite store operation shares those codecs across its rows and reuses a
replayed history prefix only when the complete run and event bytes are unchanged.
An append extends that verified prefix instead of replaying it three times.
Schema, row, chain, and post-write integrity checks remain active. The next store
operation uses fresh caches and revalidates stored history, including external
changes. There is no process-wide cache of application decisions or evaluations.

Local Python 3.13 observations on 2026-09-06/07, without profiling or coverage:

| Check | Before | After |
| --- | ---: | ---: |
| Routine fast suite | 158.50 s (557 tests) | 36.72 s (576 tests) |
| Persisted adaptive rollback | 135.96 s | 53.35 s |
| External-controller restart | 0.92 s | 0.39 s |

These are sample timings on a shared GCP host, not performance guarantees.
Coverage-instrumented full-suite results must be measured separately. The fast
suite alone measured 69.28% coverage, so it does not replace the full 90% gate.

The complete coverage validation passed all 869 tests in two disjoint groups
(492 and 377), taking 87.64 minutes for the longer group versus 140.59 minutes
for the previous two-group run. Combined coverage was 90.87%, passing the
unchanged 90% gate. All 849 prior tests remain, with 20 additional reuse,
integrity, and isolation checks. The standard two-worker runner and its coverage
merge were also checked on 35 runtime and packaging tests. The full suite is
still a substantial integration check; routine feedback uses the fast command.
