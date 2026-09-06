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
python -m pytest --cov=librsi --cov-branch --cov-report=term-missing --durations=25
```

The full suite retains the 90% global branch-coverage gate. A passing fast lane
does not establish full-suite success or coverage. Reuse completed validation for
unchanged code instead of rerunning it at each documentation or commit checkpoint.

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
