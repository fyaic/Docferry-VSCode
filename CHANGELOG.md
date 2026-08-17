# Changelog

## 0.2.5 - 2026-08-17

### Fixed

- Removed stale `0.2.3` release-candidate copy from the Marketplace README and
  feature contract so the installed extension no longer advertises an older
  package than the one a user is running.
- Updated the manual Marketplace package gate and bug-report template to the
  current release version.
- Clarified that the four target-specific VSIX files are platform variants of
  one extension and Marketplace selects the matching package automatically.

### Distribution

- Kept the public `fyaic/Docferry-VSCode` repository as the sole review and
  release source. The bundled runtime remains DocFerry Agent Kit `0.4.4`.

## 0.2.4 - 2026-08-14

### Fixed

- Strip unused symbols from the Linux bundled helper so Marketplace upload and
  scanning stay below the extension's reliability budget without returning to
  the slower single-file runtime.
- Reject oversized VSIX artifacts during release verification instead of
  discovering the problem in the Marketplace upload flow.

## 0.2.3 - 2026-08-14

### Fixed

- Open system-browser sign-in before the extension begins its approval wait,
  with explicit open and copy-link recovery when the OS declines the request.
- Avoid a redundant bundled-helper version launch on the first user action.
- Package the helper as a self-contained runtime directory so macOS does not
  repeat first-launch security work for every command.
- Refresh share lists again after server projection settles.
- Keep a background detailed note visible in the Activity Bar and status bar
  until it is reviewed, saved, cancelled, or fails.
- Make whole-workspace folder sharing unmistakable before confirmation.

### Changed

- Updated the bundled and minimum Agent Kit version to `0.4.4`.

## 0.2.2 - 2026-08-13

### Fixed

- Made system-browser Device Code login tolerate bounded gateway and network
  interruptions without discarding an approval already in progress.

### Changed

- Updated the bundled and minimum Agent Kit version to `0.4.3`.

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
