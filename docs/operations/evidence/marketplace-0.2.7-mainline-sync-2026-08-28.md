# DocFerry VS Code 0.2.7 mainline sync evidence

Date: 2026-08-28

## Reviewed sources

- DocFerry mainline: `f78eae80a808f5f04e31d651a1db287b1e2d0a13`
- Public VS Code base: `5c0fa39a632dd4be219e5b1f51917007637ca6e0`
- Bundled Agent Kit: `0.4.6`
- Candidate extension: `0.2.7`

The review covered DocFerry `0.0.68` through the `0.0.72` Community review
candidate, Agent Kit `0.4.5` workspace identity, Agent Kit `0.4.6` local asset
publication, the production Device Code login response, and the public
Marketplace extension.

## Closed drift

- The extension accepts the current product-owned account-selection login URL
  and rejects alternate origins, prompts, return paths, and extra parameters.
- The bundled helper uses the current cross-surface workspace identity and
  claim/update contract shared by Obsidian, CLI, and MCP.
- Note and folder shares publish supported workspace-local images, audio,
  video, and attachments. Hidden, unsupported, missing, and outside-workspace
  files remain private.
- Omitted local references produce a concise user notice and redacted local
  troubleshooting output.
- Folder Share creation follows the authoritative
  `docferry.publish.folder` capability. Existing history remains visible.
- Public privacy, security, feature, development, and Marketplace copy now
  describe the same behavior as the package.

Checkout contract and hosted Dashboard navigation changes remain owned by the
DocFerry web/server surface and require no separate VS Code implementation.
Obsidian theme capture remains inapplicable outside Obsidian.

## Verification

- TypeScript check and bundle: passed.
- Contract tests: `21/21` passed.
- Extension Host test: passed on VS Code `1.96.4`.
- Marketplace release verifier tests: `4/4` passed.
- Public source verifier: passed, `61` source files, Agent Kit `0.4.6`.
- Agent Kit tests: `116` passed plus `20` subtests.
- npm audit: zero vulnerabilities.
- Production Device Code start returned the expected
  `https://docferry.bondie.io/v0/auth/login` account-selection URL and the
  extension trust contract accepted it.
- Isolated VSIX install: passed; signed-out Activity Bar showed a visible
  **Connect Bondie account** system-browser action and no Folder Share creation
  action.
- macOS arm64 VSIX: `14,665,895` bytes.
- VSIX SHA-256:
  `e9e9bed95aeceffd5fb7af675a1dcccc32e88fdb963f9830f2f0c3f6554b1913`.
- Bundled helper: `docferry 0.4.6`; production HTTPS health passed.

## Distribution boundary

The Visual Studio Marketplace still serves `bondie.docferry@0.2.4` at the time
of this review. Version `0.2.7` must pass public repository CI, be built for all
release targets, and be uploaded through the authenticated Bondie publisher
page before it can be described as the Marketplace version.
