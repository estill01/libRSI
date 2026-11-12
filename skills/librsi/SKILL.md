---
name: librsi
description: Use libRSI to improve prompts, configurations, code strategies, or agent workflows through measured experiments. Use when asked to optimize with libRSI, investigate failures, or improve an optimizer's own proposal strategy.
---

# libRSI

Turn the user's goal into a bounded, reproducible improvement experiment. You are
the reasoning agent: inspect relevant feedback, generate hypotheses and candidate
changes, and use libRSI to record trials and evaluate whether changes earned
adoption. A model proposal is not evidence of improvement.

## Start with the user's system

Identify the target, how to execute it, existing evaluations and failure examples,
and the changes the user allows. Reuse the application's evaluator where it
measures the goal well. State a measurable objective, baseline, minimum worthwhile
gain, regression constraints, and a small trial/time/model budget before searching.
If the goal lacks an observable success criterion or necessary access, ask for the
missing information; continue any independent setup.

Read training feedback to generate competing explanations and concrete candidate
changes. Keep final evaluation examples and labels out of proposal context. Use
matched baseline/candidate workloads and count all attempts, including failures
and rejections. With stochastic models, use repeated samples and report variation.
Do not tune against a final test set or present a toy check as a production gain.

## Choose the existing integration, or start locally

Prefer an already configured libRSI MCP/HTTP service. Otherwise use Python 3.11+
and a project environment; check for an existing libRSI installation first. The
source installation works without a PyPI release:

```bash
python -m pip install 'libRSI @ git+https://github.com/estill01/libRSI.git@main'
python -c 'import librsi; print(librsi.__version__)'
librsi --help
```

Pin the resolved Git commit for a repeatable run. Installing this skill does not
install the Python package or configure a server. Respect the project's storage
and environment conventions. Do not replace its dependency environment.

Use the installed version's source and documentation when available. Otherwise
read the relevant guide below from the same Git revision; replace `main` in URLs
with that revision. These are instructions and examples, not preconfigured access
to the user's application.

### Local prompts, settings, and repeatable agent strategies

Read [adaptive operation](https://github.com/estill01/libRSI/blob/main/docs/adaptive-operation.md)
and the [complete adapter template](https://github.com/estill01/libRSI/blob/main/examples/adaptive_strategy.py).
Implement the target-specific pieces using those maintained signatures:

- `LearningAdapter`: validates the allowed configuration and executes/scores it
  through `evaluate(configuration, case) -> TaskMeasurement`.
- `ReasoningBackend`: proposes distinct replacement configurations from observed
  failures. You can generate these in the current coding-agent session and return
  them through `ReasoningResult.propose`, or connect an existing model backend.
  Do not request a second API key merely to generate proposals you can supply.
- `Reviewer`: evaluates the actual native review evidence with a separate reviewer
  identity; an identity string alone does not establish independent human review.
- `LocalLearningStore` and `LearningPolicy`: persist the configuration, feedback,
  bounded learning passes, and actual adoption result.

Use `AdaptiveLoop.run_task()` for measured training feedback and `learn()` for
candidate evaluation, shadow review, and optional verification. Use fresh,
disjoint training, shadow and verification cases as required by the API. The
numeric template shows wiring; replace its task and evaluator with the user's
workload. Keep the baseline unchanged when evidence is inconclusive or worse.

`activate=False` evaluates without switching the active strategy. Use
`activate=True` when activation is within the user's authorized scope; it still
requires native acceptance and verification. Changing a local strategy pointer
does not deploy the user's application.

### Shared service and broad goals

Read [goal intake](https://github.com/estill01/libRSI/blob/main/docs/goal-intake.md)
and [service protocol](https://github.com/estill01/libRSI/blob/main/docs/service-protocol.md).
If intake is configured, list adapters with `librsi_intake_adapters` (MCP) or
`GET /v1/intake/adapters` (HTTP). Submit the goal and actual observed context with
`librsi_intake` or `POST /v1/intake`, using a unique `request_id`.

Intake's configured LLM selects a registered adapter, operationalizes the goal,
and generates hypotheses. A `needs-information` receipt gives questions to answer
in a new request. A `started` receipt gives the native `run_id`; it does not mean
the experiments have run or the target has improved. Retry identical input with
the same ID after a transport interruption; check the saved receipt first.

Advance the run using its exact next-action/result schema. External routes mean
you execute the requested experiment and submit actual typed results. Managed
passes require configured execution providers. Read the terminal outcome before
reporting success. The service serializes operations; it is not a parallel queue.
For an unsupported target, implement a host adapter and real evaluator before
submitting it. A broad goal alone does not supply execution or measurement access.

For lower-level workflows without intake, use the
[external-agent protocol](https://github.com/estill01/libRSI/blob/main/docs/external-agent-protocol.md):
serialize canonical records, submit a `TargetAdmission`, start the workflow,
consume `next`, submit the schema-bound result, then inspect `outcome`. Generate
records with public constructors and `serialize_record`; do not invent JSON
schemas, hashes, evidence, or application authority.

### Improve the improver

Make the tunable target the proposer's instructions, search policy, or workflow
configuration. Measure the quality of the candidates that it subsequently
produces on fresh downstream tasks. Compare with the unchanged proposer under
matched candidate/model budgets, counting the extra optimization effort. See the
[recursive example](https://github.com/estill01/libRSI/blob/main/examples/benchmark_recursive_search.py).
An extra recursive level must earn its cost; a rejected meta change is a valid
result. This changes exposed strategies, not model weights or libRSI's core code
unless those are separately implemented and authorized targets.

## Leave a usable result

Return the baseline and candidate scores, sample counts and variation, held-out
result, effort (trials, model calls/tokens when available, elapsed time), native
disposition, and whether activation actually occurred. Link the reproducible
runner/configuration and retained evidence. If nothing improved, say so. Treat
library acceptance rules as their documented rules, not a universal statistical
significance guarantee. Stop at the budget or missing external dependency; retain
the run ID and exact next action so the work can resume.
