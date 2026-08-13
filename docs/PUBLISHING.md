# Visual Studio Marketplace publishing

## One-time publisher setup

1. Sign in to https://marketplace.visualstudio.com/manage/publishers/ with the
   company-controlled Microsoft account.
2. Create publisher ID `bondie` and display name `Bondie`. The ID cannot be
   changed later, so verify spelling and ownership before submission.
3. Fill the company profile from [PUBLISHER_PROFILE.md](PUBLISHER_PROFILE.md),
   including the checked 128 x 128 Bondie mark.
4. Save the publisher, then verify ownership of `bondie.io` using the exact DNS
   record shown by Marketplace.
5. Add a second company-controlled owner so publisher recovery does not depend
   on one Microsoft account.
6. Accept the current Visual Studio Marketplace Publisher Agreement.
7. Create the `bondie.docferry` extension by uploading all four `0.2.0` Preview
   VSIX files from the same checksummed GitHub prerelease.

The first submission should be manual so the publisher identity, listing copy,
privacy links, pricing disclosure, and platform selection can be reviewed in
the portal before anything is public.

## Release artifacts

Release CI builds these targets on matching native runners:

- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `win32-x64`

Do not rename one platform artifact to another target. Each VSIX contains a
native helper and must pass `scripts/verify_vsix.py` on its build runner.

## Automated publishing after first approval

Use a protected `visual-studio-marketplace` deployment environment and
Microsoft Entra ID workload identity. Add the managed identity to the Bondie
publisher as **Contributor**, then publish with `vsce publish --azure-credential`.
Do not create a long-lived global Azure DevOps PAT; Microsoft retires global
PATs on December 1, 2026.

Automated Marketplace publication remains intentionally absent until the
publisher and Entra identity exist. GitHub release automation contains no
publisher credential and cannot submit to Marketplace by itself.
