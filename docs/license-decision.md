# License decision packet

Status: `pending-direct-user-selection`.

The repository is public, but no license grant has been selected. Until the owner makes
a direct choice, libRSI does not claim open-source status or public rights to copy,
modify, distribute, sublicense, or reuse the source. This packet is implementation
guidance, not legal advice.

## MIT

- Short permissive grant covering use, copying, modification, publication,
  distribution, sublicensing, and sale.
- Copies or substantial portions must retain the copyright and permission notice.
- Includes a broad warranty/liability disclaimer but no express patent-license clause.
- If selected, add the canonical MIT text with the owner/year, `License-Expression:
  MIT` metadata, and the matching Trove classifier.

Authoritative text: [Open Source Initiative MIT License](https://opensource.org/license/mit).

## Apache License 2.0

- Permissive copyright grant plus an express contributor patent grant and patent
  termination terms.
- Redistribution conditions require the license, prominent change notices, retained
  attribution notices, and eligible `NOTICE` content when a NOTICE file exists.
- Longer compliance surface than MIT; suitable when an explicit patent grant matters.
- If selected, add the canonical Apache-2.0 text, `License-Expression: Apache-2.0`
  metadata, the matching Trove classifier, and an accurate NOTICE determination.

Authoritative text and application guidance:
[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0) and
[Applying Apache License 2.0](https://www.apache.org/legal/apply-license).

## Explicit no-license choice

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
