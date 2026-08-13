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
7. Create the `bondie.docferry` extension by publishing all four `0.2.0`
   Preview VSIX files from the same checksummed GitHub prerelease.

Preview `0.2.0` was first published with a short-lived Microsoft Entra token
after local package and identity verification. Future submissions must run
through the protected `Visual Studio Marketplace` workflow. Select `verify`
first, review its evidence, then select `publish`. This preserves the same
manual approval boundary while ensuring all four packages come from the
accepted GitHub release.

## Release artifacts

Release CI builds these targets on matching native runners:

- `darwin-arm64`
- `darwin-x64`
- `linux-x64`
- `win32-x64`

Do not rename one platform artifact to another target. Each VSIX contains a
native helper and must pass `scripts/verify_vsix.py` on its build runner.

## One-time Microsoft Entra setup

The publishing workflow uses GitHub OIDC and Microsoft Entra ID. It does not
store a Marketplace PAT or an application secret.

1. In Microsoft Entra, create an application named
   `bondie-docferry-marketplace-publisher` and record its Application (client)
   ID and Directory (tenant) ID.
2. Add a federated identity credential to the application with:
   - Issuer: `https://token.actions.githubusercontent.com`
   - Audience: `api://AzureADTokenExchange`
   - Subject:
     `repo:fyaic/Docferry-VSCode:environment:visual-studio-marketplace`
3. Configure `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` as variables on the
   repository's protected `visual-studio-marketplace` environment.
4. Run **Visual Studio Marketplace** with operation `profile`. The workflow
   requests the Azure DevOps profile using resource
   `499b84ac-1321-427f-aa17-267ca6975798` and records the low-sensitivity
   profile `id` in its summary and evidence artifact.
5. On the Marketplace publisher **Members** tab, add that profile ID as a
   **Contributor**, never as an Owner.
6. Run **Visual Studio Marketplace** with operation `verify`. It must pass
   package validation and `vsce verify-pat --azure-credential bondie` before a
   publish run is approved.

The environment requires an explicit reviewer. The `publish` operation is the
only step that uploads packages to Marketplace.

## Publishing a release

1. Confirm the GitHub release contains exactly four target-specific VSIX files
   and `SHA256SUMS`.
2. Run **Visual Studio Marketplace** with the release tag and operation
   `verify`.
3. Review the retained `verification.json` evidence.
4. Run it again with operation `publish` and approve the protected environment.
5. Check `bondie.docferry` in Marketplace for the version, Preview badge, Free
   pricing, and all four target platforms.

The workflow downloads, checksums, and statically validates the release assets;
it never rebuilds a second set of packages at publication time. Re-running a
successful publish is safe because duplicate target versions are skipped.

## Publishing security

Use a protected `visual-studio-marketplace` deployment environment and
Microsoft Entra ID workload identity. Add the managed identity to the Bondie
publisher as **Contributor**, then publish with `vsce publish --azure-credential`.
Do not create a long-lived global Azure DevOps PAT; Microsoft retires global
PATs on December 1, 2026.

GitHub release automation contains no publisher credential and cannot submit to
Marketplace by itself. Marketplace publication remains a separate, manually
approved workflow.
