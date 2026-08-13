# Changelog

## 0.2.1 - 2026-08-13

### Fixed

- Bundled the Mozilla CA trust store and configured the frozen helper to use it
  when the host has not supplied an explicit certificate path.
- Added a real DocFerry HTTPS health request to every platform's VSIX release
  verification so a package with a broken TLS trust chain cannot be published.

## 0.2.0 - 2026-08-12

### Added

- Marketplace metadata, Preview channel, privacy/support/security disclosures,
  and a platform-specific bundled DocFerry helper.
- System-browser Device Code login suitable for local and Remote/SSH workspaces.
- Copy, update, stop, and confirmed deletion actions for note and folder shares.
- Current Pro Advanced Import usage and 30-job monthly product limit.

### Changed

- Updated the minimum Agent Kit contract from `0.2.5` to `0.4.2`.
- Unified file and folder publication through the confirmed `share` contract.
- Mandatory Bilibili, TikTok, and Douyin sources no longer silently downgrade.
- Hidden organization access is rendered generically and is not advertised as a
  purchasable plan.

## 0.1.7 - 2026-07-23

- Closed filesystem alias, multi-root workspace, stopped-action, error
  classification, and provider preflight defects in the internal preview.
