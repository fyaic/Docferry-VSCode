# Contributing

DocFerry for VS Code is source-visible proprietary software. Bug reports and
focused design feedback are welcome. Submit code only when a Bondie maintainer
has agreed to the scope and contribution terms in advance.

## Before opening an issue

1. Reproduce on the newest Marketplace or Preview release.
2. Check existing issues without posting private workspace content.
3. Include the versions and redacted environment details listed in
   [SUPPORT.md](SUPPORT.md).

## Pull requests

- Keep product authentication, membership, billing, and AI-provider ownership
  in DocFerry's hosted service and Agent Kit contract.
- Use VS Code native controls and ThemeIcon values; do not add custom webviews
  for ordinary commands or navigation.
- Preserve workspace trust, path containment, explicit confirmation, and
  output-redaction boundaries.
- Update tests, changelog, privacy disclosure, and runtime provenance when the
  corresponding behavior changes.
- Run the full verification sequence in [DEVELOPMENT.md](DEVELOPMENT.md).

By submitting a contribution, you confirm that you have the right to provide
it and agree that Bondie may distribute it under the repository license.
