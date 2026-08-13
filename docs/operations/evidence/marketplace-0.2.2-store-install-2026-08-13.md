# DocFerry VS Code Marketplace 0.2.2 store-install evidence

Date: 2026-08-13

## Result

- Extension: `bondie.docferry@0.2.2`
- Channel: Preview
- Bundled CLI: `docferry 0.4.3`
- Public listing:
  `https://marketplace.visualstudio.com/items?itemName=bondie.docferry`
- GitHub release:
  `https://github.com/fyaic/Docferry-VSCode/releases/tag/v0.2.2`
- Quality run:
  `https://github.com/fyaic/Docferry-VSCode/actions/runs/31699140428`
- Release run:
  `https://github.com/fyaic/Docferry-VSCode/actions/runs/31699744314`

All four Marketplace packages report `validated`:

| Target | Release SHA-256 |
| --- | --- |
| `darwin-arm64` | `5646370141ef443cbc5be99938b18e7d094906da85e84b1ea5cbfe8eef1147d6` |
| `darwin-x64` | `92a2fe7ddea9beb17661f0b13f287724ffcc69a37f322c20263de5530b7aeb15` |
| `linux-x64` | `c003b5fe12d2b91c5d5fe2139cd592626ebc776653b68e67a57bf596c19c288f` |
| `win32-x64` | `583bb2db8742cb460cf7f108432c9d1ba9b2c22c641665ba81e5339865e0c308` |

## Store provenance

The exact macOS arm64 Marketplace package was installed into a fresh extension
directory and user-data directory. The installed manifest reported
`publisher=bondie`, `version=0.2.2`, `preview=true`, and `pricing=Free`.

The isolated Marketplace install was also loaded directly as the Extension Host
development path. Activation and command registration completed successfully.
No local source checkout or older extension directory was used for this test.

The normal VS Code installation was upgraded from `bondie.docferry@0.2.0` to
the exact Marketplace version `bondie.docferry@0.2.2`. Its helper and extension
bundle hashes match the isolated Marketplace install:

| Artifact | SHA-256 |
| --- | --- |
| Bundled helper | `06bd401782b4ffc7dab4e06dc91d689d95d463d3a9dec1a5ea795092c5f30048` |
| Extension bundle | `d712bdb2aea15847ee41f39f555f57f6cfdccfd35ea0f7588f93c343630e5a17` |

## Production smoke

- Packaged TLS and CA trust: production health returned
  `ok=true`, `service=docferry-share`, and version `0.0.63`.
- Device Code login: the system Chrome browser opened the DocFerry product
  approval page, completed Google login, requested explicit approval for the
  VS Code device, and returned an authenticated product session.
- Product routing: the generated dashboard target was
  `https://docferry.bondie.io/v0/auth/dashboard-open` with target path
  `/dashboard`, not the generic Bondie Account Center.
- Membership: a real Pro account returned folder publishing, full theme,
  history, and Advanced Import feature gates.
- Note share: public HTTP 200 and source marker verified; importing the share
  back into the workspace preserved the marker.
- Folder share: two nested Markdown documents were published; the hidden file
  marker was absent from the folder page and both public document pages.
- Advanced Import: an intentionally insufficient page was rejected by the
  paid-note quality gate. A substantive public page reached `extracted` and
  wrote a structured Markdown note to the workspace.
- Cleanup: both synthetic shares were stopped, both public URLs returned HTTP
  410, and both history records were deleted. Pre-test active share counts were
  restored.

The isolated login configuration and generated test workspace lived under
`/tmp`; no credentials or user content are recorded in this evidence.

## Publisher domain

The Publisher Details page currently states:

> Your request to verify the domain is submitted to the marketplace team for
> processing.

The publisher domain is `https://bondie.io`. The public Gallery API still
reports publisher flag `verified` and `isDomainVerified=false`. Therefore the
owner-side DNS and submission steps are complete; the remaining badge state is
Marketplace-team processing and propagation, not an extension publication
blocker.

## Remaining release operation

The protected Marketplace workflow is present, but unattended OIDC publishing
still requires the Microsoft Entra application values `AZURE_CLIENT_ID` and
`AZURE_TENANT_ID`. Version `0.2.2` was published with a short-lived interactive
token, and no long-lived Marketplace PAT was stored.
