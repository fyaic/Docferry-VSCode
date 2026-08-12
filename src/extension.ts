import path from "node:path";
import * as vscode from "vscode";

import { DocFerryCli } from "./cli";
import { DetailedNoteManager } from "./imports";
import {
  advancedImportDecision,
  classifyOperationError,
  dashboardCommandArgs,
  DashboardLinkResult,
  DashboardSection,
  isCanonicalDocFerryShareUrl,
  isPathInside,
  isShareActionable,
  isTrustedDashboardHandoffUrl,
  isTrustedDeviceLoginUrl,
  MembershipSummary,
  membershipLabel,
  operationErrorMessage,
  resolveWorkspaceOutput,
  SaveResult,
  VS_CODE_LOGIN_ARGS,
  validateImportFolder,
  workspaceRootForPath,
  workspaceRelativePath
} from "./contracts";
import { DocFerryTreeProvider, FolderShareNode, NoteShareNode } from "./tree";

const SUPPORT_URL = "https://github.com/fyaic/Docferry-VSCode/issues";

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("DocFerry", { log: true });
  const cli = new DocFerryCli(output, context.extensionPath);
  const detailedNotes = new DetailedNoteManager(context, cli);
  const tree = new DocFerryTreeProvider(cli);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 40);
  status.name = "DocFerry";
  status.text = "$(cloud-upload) DocFerry";
  status.tooltip = "Save a link to this workspace";
  status.command = "docferry.saveLink";
  if (vscode.workspace.workspaceFolders?.length) {
    status.show();
  }

  context.subscriptions.push(
    output,
    status,
    detailedNotes,
    vscode.window.registerTreeDataProvider("docferry.workspace", tree),
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      if (vscode.workspace.workspaceFolders?.length) {
        status.show();
      } else {
        status.hide();
      }
      tree.refresh();
      void detailedNotes.resume();
    }),
    vscode.commands.registerCommand("docferry.refresh", () => tree.refresh()),
    vscode.commands.registerCommand(
      "docferry.openDashboard",
      (section: DashboardSection = "home") => openDashboard(cli, section)
    ),
    vscode.commands.registerCommand("docferry.openUrl", (url: string) => openExternal(url)),
    vscode.commands.registerCommand("docferry.signIn", () => signIn(cli, tree, detailedNotes)),
    vscode.commands.registerCommand("docferry.signOut", () => signOut(cli, tree, detailedNotes)),
    vscode.commands.registerCommand("docferry.showMembership", () => showMembership(cli)),
    vscode.commands.registerCommand("docferry.shareCurrentFile", (uri?: vscode.Uri) => shareMarkdown(cli, tree, uri)),
    vscode.commands.registerCommand("docferry.shareFolder", (uri?: vscode.Uri) => shareFolder(cli, tree, uri)),
    vscode.commands.registerCommand("docferry.saveLink", () => saveLink(cli, tree, detailedNotes)),
    vscode.commands.registerCommand("docferry.checkDetailedNote", () => detailedNotes.check()),
    vscode.commands.registerCommand("docferry.cancelDetailedNote", () => detailedNotes.cancel()),
    vscode.commands.registerCommand("docferry.copyShareLink", (node: NoteShareNode | FolderShareNode) => copyShareLink(node)),
    vscode.commands.registerCommand("docferry.updateShare", (node: NoteShareNode) => updateShare(cli, tree, node)),
    vscode.commands.registerCommand(
      "docferry.updateFolderShare",
      (node: FolderShareNode) => updateFolderShare(cli, tree, node)
    ),
    vscode.commands.registerCommand("docferry.stopShare", (node: NoteShareNode) => stopShare(cli, tree, node)),
    vscode.commands.registerCommand(
      "docferry.stopFolderShare",
      (node: FolderShareNode) => stopFolderShare(cli, tree, node)
    ),
    vscode.commands.registerCommand(
      "docferry.deleteShareRecord",
      (node: NoteShareNode) => deleteShareRecord(cli, tree, node)
    ),
    vscode.commands.registerCommand(
      "docferry.deleteFolderShareRecord",
      (node: FolderShareNode) => deleteFolderShareRecord(cli, tree, node)
    )
  );
  void detailedNotes.resume();
}

export function deactivate(): void {}

async function signIn(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  detailedNotes?: DetailedNoteManager
): Promise<void> {
  if (detailedNotes && !(await detailedNotes.guardAccountChange())) {
    return;
  }
  const workspacePath = await pickWorkspacePath();
  if (!workspacePath) {
    return;
  }
  let loginOutput = "";
  let browserOpened = false;
  const result = await runWithProgress(
    "Finish signing in in your browser",
    (token) => cli.run(workspacePath, VS_CODE_LOGIN_ARGS, {
      label: "Sign in",
      token,
      onStdout: (chunk) => {
        loginOutput += chunk;
        if (browserOpened) {
          return;
        }
        const candidate = loginOutput.match(/https:\/\/[^\s]+/)?.[0];
        if (isTrustedDeviceLoginUrl(candidate)) {
          browserOpened = true;
          void openExternal(candidate);
        }
      }
    })
  );
  if (!result) {
    return;
  }
  tree.refresh();
  void vscode.window.showInformationMessage("DocFerry is connected to your Bondie account.");
}

async function openDashboard(cli: DocFerryCli, section: DashboardSection): Promise<void> {
  const workspacePath = await pickWorkspacePath();
  if (!workspacePath) {
    return;
  }
  const result = await runWithProgress(
    "Opening DocFerry Dashboard",
    (token) => cli.runJson<DashboardLinkResult>(workspacePath, dashboardCommandArgs(section), {
      label: `Open Dashboard: ${section}`,
      token,
      timeoutSeconds: 60
    })
  );
  if (!result) {
    return;
  }
  if (!isTrustedDashboardHandoffUrl(result.dashboard_url)) {
    void vscode.window.showErrorMessage("DocFerry returned an invalid Dashboard link.");
    return;
  }
  await openExternal(result.dashboard_url);
}

async function signOut(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  detailedNotes: DetailedNoteManager
): Promise<void> {
  if (!(await detailedNotes.guardAccountChange())) {
    return;
  }
  const workspacePath = await pickWorkspacePath();
  if (!workspacePath) {
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    "Sign out of DocFerry on this computer?",
    { modal: true },
    "Sign out"
  );
  if (approved !== "Sign out") {
    return;
  }
  const result = await runWithProgress(
    "Signing out of DocFerry",
    (token) => cli.run(workspacePath, ["logout"], { label: "Sign out", token, timeoutSeconds: 60 })
  );
  if (!result) {
    return;
  }
  tree.refresh();
  void vscode.window.showInformationMessage("Signed out of DocFerry.");
}

async function showMembership(cli: DocFerryCli): Promise<void> {
  const workspacePath = await pickWorkspacePath();
  if (!workspacePath) {
    return;
  }
  const membership = await runWithProgress(
    "Checking DocFerry plan and usage",
    (token) => cli.runJson<MembershipSummary>(workspacePath, ["membership"], {
      label: "Read plan and usage",
      token,
      timeoutSeconds: 60
    })
  );
  if (!membership) {
    return;
  }
  const action = await vscode.window.showInformationMessage(membershipLabel(membership), "Open dashboard");
  if (action === "Open dashboard") {
    await openDashboard(cli, "membership");
  }
}

async function shareMarkdown(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  candidate?: vscode.Uri
): Promise<void> {
  const uri = candidate?.scheme === "file" ? candidate : vscode.window.activeTextEditor?.document.uri;
  if (!uri || uri.scheme !== "file" || path.extname(uri.fsPath).toLowerCase() !== ".md") {
    void vscode.window.showInformationMessage("Open or select a Markdown file to share.");
    return;
  }
  const workspace = workspaceFolderForUri(uri);
  if (!workspace) {
    void vscode.window.showErrorMessage("The Markdown file must be inside an open VS Code workspace.");
    return;
  }
  const relative = workspaceRelativePath(workspace.uri.fsPath, uri.fsPath);
  const approved = await vscode.window.showWarningMessage(
    `Create a DocFerry link for “${path.basename(uri.fsPath)}”?`,
    { modal: true },
    "Share"
  );
  if (approved !== "Share") {
    return;
  }
  const result = await runWithProgress(
    "Sharing Markdown with DocFerry",
    (token) => cli.runJson<SaveResult>(workspace.uri.fsPath, ["share", relative, "--confirm"], {
      label: "Share Markdown",
      token,
      timeoutSeconds: 120
    })
  );
  if (result) {
    tree.refresh();
    await showPublishedResult(result, "Markdown shared.");
  }
}

async function shareFolder(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  candidate?: vscode.Uri
): Promise<void> {
  let uri = candidate?.scheme === "file" ? candidate : undefined;
  if (!uri) {
    const workspacePath = await pickWorkspacePath();
    if (!workspacePath) {
      return;
    }
    const picked = await vscode.window.showOpenDialog({
      canSelectFiles: false,
      canSelectFolders: true,
      canSelectMany: false,
      defaultUri: vscode.Uri.file(workspacePath),
      openLabel: "Share this folder"
    });
    uri = picked?.[0];
  }
  if (!uri) {
    return;
  }
  const workspace = workspaceFolderForUri(uri);
  if (!workspace) {
    void vscode.window.showErrorMessage("The folder must be inside an open VS Code workspace.");
    return;
  }
  const relative = workspaceRelativePath(workspace.uri.fsPath, uri.fsPath);
  const displayName = relative === "." ? workspace.name : path.basename(uri.fsPath);
  const approved = await vscode.window.showWarningMessage(
    `Share Markdown files in “${displayName}”?`,
    { modal: true, detail: "DocFerry will publish visible Markdown files in this folder and its subfolders." },
    "Share folder"
  );
  if (approved !== "Share folder") {
    return;
  }
  const result = await runWithProgress(
    "Sharing folder with DocFerry",
    (token) => cli.runJson<SaveResult>(workspace.uri.fsPath, ["share", relative, "--confirm"], {
      label: "Share folder",
      token,
      timeoutSeconds: 300
    })
  );
  if (result) {
    tree.refresh();
    await showPublishedResult(result, "Folder shared.");
  }
}

async function saveLink(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  detailedNotes: DetailedNoteManager
): Promise<void> {
  const workspacePath = await pickWorkspacePath();
  if (!workspacePath) {
    return;
  }
  const link = await vscode.window.showInputBox({
    title: "Save to this workspace",
    prompt: "Paste a DocFerry share, web page, audio, or video link",
    placeHolder: "https://…",
    ignoreFocusOut: true,
    validateInput: validatePublicUrl
  });
  if (!link) {
    return;
  }

  let outputFolder: string;
  try {
    outputFolder = validateImportFolder(
      vscode.workspace.getConfiguration("docferry").get<string>("importFolder", "DocFerry Imports")
    );
  } catch (error) {
    const action = await vscode.window.showErrorMessage(errorMessage(error), "Open settings");
    if (action === "Open settings") {
      await vscode.commands.executeCommand("workbench.action.openSettings", "docferry.importFolder");
    }
    return;
  }

  let membership: MembershipSummary = {};
  if (!isCanonicalDocFerryShareUrl(link)) {
    try {
      membership = await cli.runJson<MembershipSummary>(workspacePath, ["membership"], {
        label: "Check Import access",
        timeoutSeconds: 60
      });
    } catch (error) {
      if (classifyOperationError(error) !== "authentication") {
        await showOperationError(error);
        return;
      }
      const action = await vscode.window.showInformationMessage(
        "Sign in for a detailed note, or save this as a simple link.",
        "Sign in",
        "Save link only"
      );
      if (action === "Sign in") {
        await signIn(cli, tree);
        try {
          membership = await cli.runJson<MembershipSummary>(workspacePath, ["membership"], {
            label: "Check Import access after sign in",
            timeoutSeconds: 60
          });
        } catch (errorAfterLogin) {
          await showOperationError(errorAfterLogin);
          return;
        }
      } else if (action !== "Save link only") {
        return;
      }
    }
  }

  const importDecision = advancedImportDecision(link, membership);
  if (importDecision.reason === "mandatory_provider_unavailable") {
    void vscode.window.showErrorMessage(
      `Detailed notes are temporarily unavailable for ${importDecision.provider}. Nothing was saved.`
    );
    return;
  }
  const advanced = importDecision.eligible;
  if (advanced) {
    const approved = await vscode.window.showWarningMessage(
      "Create a detailed note from this link?",
      {
        modal: true,
        detail: "DocFerry will securely fetch and process the public link. Audio and video can take a few minutes; you can keep working while it finishes."
      },
      "Create note"
    );
    if (approved !== "Create note") {
      return;
    }
    try {
      await detailedNotes.start(workspacePath, link, outputFolder);
    } catch (error) {
      await showOperationError(error);
    }
    return;
  }

  const args = ["import", link, "--output", outputFolder];
  const result = await runWithProgress(
    "Saving link to workspace",
    (token) => cli.runJson<SaveResult>(workspacePath, args, {
      label: "Save link",
      token
    })
  );
  if (!result) {
    return;
  }
  tree.refresh();
  await openSavedResult(workspacePath, result);
  if (!isCanonicalDocFerryShareUrl(link)) {
    if (importDecision.reason === "not_entitled") {
      const action = await vscode.window.showInformationMessage(
        "Link saved. Detailed notes are available with DocFerry Pro.",
        "View plans"
      );
      if (action === "View plans") {
        await openDashboard(cli, "plans");
      }
    } else if (importDecision.reason === "runtime_disabled") {
      void vscode.window.showInformationMessage(
        "Link saved. Detailed-note processing is temporarily unavailable."
      );
    } else if (importDecision.reason === "provider_unsupported") {
      void vscode.window.showInformationMessage(
        "Link saved. Detailed notes are not available for this source yet."
      );
    }
  }
}

async function stopShare(cli: DocFerryCli, tree: DocFerryTreeProvider, node: NoteShareNode): Promise<void> {
  if (!node?.shareId || !isShareActionable(node.status)) {
    return;
  }
  const workspacePath = openWorkspaceContext(node.workspacePath);
  if (!workspacePath) {
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    `Stop sharing “${node.label}”?`,
    { modal: true, detail: "Its public DocFerry link will stop working." },
    "Stop sharing"
  );
  if (approved !== "Stop sharing") {
    return;
  }
  const result = await runWithProgress(
    "Stopping share",
    (token) => cli.runJson<SaveResult>(workspacePath, ["unshare", node.shareId, "--confirm"], {
      label: "Stop note share",
      token,
      timeoutSeconds: 60
    })
  );
  if (result) {
    tree.refresh();
    void vscode.window.showInformationMessage("Share stopped.");
  }
}

async function stopFolderShare(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: FolderShareNode
): Promise<void> {
  if (!node?.folderShareId || !isShareActionable(node.status)) {
    return;
  }
  const workspacePath = openWorkspaceContext(node.workspacePath);
  if (!workspacePath) {
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    `Stop sharing “${node.label}”?`,
    { modal: true, detail: "Its public DocFerry folder link will stop working." },
    "Stop sharing"
  );
  if (approved !== "Stop sharing") {
    return;
  }
  const result = await runWithProgress(
    "Stopping folder share",
    (token) => cli.runJson<SaveResult>(workspacePath, ["unshare", node.folderShareId, "--confirm"], {
      label: "Stop folder share",
      token,
      timeoutSeconds: 60
    })
  );
  if (result) {
    tree.refresh();
    void vscode.window.showInformationMessage("Folder share stopped.");
  }
}

async function copyShareLink(node: NoteShareNode | FolderShareNode): Promise<void> {
  if (!node?.url || !isShareActionable(node.status)) {
    return;
  }
  await vscode.env.clipboard.writeText(node.url);
  void vscode.window.showInformationMessage("DocFerry link copied.");
}

async function updateShare(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: NoteShareNode
): Promise<void> {
  if (!node?.shareId || !node.sourcePath || !isShareActionable(node.status)) {
    void vscode.window.showInformationMessage("This share has no source file in the current workspace.");
    return;
  }
  const workspacePath = openWorkspaceContext(node.workspacePath);
  if (!workspacePath) {
    return;
  }
  const sourcePath = node.sourcePath;
  const source = path.resolve(workspacePath, sourcePath);
  if (!isPathInside(workspacePath, source) || path.extname(source).toLowerCase() !== ".md") {
    void vscode.window.showErrorMessage("The shared Markdown source is no longer inside this workspace.");
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    `Replace the public version of “${node.label}” with the current file?`,
    { modal: true, detail: "The existing link stays the same." },
    "Update share"
  );
  if (approved !== "Update share") {
    return;
  }
  const result = await runWithProgress(
    "Updating shared Markdown",
    (token) => cli.runJson<SaveResult>(workspacePath, ["update", node.shareId, sourcePath, "--password-mode", "keep"], {
      label: "Update note share",
      token,
      timeoutSeconds: 120
    })
  );
  if (result) {
    tree.refresh();
    void vscode.window.showInformationMessage("Shared Markdown updated.");
  }
}

async function updateFolderShare(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: FolderShareNode
): Promise<void> {
  if (!node?.folderShareId || !node.sourcePath || !isShareActionable(node.status)) {
    void vscode.window.showInformationMessage("This share has no source folder in the current workspace.");
    return;
  }
  const workspacePath = openWorkspaceContext(node.workspacePath);
  if (!workspacePath) {
    return;
  }
  const sourcePath = node.sourcePath;
  const source = path.resolve(workspacePath, sourcePath);
  if (!isPathInside(workspacePath, source)) {
    void vscode.window.showErrorMessage("The shared folder is no longer inside this workspace.");
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    `Replace the public version of “${node.label}” with the current folder?`,
    { modal: true, detail: "The existing folder link stays the same." },
    "Update folder"
  );
  if (approved !== "Update folder") {
    return;
  }
  const result = await runWithProgress(
    "Updating shared folder",
    (token) => cli.runJson<SaveResult>(workspacePath, [
      "folder",
      "publish",
      sourcePath,
      "--folder-share-id",
      node.folderShareId
    ], {
      label: "Update folder share",
      token,
      timeoutSeconds: 300
    })
  );
  if (result) {
    tree.refresh();
    void vscode.window.showInformationMessage("Shared folder updated.");
  }
}

async function deleteShareRecord(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: NoteShareNode
): Promise<void> {
  await deleteHistoryRecord(cli, tree, node, node.shareId);
}

async function deleteFolderShareRecord(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: FolderShareNode
): Promise<void> {
  await deleteHistoryRecord(cli, tree, node, node.folderShareId);
}

async function deleteHistoryRecord(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  node: NoteShareNode | FolderShareNode,
  shareId: string
): Promise<void> {
  if (!shareId || isShareActionable(node.status)) {
    return;
  }
  const workspacePath = openWorkspaceContext(node.workspacePath);
  if (!workspacePath) {
    return;
  }
  const approved = await vscode.window.showWarningMessage(
    `Permanently remove “${node.label}” from sharing history?`,
    { modal: true, detail: "This does not delete the source file or folder from your workspace." },
    "Delete history"
  );
  if (approved !== "Delete history") {
    return;
  }
  const result = await runWithProgress(
    "Deleting stopped share history",
    (token) => cli.runJson<SaveResult>(workspacePath, ["delete-history", shareId, "--confirm"], {
      label: "Delete share history",
      token,
      timeoutSeconds: 60
    })
  );
  if (result) {
    tree.refresh();
    void vscode.window.showInformationMessage("Stopped share removed from history.");
  }
}

function workspaceFolderForUri(uri: vscode.Uri): vscode.WorkspaceFolder | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length || uri.scheme !== "file") {
    return undefined;
  }
  const root = workspaceRootForPath(
    folders.map((folder) => folder.uri.fsPath),
    uri.fsPath
  );
  return root ? folders.find((folder) => folder.uri.fsPath === root) : undefined;
}

function openWorkspaceContext(workspacePath: string | undefined): string | undefined {
  if (workspacePath && vscode.workspace.workspaceFolders?.some(
    (folder) => isPathInside(folder.uri.fsPath, workspacePath)
      && isPathInside(workspacePath, folder.uri.fsPath)
  )) {
    return workspacePath;
  }
  void vscode.window.showInformationMessage("Refresh DocFerry after changing workspace folders.");
  return undefined;
}

async function pickWorkspacePath(): Promise<string | undefined> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders?.length) {
    void vscode.window.showInformationMessage("Open a folder in VS Code to use DocFerry.");
    return undefined;
  }
  if (folders.length === 1) {
    return folders[0].uri.fsPath;
  }
  const picked = await vscode.window.showQuickPick(
    folders.map((folder) => ({ label: folder.name, description: folder.uri.fsPath, folder })),
    { title: "Choose a workspace for DocFerry", placeHolder: "Workspace" }
  );
  return picked?.folder.uri.fsPath;
}

async function runWithProgress<T>(
  title: string,
  operation: (token: vscode.CancellationToken) => Promise<T>
): Promise<T | undefined> {
  try {
    return await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title, cancellable: true },
      async (_progress, token) => await operation(token)
    );
  } catch (error) {
    await showOperationError(error);
    return undefined;
  }
}

async function showOperationError(error: unknown): Promise<void> {
  const kind = classifyOperationError(error);
  if (kind === "cancelled") {
    return;
  }
  if (kind === "missing") {
    const action = await vscode.window.showErrorMessage(
      "DocFerry's bundled helper could not start. Reinstall the extension or configure an external CLI.",
      "Get support",
      "Configure path"
    );
    if (action === "Get support") {
      await openExternal(SUPPORT_URL);
    } else if (action === "Configure path") {
      await vscode.commands.executeCommand("workbench.action.openSettings", "docferry.cliPath");
    }
    return;
  }
  if (kind === "incompatible") {
    const action = await vscode.window.showErrorMessage(operationErrorMessage(error), "Reinstall extension");
    if (action === "Reinstall extension") {
      await vscode.commands.executeCommand("workbench.extensions.action.showExtensionsWithIds", ["bondie.docferry"]);
    }
    return;
  }
  if (kind === "authentication") {
    const action = await vscode.window.showErrorMessage("Sign in to DocFerry to continue.", "Sign in");
    if (action === "Sign in") {
      await vscode.commands.executeCommand("docferry.signIn");
    }
    return;
  }
  if (kind === "entitlement") {
    const action = await vscode.window.showErrorMessage("This action needs DocFerry Pro.", "View plans");
    if (action === "View plans") {
      await vscode.commands.executeCommand("docferry.openDashboard", "plans");
    }
    return;
  }
  void vscode.window.showErrorMessage(operationErrorMessage(error));
}

function isAuthenticationError(error: unknown): boolean {
  return classifyOperationError(error) === "authentication";
}

function errorMessage(error: unknown): string {
  return operationErrorMessage(error);
}

function validatePublicUrl(value: string): string | undefined {
  try {
    const url = new URL(value.trim());
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
      return "Paste a public http or https link without embedded credentials.";
    }
    return undefined;
  } catch {
    return "Paste a complete public link.";
  }
}

async function showPublishedResult(result: SaveResult, fallback: string): Promise<void> {
  if (!result.url) {
    void vscode.window.showInformationMessage(fallback);
    return;
  }
  const action = await vscode.window.showInformationMessage(fallback, "Copy link", "Open");
  if (action === "Copy link") {
    await vscode.env.clipboard.writeText(result.url);
    void vscode.window.showInformationMessage("DocFerry link copied.");
  } else if (action === "Open") {
    await openExternal(result.url);
  }
}

async function openSavedResult(workspacePath: string, result: SaveResult): Promise<void> {
  if (!result.output) {
    void vscode.window.showInformationMessage("Saved to this workspace.");
    return;
  }
  try {
    const output = resolveWorkspaceOutput(workspacePath, result.output);
    const document = await vscode.workspace.openTextDocument(vscode.Uri.file(output));
    await vscode.window.showTextDocument(document, { preview: false });
  } catch (error) {
    void vscode.window.showErrorMessage(errorMessage(error));
  }
}

async function openExternal(value: string): Promise<void> {
  try {
    const uri = vscode.Uri.parse(value, true);
    if (uri.scheme !== "https" || !uri.authority) {
      throw new Error("DocFerry only opens secure web links.");
    }
    await vscode.env.openExternal(uri);
  } catch (error) {
    void vscode.window.showErrorMessage(errorMessage(error));
  }
}
