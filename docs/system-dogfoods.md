# Maintained system dogfoods

Block 24 is a deterministic CI matrix over the existing canonical engine. It is
not a second implementation architecture and not a one-time demonstration. The
new system fixture extends earlier fixtures only where an end-to-end combination
was missing.

## Exact qualified package set

The shared-utility lanes consume terminal utils revision
`a5659745a7cbcbb002b5f06051f6ed9826f721a7` under qualification-matrix SHA-256
`0888bed363b63842c37baa8187c9883cdddff73d936596e497e4e013341cd849`
and technical qualification root
`9ab96149f63a45429a44ae07e309b68bb4204b4e2e6f4da6a7a93acbd5547068`.

| Distribution | Accepted source | Exact wheel SHA-256 | Wheel content root |
| --- | --- | --- | --- |
| `codex-app-server-client` 0.1.0 | `08c416da4202b7036110e33e43d34ea590054e2e` | `1e9dc5b9c7f2edb9676b5a47eb2c9b96498f1b429acec474cd26702fe8e3fdb9` | `6ecc26e75197d06682fe9d8d0612edb1e56ead6d04c3a41cde1132e2618efd8f` |
| `embedded-service-contract` 0.1.0 | `401f87a64349c636a66be2da656498e7d9cb58e3` | `2b36d7307c08cd6d7d95bfb86d4a240b6ab2a69de5b2c61bf75a54507c7ea18d` | `c53432ff83c6b80483a95384af3c9058a3cd82c56ac774126f123a93dbff7113` |
| `runtime-manifest` 0.1.0 | `6f7a7ea3c105c7461e6cb4c83944dd094883f187` | `f2e601d542272187998296f09d33b2235002d108fe07c0b3c89a678ea1d010ac` | `db8f7f7d0b0105361f9b1380ff1d1cc432e720be02def65880a9ef484ad112a2` |

CI checks out the trusted revision, independently rebuilds all three wheels, verifies
the exact accepted wheel hashes, and installs those artifacts without dependencies.
No utility code or wheel is copied into libRSI. These upstream artifacts remain
unlicensed and unpublished; this internal test handoff is not a claim of public
installability, reuse rights, redistribution, or release authority.

The libRSI adapter root is
`b8bff636687b34fecb6a5fbea6cfda28c53e6866df8a1fa9264eb5b569a300bf`.
Its file set is fixed in libRSI code and includes the utility handoff document;
the exact root is independently frozen by this document and the system test,
not supplied by the handoff document itself.
libRSI resolves the exact installed distributions and executes their already-hashed
sources under private libRSI-owned module namespaces. Adapter exports bind only
from those executed module objects, so caller-populated canonical import entries,
including shadows carrying copied loader metadata, cannot become operational.
Immutable behavioral roots cover executed function code/defaults/closures and
class-owned methods, descriptors, annotations, and fields. They are revalidated
before use, so in-place mutation of an otherwise identical function or class
object also fails closed.
The external-agent schema source root is
`89edd647d75977f1b33dba9173118ae5490f1699a9e5725e28207961b8fd4e1a`.
The canonical descriptive manifest SHA-256 is
`f826048537680971c04c596c996e84e6de4a2954ace84c36ff7cab0f4a860505`;
its component version is the `0.3.0` release candidate.

The lifecycle package checks only host shape, process ownership, run references,
status, ordered events, cancellation, and structural outcomes. libRSI continues
to own requests, workflow state, persistence, evidence, semantic outcomes, and
authority. The runtime manifest is caller-supplied description only. Its fields
do not grant availability, application permission, evidence weight, acceptance,
or release authority.

## Scenario and output matrix

| Scenario | Maintained proof | Exact output contract |
| --- | --- | --- |
| validation-only | `test_managed_and_external_service_runs_share_exact_canonical_outcomes` | managed and external service projections are identical |
| investigation-only and parallel search | `test_investigate_falsifies_one_branch_and_retains_supported_alternative`, `test_parallel_portfolio_round_robins_design_before_execution` | complete competing branch roster; no losing-lane promotion |
| externally driven improvement | `test_external_and_managed_system_improvement_have_exact_roots_and_outcomes` | two externally submitted improvement-cycle actions settle the canonical workflow |
| managed-equivalent improvement | same system test | exact action, result, outcome, and projection roots match external control |
| managed standalone target/objective | same system test | target admission and evaluation contract remain canonical inputs |
| competing hypotheses and discriminating experiments | same system test | two materially distinct hypotheses; supported and retired-null branches remain distinct |
| honest inconclusive evidence | same system test and `test_inconclusive_evidence_redesigns_before_stopping` | null evidence remains null and never becomes support |
| intervention comparison and selection | same system test | two candidates per iteration; first iteration selects none, second selects one |
| typed iterate/stop | same system test | first direction `broaden`; second direction `stop`; terminal reason `accepted candidate selected` |
| interruption and resume | `test_external_controller_drives_exact_json_run_across_restart`, `test_service_handles_survive_restart_and_duplicate_results_fail_closed` | resumed frontier and final projection equal uninterrupted execution |
| application disabled by default | `test_managed_rsi_stops_before_apply_then_verifies_and_rolls_back_when_authorized` | stop reason `application-authority`; no target effect |
| apply, verify, and rollback | same managed RSI test and `test_rsi_schema_conforms_through_apply_verify_and_rollback` | explicit authority, currentness gate, verification, and exact rollback |
| RSI/self-change | `test_activation_disabled_runs_every_gate_without_target_effect`, `test_accepted_self_change_uses_approval_bound_ordinary_application`, `test_failed_post_activation_verification_rolls_back_exactly` | historical, shadow, independent review, application, verification, and rollback remain separate |
| Codex proposal fake | system improvement test and `test_codex_backend_is_equivalent_to_other_reasoning_backends` | the injected fake's typed proposal is converted into the exact initial hypotheses used by both canonical executions; it is never Evidence or application authority |
| injected provider/process ownership | system improvement and lifecycle tests, `test_injected_codex_session_uses_typed_surface_without_process_ownership`, `test_process_owner_contract_rejects_two_owners_before_import` | the causally used injected Codex provider declares embedded owner count 0 alongside service owner count 1; two owners are rejected |
| structural lifecycle equivalence | `test_real_embedded_and_service_hosts_pass_exact_structural_conformance` | both real host compositions pass the accepted three-scenario lifecycle contract |
| descriptive runtime compatibility | `test_exact_qualified_shared_package_set_and_descriptive_manifest_are_consumed` | exact component, protocol, schema, dependency, and adapter roots; diagnostics only |
| stale, mixed, copied, shadowed, or missing utility | `test_shared_utility_substitutes_missing_lanes_and_manifest_authority_fail_closed`, `test_lifecycle_projection_rejects_implicit_or_malformed_semantics` | fail closed before mapped conformance or manifest projection; every operational root export remains object-identical to its exact hashed owner submodule |

The deterministic system improvement output is frozen as:

- action roots `7177156a4f6f7c829b3be17a8411b5003adaa0a66d0255681d74ca26e33b404d`
  and `fae7619b63c69b98cca3590846b22e6c65d48ee71604ba404538ac0b105083ff`;
- result root `aa061bc0d8c92e9f3cdd8f5311054d3ccca4eabfbb66b3af7aa537849b48b841`;
- outcome root `25443d2238e70a2dc38ebf2ede9778318824cdda8e05d59909d9fa916baf5630`;
  and
- projection root `72ce0e66a9d6d53261e6e2ac049063533405c0202bde0a70927239f4af60124a`.

External and managed execution must reproduce all five roots exactly. A change
to any scenario input intentionally changes those roots and requires a reviewed
fixture and matrix revision rather than accepting drift.
