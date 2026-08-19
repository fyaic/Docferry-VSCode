# Bondie Marketplace publisher profile

Use this copy for the company-level Visual Studio Marketplace publisher. Keep
product plans, quotas, release status, and DocFerry-only claims on the extension
listing rather than the publisher profile.

## Submission values

| Marketplace field | Value |
| --- | --- |
| Publisher name | `Bondie` |
| Publisher ID | `bondie` |
| Verified domain | `https://bondie.io` |
| Company website | `https://bondie.io` |
| Support | `support@bondie.io` |
| Source repository | `https://github.com/fyaic` |
| LinkedIn | Leave blank until Bondie has an official company page. |
| X / Twitter | Leave blank until Bondie has an official organization account. |
| Logo | `resources/bondie-publisher-128.png` |

## Description

```text
Bondie builds thoughtful software for capturing, organizing, and sharing knowledge across the tools people already use. Our products combine clear user control, privacy-aware workflows, and dependable integrations for individual and team work.
```

The description is intentionally company-level. DocFerry-specific listing copy
belongs in `README.md`, where Free and Pro capabilities are disclosed.

## Review before creation

- Confirm that `bondie` is available and selected as the publisher ID. The ID is
  referenced by the extension manifest as `bondie.docferry`.
- Confirm the signed-in Microsoft account is company-controlled and protected by
  MFA. Do not use a disposable personal account as the sole owner.
- Review the current Visual Studio Marketplace Publisher Agreement before
  selecting **Create**.
- Upload the square 128 x 128 PNG from this repository. It is derived from the
  canonical Bondie mark used by `bondie.io`.
- Leave unsupported social profiles blank. Do not substitute a founder's
  personal profile.

## After creation

1. Save the publisher before starting domain verification.
2. Keep `https://bondie.io` as the publisher domain and preserve control of the
   Marketplace DNS TXT record. Do not resubmit trusted-publisher verification
   before `2027-02-13`; both the domain registration and at least one published
   extension must independently be at least six months old.
3. Add a second company-controlled owner so the publisher has no single-person
   recovery dependency.
4. Keep human accounts at the minimum role needed. Use a Contributor identity,
   not an Owner identity, for future automated publishing.
5. Upload all four target-specific VSIX assets from the same checksummed GitHub
   prerelease for the first `bondie.docferry` submission.

## Trusted-publisher eligibility

Domain ownership and the Marketplace verified badge are separate states. The
domain is configured correctly, but Marketplace Support deferred the badge on
2026-08-18 because the required track record is not yet old enough.

- `bondie.io` was registered on `2026-05-14`; its six-month threshold is
  `2026-11-14`.
- `bondie.docferry` first entered Marketplace in August 2026; the extension
  threshold is the later constraint.
- Reapply on or after `2027-02-13`, then retain Marketplace's review response as
  low-sensitivity release evidence.

The missing badge does not block publishing, installation, updates, billing, or
the Preview channel. See the
[official verified-publisher prerequisites](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#verify-a-publisher).
