# Security Policy

## Supported versions

The newest Marketplace release and the newest preview release receive security
fixes. Upgrade before reporting a defect that may already be resolved.

## Report a vulnerability

Do not open a public issue for a suspected vulnerability. Email
`support@bondie.io` with the subject `DocFerry VS Code security report` and
include the smallest safe reproduction, affected version, impact, and a secure
way to follow up. Do not include active credentials or private user content.

## Product boundary

- The extension runs only in trusted, filesystem-backed workspaces.
- The bundled helper is version-checked before use and starts with `shell: false`.
- Workspace paths are canonicalized, bounded to an open workspace, and checked
  against symbolic-link escapes.
- Referenced local files are resolved only inside the selected workspace;
  hidden and unsupported files are excluded, and references inside code or
  comments are not treated as publishable assets.
- Authentication uses a short-lived Device Code approval in the system browser.
- Publishing, stopping links, and deleting stopped history require explicit
  confirmation. The server independently enforces ownership and state.
- No Auth0, Stripe, SynapseHub operator, OpenRouter, or infrastructure secret is
  distributed in source code or VSIX files.

See [PRIVACY.md](PRIVACY.md) for the data-flow disclosure.
