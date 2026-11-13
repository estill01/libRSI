![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

**Turn a model's improvement ideas into measured, recoverable changes.**

Define what good means, connect a model and supply an adapter that runs your
system. libRSI records experiments, compares alternatives, checks held-out cases,
and manages review, adoption, verification and rollback.

The same loop can improve **the improver**: revise its instructions, measure
whether it produces better systems, and use accepted instructions on future work.

**Python 3.11+ · Dependency-free core · Typed API · MIT**

## Base → libRSI optimization → meta optimization

A runnable example reduces setup costs in repeating **14-job production
schedules**. One Astra call proposes two search programs; the host executes them with a fixed
**256 cost evaluations per workload**. Scheduler execution uses no LLM.

Each optimization arm has **32 independent, complete libRSI runs**, evaluated on
**512 unseen synthetic workloads**. Both start from the same original scheduler.
The meta arm first optimizes the improver's instruction, then uses the retained
improver to optimize a fresh copy of that original scheduler.

![Actual retained-system improvements and model effort; gpt-6-astra high at both optimization levels](docs/assets/native-sequence-results.png)

| Case | Model driving optimization | Retained setup-cost reduction | Model request attempts for this arm |
| --- | --- | ---: | ---: |
| Base scheduler | None | 0% | 0 |
| libRSI optimizes the base | `gpt-6-astra`, high reasoning | 15.94% | 32 + 1 timeout retry |
| Meta → libRSI (original improver retained) | `gpt-6-astra`, high reasoning at **both levels** | 15.99% | 73 development + 32 final + 1 timeout retry |

The meta pass **rejected both revisions and kept the original improver**. The
third case uses the same instruction as ordinary optimization; its difference
reflects independent model samples, not a learned meta improvement.

After-meta minus ordinary: **+0.05 percentage points**, with a crossed-bootstrap
95% interval of **[-0.32, +0.42]**. This interval accounts for model-draw and
workload variation, conditional on one meta-development run. The study compares
outcomes with different development budgets; it does not establish compute efficiency.

**Using the proposed meta revision anyway did worse:** a separate 32-run diagnostic
achieved **15.52%**, or **−0.41 percentage points** versus ordinary libRSI
(exploratory 95% interval **[−0.82, −0.02]**). This result uses the revised
instruction, but it is not an accepted libRSI meta update.

Both reasoning levels use **OpenAI `gpt-6-astra`, high, via Codex CLI**. Scoring
and review use no model. libRSI has no default model; your backend chooses it.

Full study: **171 Astra request attempts (169 completed) · 2,245,947 known input/output tokens**.
Two requests timed out and were each retried once after diagnosis; their token usage is unknown.
Timing, setup attempts and the forced-revision diagnostic are itemized in the
[methods, costs and results](docs/native-sequence-benchmark.md).
[Run-level CSV](docs/benchmarks/native-sequence/run-scores.csv) · [Full data](docs/benchmarks/native-sequence/) · [Effort graph](docs/assets/native-sequence-effort.png).

<details>
<summary>Model effort and the forced meta-revision diagnostic</summary>

![Model request attempts and known token usage; gpt-6-astra high](docs/assets/native-sequence-effort.png)

![Retained original vs forced revised improver; gpt-6-astra high at both levels](docs/assets/native-sequence-meta-diagnostic.png)

</details>

The investigation also found and corrected a library gate that counted ties
against useful changes. [Diagnosis, historical results and replay-safe correction](docs/meta-diagnosis.md).
These measurements concern synthetic setup costs, not measured factory throughput.

## Run it

From a source checkout, with an authenticated Codex CLI that can access Astra and
a C++17 compiler for the exact reference solver:

```bash
python -m pip install . numpy matplotlib
python examples/run_native_sequence_study.py --output ./native-sequence-run
```

This runs the experiment, audits its saved evidence, and generates the graphs.
Use a fresh directory; the model-call ceiling is 169, with no automatic retries.
[Smaller LLM example](docs/llm-search-benchmark.md) · [No-model companion](docs/search-benchmark.md).

## Connect your application

Supply a measuring adapter, model-backed proposer, reviewer, store and metric policy.
The [complete benchmark](examples/benchmark_native_sequence.py) implements these
components. Your application supplies meaningful measurements, representative data
and execution isolation. The [intent layer](examples/sequence_intent.py) also
supports proposing a measurable contract from a broad goal.

## Guides

- [Adaptive integration](docs/adaptive-operation.md) · [API](docs/api.md) · [Concurrent serving](docs/concurrent-adaptive-operation.md)
- [Model providers](docs/providers.md) · [External agents](docs/external-agent-protocol.md) · [HTTP/MCP](docs/service-protocol.md)
- [Consumer integration](docs/consumer-integration.md) · [Testing](docs/testing.md) · [Migration](docs/migration-0.2.md)

libRSI-owned material is [MIT licensed](LICENSE). [Separate upstream license boundaries](docs/license-decision.md).
