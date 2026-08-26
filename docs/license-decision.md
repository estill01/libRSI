# License decision packet

Status: `selected-mit`.

Direct user authority selected MIT for libRSI on 2026-08-25. The canonical root
`LICENSE` and `License-Expression: MIT` package metadata implement that decision.
PEP 639 deprecates license classifiers when a license expression is present, so the
release metadata intentionally contains no `License ::` classifier. This record is
implementation guidance, not legal advice.

## MIT

- Short permissive grant covering use, copying, modification, publication,
  distribution, sublicensing, and sale.
- Copies or substantial portions must retain the copyright and permission notice.
- Includes a broad warranty/liability disclaimer but no express patent-license clause.
- Applied to libRSI-owned material with the canonical owner/year text and
  `License-Expression: MIT` metadata. The deprecated Trove classifier is omitted.

Authoritative text: [Open Source Initiative MIT License](https://opensource.org/license/mit).
Packaging authority: [PEP 639](https://peps.python.org/pep-0639/).

## Apache License 2.0 — not selected

- Permissive copyright grant plus an express contributor patent grant and patent
  termination terms.
- Redistribution conditions require the license, prominent change notices, retained
  attribution notices, and eligible `NOTICE` content when a NOTICE file exists.
- Longer compliance surface than MIT; suitable when an explicit patent grant matters.
- If selected, add the canonical Apache-2.0 text, `License-Expression: Apache-2.0`
  metadata, omit the deprecated Trove classifier, and record an accurate NOTICE
  determination.

Authoritative text and application guidance:
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) and
[Applying Apache License 2.0](https://www.apache.org/legal/apply-license).

## Explicit no-license choice — not selected

- Keep the repository source-visible without granting general reuse or redistribution
  rights.
- Add no OSI classifier, license expression, or `LICENSE` file and make the no-license
  posture explicit in README, artifacts, and release evidence.
- Public source visibility alone leaves default copyright restrictions in place; see
  [GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## Upstream utility boundary

This decision applies only to libRSI-owned material. It cannot license or publish the
separate utils artifacts consumed by internal conformance/provider lanes. Public libRSI
artifacts and extras therefore remain free of those packages regardless of which
libRSI choice is selected.
