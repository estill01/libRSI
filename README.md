![libRSI — Experiment. Learn. Improve. Recurse.](docs/assets/librsi-banner.webp)

# libRSI

**Give your application an improvement loop—and improve the loop itself.**

libRSI turns proposed changes into measured experiments. An LLM can suggest a
better search formula, prompt, or strategy; libRSI tests it, records the evidence,
and manages review, adoption, verification, and recovery. The next task uses the
accepted revision.

The same workflow can improve **the improver**: change its proposal instructions,
measure whether they produce better candidates, and use the accepted instructions
on subsequent work. That is the recursive part.

**Python 3.11+ · Dependency-free core · Typed API · MIT**

## A real LLM-driven example

Improve a search engine over **5,183 scientific abstracts**, then improve the
instructions given to its LLM proposer. The search engine ranks documents using
an arithmetic formula; it makes no LLM calls at query time.

**Model driving every proposal: OpenAI `gpt-6-astra`, reasoning `high`, via Codex CLI.**
This includes ordinary formula generation, meta instruction generation, and formula
generation during meta evaluation. Scoring, review and adoption use deterministic
Python and libRSI. libRSI has no built-in model choice; your backend specifies it.

1. **Original:** rank by matching term counts (`tf`).
2. **Ordinary improvement:** the LLM sees training results and writes two new
   scoring formulas. libRSI measures them and adopts a revision only if it passes.
3. **Meta attempt:** the same LLM proposes two changes to the
   **proposer's instructions**. libRSI tests the formulas those instructions produce.
   A fresh ordinary pass then uses the active instructions with the same
   two-formula budget.

![LLM-driven search results and effort; OpenAI gpt-6-astra high drives ordinary and meta proposals](docs/assets/llm-search-improvement.png)

| Result | Proposing model | Test MRR@5 × 100 | Relevant first result |
| --- | --- | ---: | ---: |
| Original term counts | None | 6.3 | 9/300 |
| Ordinary LLM improvement | `gpt-6-astra`, high | 62.2 | 162/300 |
| Rerun after rejected meta attempt | `gpt-6-astra`, high | 61.4 | 158/300 |

**The meta attempt did not produce a supported improvement.** Both proposed
instruction sets were exercised on real tasks, but neither earned adoption;
the last row uses the original instructions with a fresh model sample. Ordinary
improvement used **1 model call / 4.3 minutes**;
meta plus the rerun used **8 calls / 8.9 minutes**.
The ordinary formula is conventional BM25 up to a constant scale factor.

These are actual model calls inside the experiment, not choices from a fixed
portfolio. The meta step receives extra data and compute, all included in its
reported effort. Dollar billing is unavailable through subscription credentials;
that does not mean zero cost. This is one stochastic run, not a general claim
that meta improvement always helps. [Method, exact formulas, costs and evidence](docs/llm-search-benchmark.md).

## Run it

From a source checkout, install the benchmark dependencies and authenticate the
public Codex CLI with access to the model you name:

```bash
python -m pip install . numpy matplotlib
python examples/scifact_data.py --download ./scifact.zip
python examples/benchmark_llm_search.py \
  --dataset ./scifact.zip --output ./llm-search-run --model gpt-6-astra
python examples/plot_llm_search.py \
  --report ./llm-search-run/report.json --output ./llm-search-run/improvement
```

Use a fresh output directory. The run consumes model quota and saves prompts,
responses, tokens, timings, query-level scores and native evidence. It is bounded
to 24 model turns with no automatic retries. The
[supplementary deterministic example](docs/search-benchmark.md) needs no model
access; it selects among prewritten configurations and proposal portfolios.

## Use it in your application

Supply three application-specific pieces:

- **Adapter:** execute a configuration and return its measured result.
- **Proposer:** use your chosen LLM or another method to suggest configurations.
- **Reviewer:** inspect experimental evidence before adoption.

Wire them into `AdaptiveLoop`, record real tasks with `run_task()`, and call
`learn()` with separate evaluation cases. This integration sketch assumes those
components, a store, and a metric policy have been supplied:

```python
from librsi import AdaptiveLoop, LearningCase

loop = AdaptiveLoop(
    store, adapter=adapter, proposer=proposer, proposer_id="my-model-proposer",
    reviewer=reviewer, reviewer_id="my-reviewer", policy=policy,
)
loop.run_task(LearningCase("task-1", task_input))
result = loop.learn(
    "round-1", shadow_cases=held_out_tasks,
    verification_cases=verification_tasks, activate=True,
)
```

For meta use, make the configurable artifact the proposer's instructions and make
its adapter measure the usefulness of generated candidates. Feed the resulting
active instructions into the ordinary loop. The
[complete example](examples/benchmark_llm_search.py) does this and checks that
subsequent tasks consume the saved revisions.

## Guides

- [Adaptive integration](docs/adaptive-operation.md) · [API](docs/api.md) · [Concurrent serving](docs/concurrent-adaptive-operation.md)
- [Model providers](docs/providers.md) · [External agents](docs/external-agent-protocol.md) · [HTTP/MCP](docs/service-protocol.md)
- [Consumer integration](docs/consumer-integration.md) · [Stateless comparisons](docs/stateless-comparison.md)
- [Testing](docs/testing.md) · [Migration](docs/migration-0.2.md) · [Changelog](CHANGELOG.md)

Your application owns metric quality, execution isolation and effects. libRSI owns
the experiment and decision records; proposals still have to earn adoption.

libRSI-owned material is [MIT licensed](LICENSE). [Separate upstream license boundaries](docs/license-decision.md).
