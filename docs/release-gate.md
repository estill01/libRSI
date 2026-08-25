# 0.3.0 release gate

Status: technical candidate in progress; publication is not authorized.

## Candidate invariants

- base wheel has zero dependencies and imports without optional provider/service stacks;
- public extras contain only published third-party requirements and no Git/path URL;
- exact utils producer artifacts are CI-only inputs, never embedded or required by the
  wheel, sdist, examples, or dependency metadata;
- `librsi.__version__`, project metadata, wheel metadata, sdist directory, provider
  identity, and runtime-manifest component version agree on `0.3.0`;
- `librsi.__all__` has no duplicates or missing attributes and retains the executable
  `0.2.0` compatibility fixture;
- wheel contains every package, `py.typed`, JSON schema/compatibility artifact, and all
  three console entrypoints;
- sdist contains README, changelog, public docs, migration guide, decision packet, and
  executable examples;
- both examples and all three entrypoint help paths execute through an isolated wheel
  installation with the checkout excluded from `sys.path`.

## Required evidence

Ruff, formatting, mypy, full branch-covered tests, wheel/sdist audit, installed examples,
independent semantic review, exact-head CI across Python 3.11–3.13, and merge evidence
must all pass. Artifact hashes and the final license posture are recorded only after the
candidate tree and direct-user license choice are frozen.

PyPI publication, GitHub Release creation, release tagging, deployment, and announcement
remain outside this gate and require separate authority.
