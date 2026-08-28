# Privacy

Last updated: August 28, 2026.

DocFerry for VS Code connects to the hosted DocFerry service at
`docferry.bondie.io`. The extension does not contain advertising SDKs or sell
personal information.

## Data used by an action

- **Sign in:** the product receives a one-time device authorization request,
  the extension version, operating-system description, and a random local
  instance identifier. Authentication completes in the system browser.
- **Share Markdown:** the selected Markdown, title, workspace-relative source
  path, content hash, publication settings, and supported referenced local
  images, audio, video, or attachments are sent only after confirmation.
- **Share a folder:** visible Markdown in the selected folder, relative paths,
  titles, hashes, publication settings, and supported referenced local files are
  sent only after confirmation. Hidden files, unsupported files, and paths
  outside the workspace are excluded.
- **Import a DocFerry share:** the selected share URL and optional password are
  sent to retrieve the document and assets.
- **Detailed note:** the confirmed public source URL is sent to DocFerry's
  hosted processing service. Its enabled providers may use contracted AI and
  media-processing subprocessors. The current product privacy policy governs
  retention and subprocessors.
- **Billing:** plans and receipts open on the DocFerry website. The extension
  does not receive or store card details.

## Data kept on the device

The bundled helper stores the DocFerry product session and a random instance
identifier in the user's operating-system configuration directory. Imported
notes are written only inside the selected workspace. The extension does not
write credentials to workspace settings or source-control files.

While one detailed note is pending, VS Code global storage keeps only its job
identifier, creation time, original workspace path, and destination folder so
the extension can resume after reload. It does not store the source URL or
generated Markdown there, and clears the record after save, cancellation, or a
terminal failure.

The DocFerry output channel records operation names, redacted error details, and
local warnings when referenced files cannot be published. A warning may contain
a redacted local file name or path for troubleshooting, but never the file
content. The channel does not intentionally log session tokens, imported
content, shared Markdown, share URLs, or titles, and remains on the device.

## Controls

Sign out from the DocFerry view to remove the local product session. Stop a
public share to disable its link. Stopped history can be removed separately;
this does not delete the local source. Account access, export, correction, and
deletion requests are available through DocFerry Dashboard or
`support@bondie.io`.

The authoritative hosted-service policy is available at
https://docferry.bondie.io/privacy.
