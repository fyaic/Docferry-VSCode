# Development

## Requirements

- Node.js 20 or newer
- Python 3.11 or newer for rebuilding the bundled helper
- VS Code 1.96 or newer

## Local verification

```sh
npm ci
npm audit --audit-level=high
npm run build
npm run sync:agent-kit
npm run build:helper
npm run package:vsix
```

`sync:agent-kit` refreshes the three pinned CLI runtime files when this directory
is built inside the private DocFerry monorepo. In the public release repository,
it verifies and preserves the vendored runtime recorded in
`runtime/PROVENANCE.json`.

The generated VSIX is platform-specific because it contains a native helper.
Never copy a helper between operating systems or CPU architectures. Release CI
builds each supported target on its matching GitHub-hosted runner.

## Release discipline

1. Update `package.json`, `CHANGELOG.md`, and runtime provenance together.
2. Pass TypeScript, unit, Extension Host, npm audit, helper, and VSIX content
   verification gates.
3. Publish a GitHub prerelease for preview versions.
4. Promote the exact checksummed VSIX files to Visual Studio Marketplace.
5. Keep publisher credentials only in the protected GitHub environment. Never
   place them in repository variables, source, release assets, or local config.
