# Submit goals to a shared service

Intake accepts an ordinary goal plus context, chooses a registered adapter, gathers
observations, proposes measurable criteria and competing hypotheses, and starts a
normal libRSI improvement or investigation run. When information is missing, it
returns specific questions without starting a run.

```json
{
  "request_id": "support-prompt-17",
  "goal": "Make this prompt produce more useful support answers",
  "context": {
    "target_id": "support-prompt",
    "configuration": {"prompt": "Answer the customer's question"},
    "examples": [
      {"input": "Where is my order?", "output": "Check online", "passed": false},
      {"input": "How can I reset my password?", "output": "Use the reset link", "passed": true}
    ]
  }
}
```

Send that JSON to `POST /v1/intake`. A successful response's `data` contains
`disposition: "started"`, the selected adapter, `run_id`, the evaluation contract,
and the hypotheses. Use the existing run status, actions, results, managed-pass,
and outcome endpoints with that ID. Intake submission starts the run; experiment
execution uses its configured providers or an external agent. It never applies
changes or authorizes application.

`disposition: "needs-information"` contains a `questions` array and no run ID.
Answer those questions in the goal/context and submit a **new** request ID. Reusing
an ID with identical input returns the existing receipt; changing that input is an
error. `GET /v1/intake/{request_id}` retrieves the receipt. `GET /v1/intake/adapters`
lists available target families, workflows, capabilities and budgets. Supply
`adapter_id` in a request to explicitly select one and skip the routing model call.

## Configure once per target family

Use `from librsi.intake import IntakeAdapter, IntakeContext, IntakeMetric`.
Each adapter has a versioned ID, a description, a read-only `collect(request)`
function, and ordinary capability bindings. The collector returns:

- An exact snapshot of the current target.
- Available objective metrics with actual baseline measurements, descriptions,
  and minimum worthwhile improvement floors.
- Relevant observations and task feedback, plus any constraints, guardrails,
  guardrail measurements, and existing sourced evidence.

The model selects among these metrics and may propose a stricter improvement
threshold. It cannot invent a metric, weaken the registered floor, alter execution
routes, change budgets, or remove host constraints. Register metrics that measure
what the application actually values. Intake validates the proposed structure;
the host remains responsible for measurement quality and the suitability of the
metric catalog. Keep held-out evaluation data outside the collector's context.

Collectors can raise `IntakeNeedsInformation("Which task set should we use?")`.
The model can also ask questions during routing or goal interpretation. Collection
runs again before a new workflow starts to check that its target snapshot still
matches the one used for planning. Collectors must therefore be bounded, read-only,
and safe to repeat; they should re-observe live targets in real integrations.

Configure `LibRSIService.local(data_directory, intake_backend=backend,
intake_adapters=(adapter, ...), registry=registry)`. The backend is the existing
`ReasoningBackend`, including `OpenAIResponsesBackend` or a compatible host model
adapter. Register execution providers in the normal capability registry, or use
external bindings for an agent that performs actions and submits measured results.

## Run over HTTP or MCP

Both executables accept `--factory module:callable` to load a trusted host factory
with arguments `data_directory` and `limits`. It must return a configured
`LibRSIService` preserving those limits. Factory loading is a startup operation;
requests cannot load modules or register executable adapters.

The runnable [example factory](../examples/goal_intake_service.py) registers prompt
and search adapters. It derives baseline scores from the caller's measured task
records and uses a real, explicitly selected OpenAI model for intake. From a
checkout with the server and OpenAI extras installed:

```bash
export LIBRSI_INTAKE_MODEL='YOUR_MODEL_ID'
# Configure OPENAI_API_KEY through your existing secret environment.
librsi-http --factory examples.goal_intake_service:create_service --data-dir /path/to/intake-data
```

For MCP, install the MCP extra and use the same factory with `librsi-mcp`; add
`--transport streamable-http` for HTTP transport. Configured MCP servers expose
`librsi_intake`, `librsi_intake_status`, and `librsi_intake_adapters`. Ordinary
HTTP/MCP authentication and application-authority boundaries still apply.

The example uses external experiment routes: the connected agent carries out
experiments through the existing next-action/result protocol. It is an intake
integration example, not evidence of improved prompt or search performance. Its
two illustrative task records above are not a statistical benchmark. A production
collector should read the application's actual target, feedback, and evaluators.

## Persistence and operating limits

Local composition adds `intake.sqlite3` beside the existing service databases.
It checkpoints the request, adapter configuration, observations, model proposals,
prepared admission/request, and final receipt. Native workflow stores remain the
authority for experiment state and outcomes. Completed model calls are reused
after a restart, and a crash after native run creation does not create another run.
A crash before a model response is saved can repeat that call; this is not an
exactly-once provider guarantee. Changing adapter semantics requires a new adapter
ID; changing configuration during an unfinished intake requires a new request ID.

There are at most three model calls per uninterrupted intake: routing, criteria,
and hypotheses. An explicit adapter skips routing. Context/proposal records are
bounded to 256 KiB by default; the service request limit also applies. The host
backend supplies model timeouts and token/cost controls. The example sets a
60-second provider timeout and disables automatic SDK retries.

Intake preserves the existing serialized service execution model. It does not add
a background scheduler, parallel job queue, or worker deployment. Independent jobs
retain separate durable run IDs and can be advanced through the existing API.
