![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

**Turn task feedback into tested improvements—and improve the process that proposes them.**

libRSI is a Python library for adding an improvement loop to an application. Use it
to improve a search strategy, an agent's prompt, or the way a system generates
candidate solutions. Your application supplies the work, proposals, and scores;
libRSI runs the bounded experiments, compares candidates, and manages review,
adoption, verification, and recovery.

The same loop can target **the improver itself**: test a better proposal strategy,
adopt it, then use it to find better changes on subsequent tasks. This is the
library's practical approach to recursive self-improvement (RSI).

**Python 3.11+ · Dependency-free core · Typed API · MIT**

## See it work: improve a search engine, then its improver

The [runnable benchmark](examples/benchmark_document_search.py) searches **5,183
scientific abstracts** using the public [BEIR SciFact dataset](https://github.com/beir-cellar/beir/wiki/Datasets-available).
It compares three systems on the same **300 official test queries**:

1. **Original search:** rank documents by matching term counts.
2. **Ordinary libRSI:** propose two ranking changes, measure them, and use the
   revision that passes review and verification.
3. **Meta-improved libRSI:** first use libRSI to improve the proposal policy;
   then repeat the ordinary improvement pass with that policy and the same
   two-candidate budget.

**What drives the improvement loops? No LLM or model provider is used in this run.**
The ordinary `SearchProposer` supplies two predefined ranking configurations.
The meta `PortfolioProposer` supplies two predefined proposal portfolios.
`MeasuredReviewer` checks the evaluation in Python; scoring and libRSI's selection
rules are deterministic too. The meta step selects a proposal policy from those
choices; it is not an LLM generating or improving its own reasoning.

![BEIR SciFact benchmark: ordinary proposer, meta-proposer, and reviewer use no LLM; all are deterministic Python](docs/assets/search-improvement.png)

On this run, retrieval score (MRR@5) was **6.3%** for original search, **41.1%** with ordinary improvement, and **57.4%** after improving the proposer. The top result was relevant for **9, 102, and 151 of 300 queries**, respectively.

Both ordinary passes use identical development queries. The meta pass gets an
additional 600 training queries; its work is included in the effort graph.
Fixed BM25 matches the meta result; a full sweep scores **57.9%** using only
360 tuning-query executions. For this small search space, direct tuning is
cheaper. libRSI adds the experiment history, review, and verified adoption workflow.

This example uses explicit, deterministic ranking algorithms and proposal policies,
with **no model calls**. It demonstrates measured improvement and transfer from an
improved proposer; it does not train model weights or rewrite libRSI's rules.
See the [method, costs, limitations, and raw results](docs/search-benchmark.md).

## Run it

Install from this checkout, with NumPy for this benchmark's retrieval and
Matplotlib for its graph. Ordinary libRSI use needs neither.

```bash
git clone https://github.com/estill01/libRSI.git
cd libRSI
python -m pip install . numpy matplotlib
python examples/scifact_data.py --download ./scifact.zip
python examples/benchmark_document_search.py \
  --dataset ./scifact.zip --output ./search-run
python examples/plot_document_search.py \
  --report ./search-run/report.json --output ./search-run/improvement
```

Use a fresh output directory. The download is about 2.7 MB and is checked against
a pinned hash. The run saves query-level scores, configurations, timings, native
results, and durable stores. [Reproduction details](docs/search-benchmark.md#reproduce).

## Use it in your application

Provide three pieces: an **adapter** that runs a strategy and measures its output,
a **proposer** that suggests candidate strategies, and a **reviewer** that checks
results before adoption. They can wrap your existing models, tools, or services.
libRSI has no built-in LLM choice: your reasoning backend determines the model.
For example, its [OpenAI backend](docs/providers.md) requires a model identifier
in its configuration. The benchmark above uses Python proposal functions instead.

Once those application-owned pieces are supplied, an adaptive integration looks
like this:

```python
from librsi import AdaptiveLoop, LearningCase, LearningPolicy, LocalLearningStore, Metric

with LocalLearningStore(
    "./search-profile",
    profile_id="search",
    initial_configuration=current_search_config,
) as store:
    loop = AdaptiveLoop(
        store,
        adapter=search_adapter,
        proposer=search_proposer,
        proposer_id="search-proposer-v1",
        reviewer=search_reviewer,
        reviewer_id="search-reviewer-v1",
        policy=LearningPolicy(
            objective="Improve retrieval quality",
            metric=Metric(metric_id="mrr", direction="increase", unit="reciprocal-rank"),
            minimum_effect=0.01,
        ),
    )
    for job_id, task_input in new_tasks:
        feedback = loop.run_task(LearningCase(job_id, task_input))
    result = loop.learn("round-1", shadow_cases=held_out_tasks, activate=True)
```

A verified revision becomes the strategy used by the next task. Without
`activate=True`, learning evaluates changes while leaving the active strategy in
place. The [benchmark adapter and proposers](examples/document_search.py) are
complete implementations; the [integration guide](docs/adaptive-operation.md)
explains how to replace them for your workload.

For a meta application, make the adapter **measure the quality of proposed
changes**, and make the configuration **the policy used to propose them**.
Feed the verified policy back into the ordinary loop. The benchmark does exactly
this, then reopens storage and checks that subsequent tasks use the saved revisions.

## Where to go next

- [API guide](docs/api.md): validate a claim, test a hypothesis, investigate,
  improve, or govern self-change through `LibRSI`.
- [Adaptive operation](docs/adaptive-operation.md) and
  [concurrent serving](docs/concurrent-adaptive-operation.md): learn from task
  feedback, persist progress, and serve requests while learning.
- [Consumer integration](docs/consumer-integration.md) and
  [stateless comparison](docs/stateless-comparison.md): connect your execution
  and storage, or compare completed trials without a local store.
- [Model providers](docs/providers.md), [external agents](docs/external-agent-protocol.md),
  and [HTTP/MCP](docs/service-protocol.md): use your existing reasoning and service stack.

Your application owns metric quality, execution isolation, scheduling, and effects.
libRSI owns the experiment and decision records. A proposed change still has to earn
adoption through measurements. Local profiles have explicit ownership and recovery
requirements; see the relevant operation guide before sharing a profile.

For development, see [testing](docs/testing.md), the [module map](src/librsi/README.md),
and the [changelog](CHANGELOG.md). Internal provider tests require separate upstream
artifacts; they are not public runtime dependencies. Existing users can consult the
[migration guide](docs/migration-0.2.md).

libRSI-owned material is [MIT licensed](LICENSE); separate upstream artifacts remain
outside that grant. [License boundary](docs/license-decision.md).
