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
| `embedded-service-contract` 0.1.0 | `401f87a64349c636a66be2da656498e7d9cb58e3` | `2b36d7307c08cd6d7d95bfb86d4a240b6ab2a69de5b2c61bf75a54507c7ea18d` | `c53432ff83c6b80483a95384af3c9058a3cd82c56ac774126f123a93dbff7113` |
| `runtime-manifest` 0.1.0 | `6f7a7ea3c105c7461e6cb4c83944dd094883f187` | `f2e601d542272187998296f09d33b2235002d108fe07c0b3c89a678ea1d010ac` | `db8f7f7d0b0105361f9b1380ff1d1cc432e720be02def65880a9ef484ad112a2` |

CI checks out the trusted revision, independently rebuilds both wheels, verifies
the exact accepted wheel hashes, and installs those artifacts without dependencies.
No utility code or wheel is copied into libRSI. These upstream artifacts remain
unlicensed and unpublished; this internal test handoff is not a claim of public
installability, reuse rights, redistribution, or release authority.

The libRSI adapter root is
`170d5d377877b361d9699051f6ff21c97c185436d2fd24b2f030e1bf25b75a76`.
The external-agent schema source root is
`89edd647d75977f1b33dba9173118ae5490f1699a9e5725e28207961b8fd4e1a`.
The canonical descriptive manifest SHA-256 is
`ba4a9a51a85cd56fe50f3b47a9725128902ae75afadba3892e0e3d72f67253db`.

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
| Codex proposal fake | system improvement test and `test_codex_backend_is_equivalent_to_other_reasoning_backends` | typed proposal only; never Evidence or application authority |
| injected provider/process ownership | lifecycle system test, `test_injected_codex_session_uses_typed_surface_without_process_ownership`, `test_process_owner_contract_rejects_two_owners_before_import` | embedded owner count 0 plus service owner count 1; two owners rejected |
| structural lifecycle equivalence | `test_real_embedded_and_service_hosts_pass_exact_structural_conformance` | both real host compositions pass the accepted three-scenario lifecycle contract |
| descriptive runtime compatibility | `test_exact_qualified_shared_package_set_and_descriptive_manifest_are_consumed` | exact component, protocol, schema, dependency, and adapter roots; diagnostics only |
| stale, mixed, copied, or missing utility | `test_shared_utility_substitutes_missing_lanes_and_manifest_authority_fail_closed`, `test_lifecycle_projection_rejects_implicit_or_malformed_semantics` | fail closed before mapped conformance or manifest projection |

The deterministic system improvement output is frozen as:

- action roots `7dea1ad37698dfb655a5f5d2c9ed6b6f4b829fe65a85508de440fee5f01f32fb`
  and `8de64a259adca0c983df5e5a2f2b63397cbad4e39dcfac36c97343c3ad501ba2`;
- result root `907ea507e742dfee6f4d2d9b561d55a3d32af9624ede9467ff002a9f56ed0d0b`;
- outcome root `bb4ba179eb57f4d36e922f7f15a8567d0f70e46ca241768fe7d7bc5c920c09f8`;
  and
- projection root `b468cd5c638a360cc39ebb7558e56ef6fbbf4189ff24ea3c6d3c8fe730514fba`.

External and managed execution must reproduce all five roots exactly. A change
to any scenario input intentionally changes those roots and requires a reviewed
fixture and matrix revision rather than accepting drift.
