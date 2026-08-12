# DocFerry for VS Code

Bring useful links into your project and share Markdown without leaving VS Code.
DocFerry works with ordinary folders and repositories; Obsidian is optional.

> **Preview:** `0.2.0` is the first Marketplace-oriented release candidate.
> Install and core features are free. Folder sharing and detailed notes from
> supported web, audio, and video sources require an optional DocFerry Pro
> subscription purchased outside the Marketplace.

## What you can do

- **Save a link** through one entrypoint. DocFerry imports its own share links,
  saves ordinary public URLs, and creates detailed notes for supported sources
  when the connected account has Pro access.
- **Share Markdown** from the editor or Explorer after a clear confirmation.
- **Share a folder** as one navigable collection with Pro access. Hidden files
  and paths outside the selected workspace stay excluded.
- **Manage shares** in the Activity Bar: open, copy, update, stop, and remove
  stopped history records.
- **Open DocFerry Dashboard** with a short-lived product handoff. Account and
  privacy settings remain secondary pages inside that dashboard.

## Start

1. Install **DocFerry** from the VS Code Marketplace or a checksummed release VSIX.
2. Open a trusted local folder or repository.
3. Open DocFerry in the Activity Bar and choose **Sign in or switch account**.
4. Approve the one-time code in your system browser.

The extension includes its required DocFerry helper. You do not need Python,
the DocFerry CLI, an Obsidian vault, or a separate authentication token.

## Free and Pro

| Capability | Free | Pro Monthly / Yearly |
| --- | --- | --- |
| Bondie sign-in and DocFerry Dashboard | Yes | Yes |
| Import a DocFerry share | Yes | Yes |
| Save an ordinary public URL | Yes | Yes |
| Active Markdown shares | 5 | 20 |
| Maximum shared Markdown file | 2 MiB | 10 MiB |
| Folder sharing | No | 5 active folders; up to 100 notes and 50 MiB each |
| Detailed notes from enabled sources | No | 1 active job; 30 jobs per month |

Monthly and yearly Pro plans have the same product features. Current limits are
returned by the signed-in DocFerry service and can be reviewed under **Plan and
usage** before an action. Plans, invoices, cancellation, and refunds are managed
on the DocFerry website; the extension never handles card details.

## Import behavior

Paste one public `http` or `https` URL into **Save a link**:

- A canonical DocFerry share is imported directly.
- An ordinary source saves a small link note when detailed processing does not
  apply.
- An eligible source asks permission before the URL is fetched and processed.
  Audio and video may take several minutes; VS Code shows cancellable progress.
- Bilibili, TikTok, and Douyin never silently fall back when their detailed-note
  lane is unavailable. Nothing is written, and DocFerry reports the condition.

Imported notes are written to `DocFerry Imports` by default. Change
`docferry.importFolder` to another visible folder inside the workspace.

## Privacy and security

DocFerry reads only content selected for an action. Publishing sends the chosen
Markdown or visible folder documents to `docferry.bondie.io`; Advanced Import
sends the confirmed public URL for hosted processing. The extension stores no
Auth0, Stripe, SynapseHub operator, or AI-provider credential.

Workspaces must be trusted and backed by a local filesystem. Commands use
argument arrays with `shell: false`, paths are contained to the chosen workspace,
and destructive actions require modal confirmation. See [Privacy](PRIVACY.md),
[Security](SECURITY.md), and [Support](SUPPORT.md).

## Development

The public repository is the review and release source for the extension. The
bundled helper is generated from the pinned DocFerry Agent Kit CLI source and
recorded in `runtime/PROVENANCE.json`.

```sh
npm ci
npm run build
npm run package:vsix
```

The package command builds a platform-specific VSIX. Release CI repeats the
build on macOS, Linux, and Windows and publishes checksums with the release.
See [Development](DEVELOPMENT.md) for the complete verification flow.
