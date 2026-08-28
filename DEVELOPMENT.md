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

`sync:agent-kit` refreshes the five pinned CLI runtime files when this directory
is built inside the DocFerry monorepo. From a standalone public checkout, set
`DOCFERRY_MONOREPO_ROOT` to a reviewed DocFerry mainline checkout when advancing
the vendored runtime. With no source checkout configured, the command verifies
and preserves the runtime recorded in `runtime/PROVENANCE.json`.

The generated VSIX is platform-specific because it contains a native helper and
its private runtime directory under `bin/helper/`. Never copy that directory
between operating systems or CPU architectures. Release CI builds each supported
target on its matching GitHub-hosted runner.

## Release discipline

1. Update `package.json`, `CHANGELOG.md`, and runtime provenance together.
2. Pass TypeScript, unit, Extension Host, npm audit, helper, and VSIX content
   verification gates.
3. Publish a GitHub prerelease for preview versions.
4. Promote the exact checksummed VSIX files to Visual Studio Marketplace.
5. Keep publisher credentials only in the protected GitHub environment. Never
   place them in repository variables, source, release assets, or local config.
