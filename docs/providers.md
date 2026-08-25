# Provider adapters

Provider adapters are optional projections of the same `ReasoningRequest` to
the same proposal-only `ReasoningResult`. They never own hypotheses, evidence,
selection, application, verification, or acceptance.

`libRSI[openai]` uses the maintained OpenAI Responses API. Configuration holds
only a model name; the SDK obtains credentials from its normal external
configuration. libRSI does not serialize credentials or provider response
objects into canonical records. Deterministic fake clients are the ordinary
test path; live calls require separate credential and spend authority.

The internal Codex adapter is pinned to terminal accepted utils revision
`a5659745a7cbcbb002b5f06051f6ed9826f721a7` and its unchanged exact package
source/artifact roots,
not to the unrelated public registry package with the same name and version.
The exact producer, artifact, API, schema, surface, qualification, and adapter
roots are recorded in `librsi/providers/compatibility.json`. The upstream
package remains unlicensed and unpublished: this is an internal compatibility
handoff, not a publication, redistribution, reuse-rights, or general public
installability claim. Consequently, public `libRSI` metadata exposes no `codex`
extra, Git/path dependency, or bare registry requirement for that client. Authorized
CI reconstructs the exact accepted wheel from the trusted producer revision, verifies
SHA-256 `1e9dc5b9c7f2edb9676b5a47eb2c9b96498f1b429acec474cd26702fe8e3fdb9`,
and installs it only for the mapped conformance lane.

Process ownership is explicit:

- `standalone`: libRSI may resolve and own one local stdio app-server process;
- `embedding-host`: the host injects one initialized typed session and retains
  process ownership; and
- `software-factory`: Software Factory injects its session, and libRSI rejects
  any executable configuration or missing injection before provider access.

Every Codex task starts an ephemeral, read-only thread with approval policy
`never`, requests one JSON proposal, observes only typed app-server events, and
projects the result through libRSI's existing schema validator. It exposes no
raw RPC escape and cannot turn provider completion into evidence or authority.

The maintained terminal composition matrix, including the exact accepted utils
structural lifecycle and descriptive runtime-manifest handoffs, is recorded in
[`system-dogfoods.md`](system-dogfoods.md). Those packages remain internal CI
inputs rather than public libRSI runtime dependencies.
