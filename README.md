![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

**Test proposed changes. Measure improvement. Control what gets adopted.**

libRSI is a Python library for building systems that improve through experiments.
It connects goals, hypotheses, measurements, and candidate selection in bounded,
restartable workflows, with explicit review, verification, and rollback when a
change is applied.

Your application supplies the target, candidate changes, and real measurements.
libRSI checks the evidence against your criteria and records why a change was
accepted, rejected, or left unresolved. You can use it for a single hypothesis
test, a loop that improves an application strategy, or governed **recursive
self-improvement (RSI)**—including changes to the strategy that proposes future
improvements.

**Python 3.11+ · Zero runtime dependencies in the core · Typed API · MIT license**

[Quick start](#quick-start) · [Choose an entry point](#choose-an-entry-point) ·
[How it works](#how-it-works) · [Documentation](#documentation)

## Why libRSI?

Generating a plausible change is only one part of improvement. You also need to
establish whether it helps, whether the evidence still applies, and whether the
change is authorized to take effect. libRSI provides those decision rules and
records so each application does not have to build them from scratch.

- **Make acceptance measurable.** Define a baseline, objectives, minimum effects,
  and guardrails. Compare experimental results against those criteria, including
  uncertainty and conflicting objectives.
- **Keep decisions traceable.** Bind evidence to the exact hypothesis, experiment,
  and target state it describes. Detect stale evidence and retain the lineage
  behind each result.
- **Bound work and resume it.** Set experiment, iteration, and resource limits;
  persist progress with the included SQLite stores; and resume through the
  workflow APIs after an interruption.
- **Control adoption.** Separate candidate preparation and selection from
  application. When application is enabled, verify the state actually produced
  and request rollback if verification fails. Self-change adds comparative trials
  and independent review.
- **Keep your existing stack.** Supply your own models, optimizers, experiment
  runners, storage, and application adapters. The same workflow records support
  embedded Python, external action loops, and optional service interfaces.

## Quick start

### Install from source

The current `0.3.0` release candidate is available from this repository; it is not
a published distribution. Use Python 3.11 or newer, preferably in a virtual
environment:

```bash
git clone https://github.com/estill01/libRSI.git
cd libRSI
python -m pip install .
```

### Run a complete improvement loop

```bash
python examples/embedded_improvement.py --data-dir ./my-first-improvement
```

The example minimizes `abs(4 - x)`, starting at `x = 0`, and requires an error
reduction of at least 2:

| State | Measured error | Decision |
| --- | ---: | --- |
| Baseline: `x = 0` | 4 | Starting point |
| First candidate: `x = 1` | 3 | Rejected: improvement is too small |
| Second candidate: `x = 3` | 1 | Selected: improvement meets the criterion |

Between the two cycles, the example interrupts, closes SQLite, and resumes without
repeating the completed cycle. It returns a selected candidate for the host to
inspect; it performs no application step. After installation, it needs no model,
credentials, or network access.

Use a fresh data directory each time. The
[example source](examples/embedded_improvement.py) shows the host adapter and
actual measurements; the [embedded guide](docs/api.md#small-embedded-improvement)
explains the request, budgets, and restart path. This small deterministic example
demonstrates the workflow, not statistical generalization to a real workload.

### Test a hypothesis in Python

For a smaller starting point, run a local command against explicit criteria:

```python
import sys
from tempfile import TemporaryDirectory

from librsi import LibRSI

with TemporaryDirectory() as workspace, LibRSI.local(workspace) as lib:
    result = lib.test_hypothesis(
        "The local command reports READY",
        command=(sys.executable, "-c", "print('READY')"),
        success_criteria={
            "accepted_exit_codes": [0],
            "stdout_contains": ["READY"],
        },
    )

assert result.evidence.evidence_type == "support"
assert result.observation.exact_input_root == result.experiment.root
```

The result ties the observation and evidence to the exact experiment. Replace the
command and criteria with a check meaningful to your application. The local runner
uses argv without a shell and restricts the working directory; it is not a
filesystem sandbox. See the [local execution limits](docs/api.md#small-embedded-improvement).

## Choose an entry point

| What you want to do | Start here |
| --- | --- |
| Check a claim against evidence | `LibRSI.validate()` — [API guide](docs/api.md#facade-first-use) |
| Test a hypothesis with a local command | `LibRSI.test_hypothesis()` — [runnable example](examples/local_hypothesis.py) |
| Investigate competing explanations | `LibRSI.investigate()` — [API guide](docs/api.md#facade-first-use) |
| Propose, test, and select a bounded improvement | `LibRSI.improve()` — [embedded example](examples/embedded_improvement.py) |
| Improve a strategy from ordinary task feedback | `AdaptiveLoop` — [adaptive operation guide](docs/adaptive-operation.md) and [consumer template](examples/adaptive_strategy.py) |
| Serve tasks while a strategy learns in the background | `ConcurrentAdaptiveLoop` — [concurrent operation guide](docs/concurrent-adaptive-operation.md) |
| Govern changes to the improvement process itself | `LibRSI.recurse()` — [self-change integration contract](docs/consumer-integration.md) |
| Compare completed trials using host-owned state | [Stateless JSON comparison](docs/stateless-comparison.md) — no local store required |
| Drive actions from an existing agent or service | `LibRSI.start()` — [external protocol](docs/external-agent-protocol.md) and [service interfaces](docs/service-protocol.md) |

`AdaptiveLoop` connects measured task outcomes to proposed strategy revisions. It
can retain unsuccessful attempts, request reflection, and run bounded follow-ups;
an adopted, verified revision becomes the strategy used by the next ordinary task.
The [proposal-generator example](examples/failure_informed_proposals.py) demonstrates
improving the generator itself, with a control comparison and subsequent use.

`ConcurrentAdaptiveLoop` keeps ordinary requests on admitted strategy revisions
while one learning pass runs. It publishes a replacement only after native
verification and retains the producing revision for requests that span publication.
The host supplies the executor and scheduling; the local backend uses one shared
store instance and a dedicated profile.

## How it works

An improvement run follows four stages:

1. **Define success.** Identify the target and baseline, then specify objectives,
   constraints, guardrails, and stopping rules in an `EvaluationContract`.
2. **Collect evidence.** Your host proposes hypotheses, prepares candidates, and
   runs experiments. libRSI checks that returned records refer to the correct
   inputs and target state.
3. **Decide from measurements.** Deterministic policies evaluate the results.
   Depending on the workflow, a result may support or contradict a claim, remain
   inconclusive, or select one candidate, a Pareto set, or none.
4. **Apply only when enabled.** The host explicitly authorizes application and
   supplies the effect adapters. libRSI evaluates fresh measurements of the actual
   resulting state and coordinates verification or rollback. Declared self-change
   targets require additional governance before activation.

The host owns execution and effects; libRSI owns the evidence and decision
contracts. Model output remains a proposal. A successful command or a prepared
candidate does not, by itself, establish improvement.

`LibRSI.local()` provides SQLite persistence, a local command runner, filesystem
inspection, artifacts, and logging. `LibRSI.for_repo()` adds repository-oriented
convenience. Plain `LibRSI(...)` accepts host-supplied components, and
`librsi.expert` exposes lower-level policies, workflows, and stores. All use the
same canonical runtime records.

### Operating boundaries

- **Measurements come from your host.** libRSI checks their structure, lineage,
  and applicability; it cannot establish that your metric captures what you value
  or independently authenticate every supplied measurement.
- **Application and activation default to disabled.** An accepted improvement
  returns a handoff.
  Enabling effects requires the appropriate host capabilities, current target
  state, and authority. Operational failure remains distinct from evidence
  against a hypothesis.
- **Local operation assumes small histories and one owner.** `AdaptiveLoop`
  serializes tasks and learning. The opt-in concurrent facade permits many serving
  threads while retaining one learning owner. External calls can repeat before
  their results are saved; make those effects idempotent and follow the
  [restart guidance](docs/adaptive-operation.md#restart-history-and-boundaries) or
  [concurrent ownership contract](docs/concurrent-adaptive-operation.md#ownership-persistence-and-limits).
- **Your application owns scheduling and isolation.** libRSI supplies the
  improvement workflows; the host supplies process containment, credentials,
  execution limits, and deployment.

## Documentation

| Guide | What it covers |
| --- | --- |
| [Public API](docs/api.md) | Local setup, workflow methods, expert APIs, typing, and execution limits |
| [Adaptive operation](docs/adaptive-operation.md) | Task feedback, strategy revisions, failed attempts, independent review, and adoption |
| [Concurrent operation](docs/concurrent-adaptive-operation.md) | Serving during learning, durable task admissions, qualified publication, and local ownership |
| [Consumer integration](docs/consumer-integration.md) | Mapping your system, measurements, and effects into libRSI contracts |
| [Stateless comparison](docs/stateless-comparison.md) | Comparing canonical trial records over JSON without a runtime store |
| [Providers](docs/providers.md) | Optional model-backed reasoning and provider boundaries |
| [External agent protocol](docs/external-agent-protocol.md) | Owning the action loop from another process or agent |
| [Service protocol](docs/service-protocol.md) | Managed execution, CLI, HTTP, MCP, authentication, and request bounds |
| [Module map](src/librsi/README.md) | Core architecture, package responsibilities, and lower-level integration |

HTTP and MCP are optional extras, separate from the dependency-free core:

```bash
python -m pip install '.[server]'   # FastAPI/HTTP
python -m pip install '.[mcp]'      # stdio and Streamable HTTP MCP
python -m pip install '.[service]'  # both
```

## Development

From a source checkout:

```bash
python -m pip install -e '.[dev]'
python -m pytest -m "not slow" \
  --ignore=tests/test_block22_providers.py \
  --ignore=tests/test_block24_system_dogfoods.py
```

The omitted suites require exact internal `estill01/utils` artifacts. They are
separate CI inputs, not public runtime dependencies, and are not covered by
libRSI's MIT license. See [provider setup](docs/providers.md) for that boundary.

The [testing guide](docs/testing.md) explains fast and full validation, affected
slow tests, and the full-suite 90% coverage gate with branch measurement enabled.
Maintainers can follow the [implementation tracker](docs/tracker.md),
[release gate](docs/release-gate.md), and [changelog](CHANGELOG.md). Existing users
should also read the [migration guide](docs/migration-0.2.md).

## License

libRSI-owned source is available under the [MIT License](LICENSE). See the
[license decision record](docs/license-decision.md) for the release boundary and
separate upstream artifact exclusions.
