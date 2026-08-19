# Marketplace 0.2.5 GitHub Release

Date: 2026-08-17

## Qualified Boundary

Public `main@2e60155ba2e536a312df2266fc5f71f375de3c97` passed the complete
five-job Quality workflow. Annotated tag `v0.2.5` points to that exact merge
commit.

The [Release workflow](https://github.com/fyaic/Docferry-VSCode/actions/runs/32012776049)
completed successfully and created the checksummed
[`v0.2.5` GitHub prerelease](https://github.com/fyaic/Docferry-VSCode/releases/tag/v0.2.5).
All four jobs independently verified the tag/version match, npm audit, source,
bundled Agent Kit `0.4.4`, native helper, VSIX manifest, package size, and
production HTTPS health.

The separate [Marketplace Package Gate](https://github.com/fyaic/Docferry-VSCode/actions/runs/32013147821)
downloaded the published assets rather than rebuilding them and passed source,
target, manifest, checksum, and package-count verification.

## Release Assets

| Target | Bytes | SHA-256 |
| --- | ---: | --- |
| `darwin-arm64` | 15,731,036 | `efe48206616a0154ea122d26baee8e280a769cb54ed3016ce85b5b6ea17688df` |
| `darwin-x64` | 16,795,070 | `607da7edebddbaa99e5749a94645c18e75bc86c8dd34d6157bebd9311a739ba3` |
| `linux-x64` | 8,671,902 | `a3cb0bb89dd10d00687bb9d18ba1024de07c80b81d5c706f95acfa3cd950e140` |
| `win32-x64` | 9,437,698 | `ae5834bb5bfeeff9c0767bf0e7a47533ca3e7cbb6db00cae2a98e86f17115263` |

The downloaded release assets were rechecked locally with `SHA256SUMS` and
`scripts/verify_marketplace_release.py`; all four variants passed.

## Marketplace State

At the time of this record, the public Marketplace API still returned four
target variants for `bondie.docferry@0.2.4` and reported
`publisher.isDomainVerified=false`. Therefore this evidence does not claim that
`0.2.5` is installed from Marketplace or that the publisher badge is visible.

Marketplace Support subsequently confirmed on `2026-08-18` that the badge is
ineligible until both `bondie.io` and a published extension have at least six
months of track record. Reapplication is scheduled for `2027-02-13` or later;
the badge does not gate release uploads.

The remaining publication step is an authenticated Owner upload of these exact
four `0.2.5` VSIX files. After Marketplace processing, acceptance must confirm
all four targets, the visible `0.2.5` version, the corrected packaged README,
the publisher badge state, and a clean store install of the matching local
platform package.
