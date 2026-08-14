# Marketplace 0.2.3 UX Closure

Date: 2026-08-14

## Candidate

- Extension: `bondie.docferry@0.2.3`
- Bundled Agent Kit: `0.4.4`
- macOS arm64 VSIX SHA-256:
  `0bfa96af160cb4ebe6b6df430d30b7b78797abcca3ad0e79f03efb10ad4931a0`
- Package size: approximately `14 MB`
- Package contents: `70` files, including the platform helper runtime

## User-facing closure

- Device Authorization is split into start and completion phases. VS Code opens
  the validated `docferry.bondie.io` activation URL in the system browser before
  it begins waiting for approval, with explicit open and copy-link recovery.
- The bundled helper is now a self-contained runtime directory. The previous
  single-file package took about `10.9s` on every macOS invocation; the installed
  runtime measured `0.11s` after its one-time operating-system inspection, and a
  real authenticated folder list completed in about `1.94s`.
- Whole-workspace folder sharing names the workspace and explains exactly what
  will and will not be published before confirmation.
- Share lists refresh after publish, update, stop, and permanent history deletion.
- Background Detailed Note work remains visible in the Activity view and status
  bar until the user saves, cancels, or receives a terminal failure.

## Verification

- Marketplace and export-safety verifier tests: `4 passed`
- Source verifier: passed (`55` files, Agent Kit `0.4.4`)
- TypeScript and contract tests: `18 passed`
- Extension Host smoke: passed
- npm audit: `0` vulnerabilities
- macOS arm64 VSIX content, secret scan, helper version, and production HTTPS
  health verification: passed
- The exact candidate was installed into desktop VS Code and loaded from
  `bin/helper/docferry`; the existing account session remained intact.

## Release state

This evidence qualifies the candidate for the repository's native build matrix.
It does not assert that `0.2.3` has already been tagged, released, or submitted
to Visual Studio Marketplace.

Native rebuilds can contain different PyInstaller binary metadata. The release
workflow must verify and publish the exact checksummed GitHub artifact rather
than rebuilding it during Marketplace submission.
