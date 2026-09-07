# Development validation

Use `python -m pytest -m "not slow" --durations=15` for routine implementation
iterations, plus targeted tests for changed behavior. Include affected slow tests
when changing adoption, recovery, rollback, persistence, or shared workflows.
See [docs/testing.md](docs/testing.md) for the fast/full split and CI cadence.

Do not repeat the full suite merely because a commit, documentation update, or
implementation-block boundary was reached. Reuse passing evidence when its code
and test inputs are unchanged. Full regression with the unchanged 90% coverage
gate remains appropriate for broad runtime changes and release validation.
Use the two-worker full command in `docs/testing.md` on the GCP environment;
keep each test in one worker and combine coverage before enforcing the gate.

When bringing these test-efficiency changes into an active run, preserve ongoing
validation and its evidence. A test-selection or documentation change alone does
not require restarting a full regression run. Record what revision was tested,
and verify changed test fixtures separately before reusing earlier results.
