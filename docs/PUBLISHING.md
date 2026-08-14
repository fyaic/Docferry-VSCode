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
7. Create the `bondie.docferry` extension by publishing all four target-specific
   Preview VSIX files from the same checksummed GitHub release.

The current publisher Owner is a company-controlled personal Microsoft account,
not an identity in a company Microsoft Entra tenant. Releases therefore use a
guarded manual upload: GitHub Actions verifies the exact release assets first,
then the signed-in Owner uploads those same files through the Marketplace
publisher page. The repository stores no Marketplace PAT, Microsoft password,
or application secret.

## Release artifacts

Release CI builds these targets on matching native runners:

- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `win32-x64`

Do not rename one platform artifact to another target. Each VSIX contains a
native helper and must pass `scripts/verify_vsix.py` on its build runner.

## Current publishing identity boundary

Do not configure arbitrary `AZURE_CLIENT_ID` or `AZURE_TENANT_ID` values for the
current personal-account Owner. GitHub OIDC can publish only after Bondie has a
dedicated Microsoft Entra identity whose Azure DevOps profile has explicitly
been added to publisher `bondie` as a Contributor.

Until that identity exists, `.github/workflows/marketplace.yml` is deliberately
a package gate only. It has `contents: read`, requests no GitHub OIDC token, and
cannot upload or modify a Marketplace extension. This avoids a workflow that
appears automated but always fails against the real publisher ownership model.

## Publishing a release

1. Confirm the GitHub release contains exactly four target-specific VSIX files
   and `SHA256SUMS`.
2. Run **Visual Studio Marketplace Package Gate** with the release tag.
3. Review the retained `verification.json` evidence.
4. Download the exact four VSIX assets from that release and verify them locally
   with `shasum -a 256 -c SHA256SUMS`.
5. Sign in to the Bondie publisher page with its company-controlled Owner and
   upload each target-specific VSIX through **More actions > Update**. Do not
   rebuild, rename, or substitute a package during this step.
6. Check `bondie.docferry` in Marketplace for the version, Preview badge, Free
   pricing, and all four target platforms.
7. Install `bondie.docferry` from Marketplace into a clean VS Code extensions
   directory and verify the installed version, target platform, helper version,
   checksum, activation, account status, and primary share/import commands.

The workflow downloads, checksums, and statically validates the release assets;
it never rebuilds a second set of packages at publication time.

## Publishing security

Do not create a long-lived global Azure DevOps PAT for convenience. The current
manual Owner upload is protected by Microsoft sign-in and Marketplace's upload
checks, while the public release checksum proves exactly which packages were
accepted. Record only low-sensitivity version, target, digest, and test evidence.

If Bondie later provisions a dedicated Entra publishing identity, add it to the
publisher as **Contributor**, keep Owner recovery separate, protect the GitHub
deployment environment with a reviewer, and introduce OIDC publishing in a
separately reviewed change. GitHub release automation currently contains no
publisher credential and cannot submit to Marketplace by itself.
