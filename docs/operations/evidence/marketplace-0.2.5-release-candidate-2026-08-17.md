# Marketplace 0.2.5 Release Candidate

Date: 2026-08-17

## Scope

DocFerry for VS Code `0.2.5` is a documentation and release-metadata
correction over `0.2.4`. It removes stale `0.2.3` copy from the packaged
Marketplace README and feature contract, advances the manual package gate and
bug template, and explains how Marketplace selects among the four
target-specific packages.

No extension runtime, command, login, Share, Import, membership, or entitlement
behavior changed. The public `fyaic/Docferry-VSCode` repository remains the
sole source and release authority. The bundled runtime remains DocFerry Agent
Kit `0.4.4`.

## Local Verification

The release candidate passed from a clean dependency install:

- npm audit at high severity: `0` vulnerabilities
- public-source verifier: `56` source files; Agent Kit `0.4.4`
- Marketplace verifier: `4` passed
- TypeScript check and bundle: passed
- extension contract tests: `18` passed
- VS Code Extension Host smoke: exit code `0`
- bundled helper build: `docferry 0.4.4`
- native package verification: HTTPS health check passed

The local Apple Silicon package was:

- file: `docferry-vscode-0.2.5-darwin-arm64.vsix`
- size: `14,647,989` bytes
- SHA-256: `814783029b36d1a6047e1838abf3658234788d5a085054c6d598ac591901bde1`

Release CI must independently rebuild and verify macOS arm64, macOS x64,
Linux x64, and Windows x64 packages from the exact tagged commit. A successful
local candidate does not claim that GitHub Release or Marketplace publication
has already occurred.

## Publication Boundary

The four VSIX files are platform variants of one `bondie.docferry` extension
version. They must all come from the same checksummed GitHub Release and be
uploaded unchanged through the authenticated Bondie publisher page. This
repository intentionally stores no Marketplace PAT or Microsoft credential.
