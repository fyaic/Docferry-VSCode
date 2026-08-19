# Marketplace publisher verification deferral

Date: 2026-08-19

## Determination

Visual Studio Marketplace Support responded on `2026-08-18` that the Bondie
publisher-domain request cannot be approved yet. The reason is the Marketplace
track-record prerequisite, not a DNS, HTTPS, extension-package, publisher-name,
or account-ownership defect.

The [official publishing guide](https://code.visualstudio.com/api/working-with-extensions/publishing-extension#verify-a-publisher)
requires both of the following before a publisher applies:

- one or more extensions must have been in VS Marketplace for at least six
  months;
- the registered domain must be at least six months old.

## Eligibility dates

- Registry creation for `bondie.io`: `2026-05-14T02:47:11Z`
- Domain six-month threshold: `2026-11-14`
- First `bondie.docferry` Marketplace packages: August 2026
- Safe operational reapplication date: `2027-02-13` or later

The extension age is the later constraint. Repeated submission before the
operational date cannot satisfy the published prerequisite.

## Current boundary

- Keep `https://bondie.io` on publisher `bondie`.
- Preserve DNS control and the existing Marketplace TXT record.
- Do not change the publisher display name while preparing for verification.
- Continue publishing and testing DocFerry releases normally.
- Do not describe `isDomainVerified=false` as a product-release blocker.
- Reapply on or after `2027-02-13` and retain only a low-sensitivity decision
  record; do not commit support email headers, account identifiers, or tokens.

The public Gallery API still reported `isDomainVerified=false` on `2026-08-19`,
which is now the expected state until a future eligible application is approved.
