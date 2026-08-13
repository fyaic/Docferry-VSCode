# DocFerry VS Code Marketplace 0.2.0 publication evidence

Date: 2026-08-13

## Result

- Publisher: `Bondie` (`bondie`)
- Extension: `bondie.docferry`
- Marketplace extension ID: `e0e78284-444f-467b-b9e1-fffb706929d4`
- Version: `0.2.0`
- Channel: Preview
- Marketplace pricing metadata: Free
- Public listing:
  `https://marketplace.visualstudio.com/items?itemName=bondie.docferry`
- GitHub release:
  `https://github.com/fyaic/Docferry-VSCode/releases/tag/v0.2.0`

All four accepted platform packages were published with a short-lived Microsoft
Entra token. No Marketplace PAT, application secret, or product credential was
created or stored.

## Published packages

| Target         | SHA-256                                                            |
| -------------- | ------------------------------------------------------------------ |
| `darwin-arm64` | `7df40cd83f6d6833a3e2b592a782204499aa69d3a244b2bf06417016eeb46258` |
| `darwin-x64`   | `09649ba5c2789cc3bb1c3c6e450f2d4fc5ec593b40d486a1f9a3615e51c1b68b` |
| `linux-x64`    | `af3c06325fa27898b952faaaf79c0cf6bc588bd7eb90682bbd6cffb69749ee06` |
| `win32-x64`    | `ba6b6bd3b16d4c518b9cecbb298e616adeaa7cd44129a6641841b0d278ee410d` |

Marketplace's `Microsoft.VisualStudio.Services.VsixSha256` values match the
checksummed GitHub release for every target.

## Verification

- Publisher authorization: `vsce verify-pat` passed using the short-lived Entra
  access token.
- Marketplace public API: returned version `0.2.0` for exactly the four targets
  above.
- Public listing: HTTP 200 and rendered DocFerry, Bondie, Preview, Free, the
  expected description, and install command `ext install bondie.docferry`.
- Isolated Marketplace install on macOS arm64: installed
  `bondie.docferry@0.2.0` into a separate extension and user-data directory.
- Installed manifest: `publisher=bondie`, `version=0.2.0`, `preview=true`, and
  `pricing=Free`.
- Installed helper: Mach-O arm64; its SHA-256 matched the accepted VSIX payload
  and a clean isolated run returned `docferry 0.4.2`.
- Source quality gate:
  `https://github.com/fyaic/Docferry-VSCode/actions/runs/31688857913` passed all
  source, extension-host, Marketplace verifier, and four-platform package jobs.

## Publication controls

- Publishing workflow: `.github/workflows/marketplace.yml`
- GitHub environment: `visual-studio-marketplace`
- Allowed publication branch: `main`
- Required reviewer: enabled
- Publication input defaults to `profile`, not `publish`.
- The workflow republishes the checksummed GitHub release assets and does not
  rebuild a second artifact set.

## Follow-up

Publisher DNS-token ownership is accepted, but the Marketplace API still
returns `isDomainVerified=false` after the publisher display-name correction.
The final domain verification request has since been submitted and is awaiting
Marketplace-team processing. See the `0.2.2` store-install evidence for the
current state. This does not block installation of the Preview extension.

The protected workflow is ready for a future Microsoft Entra application and
GitHub OIDC configuration. `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` remain
intentionally unset until that Contributor identity is created and added to the
Bondie publisher.
