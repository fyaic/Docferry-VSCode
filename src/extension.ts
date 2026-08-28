import os from "node:os";
import path from "node:path";
import * as vscode from "vscode";

import { DocFerryCli } from "./cli";
import { DetailedNoteManager } from "./imports";
import {
  advancedImportDecision,
  accountContextPath,
  AuthStatusSummary,
  canCreateFolderShare,
  classifyOperationError,
  dashboardCommandArgs,
  DashboardLinkResult,
  DashboardSection,
  DeviceLoginStartResult,
  folderShareConfirmation,
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
  VS_CODE_LOGIN_COMPLETE_ARGS,
  VS_CODE_LOGIN_START_ARGS,
  validateImportFolder,
  workspaceRootForPath,
  workspaceRelativePath
} from "./contracts";
import { AccountState, DocFerryTreeProvider, FolderShareNode, NoteShareNode } from "./tree";

const SUPPORT_URL = "https://github.com/fyaic/Docferry-VSCode/issues";

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("DocFerry", { log: true });
  const cli = new DocFerryCli(output, context.extensionPath);
  const detailedNotes = new DetailedNoteManager(context, cli);
  const tree = new DocFerryTreeProvider(cli, detailedNotes);
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 40);
  let accountState: AccountState = "checking";
  status.name = "DocFerry";
  const updateStatus = () => {
    const detailedNote = detailedNotes.indicator();
    if (detailedNote) {
      status.text = `${detailedNote.ready ? "$(check)" : "$(sync~spin)"} Detailed note`;
      status.tooltip = detailedNote.description;
      status.command = "docferry.checkDetailedNote";
      return;
    }
    if (accountState === "signedIn") {
      status.text = "$(cloud-upload) DocFerry";
      status.tooltip = "Save a link to this workspace";
      status.command = "docferry.saveLink";
      return;
    }
    if (accountState === "checking") {
      status.text = "$(sync~spin) DocFerry";
      status.tooltip = "Checking your DocFerry account";
      status.command = "docferry.refresh";
      return;
    }
    if (accountState === "error") {
      status.text = "$(warning) DocFerry";
      status.tooltip = "DocFerry could not check your account. Select to try again.";
      status.command = "docferry.refresh";
      return;
    }
    status.text = "$(account) Connect DocFerry";
    status.tooltip = "Connect your Bondie account in the system browser";
    status.command = "docferry.signIn";
  };
  const setAccountState = (state: AccountState) => {
    accountState = state;
    tree.setAccountState(state);
    void vscode.commands.executeCommand("setContext", "docferry.accountState", state);
    if (state !== "signedIn") {
      setFolderShareEnabled(false);
    }
    updateStatus();
  };
  const setFolderShareEnabled = (enabled: boolean) => {
    tree.setFolderShareEnabled(enabled);
    void vscode.commands.executeCommand("setContext", "docferry.folderShareEnabled", enabled);
  };
  setFolderShareEnabled(false);
  updateStatus();
  status.show();

  context.subscriptions.push(
    output,
    status,
    tree,
    detailedNotes,
    detailedNotes.onDidChangeState(updateStatus),
    vscode.window.registerTreeDataProvider("docferry.workspace", tree),
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      tree.refresh();
      void detailedNotes.resume();
    }),
    vscode.commands.registerCommand(
      "docferry.refresh",
      () => refreshAccountState(cli, setAccountState, setFolderShareEnabled)
    ),
    vscode.commands.registerCommand(
      "docferry.openDashboard",
      (section: DashboardSection = "home") => openDashboard(cli, section)
    ),
    vscode.commands.registerCommand("docferry.openUrl", (url: string) => openExternal(url)),
    vscode.commands.registerCommand(
      "docferry.signIn",
      () => signIn(cli, tree, setAccountState, setFolderShareEnabled, detailedNotes)
    ),
    vscode.commands.registerCommand(
      "docferry.signOut",
      () => signOut(cli, tree, detailedNotes, setAccountState)
    ),
    vscode.commands.registerCommand(
      "docferry.showMembership",
      () => showMembership(cli, setFolderShareEnabled)
    ),
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
  void refreshAccountState(cli, setAccountState, setFolderShareEnabled);
}

export function deactivate(): void {}

async function signIn(
  cli: DocFerryCli,
  tree: DocFerryTreeProvider,
  setAccountState: (state: AccountState) => void,
  setFolderShareEnabled: (enabled: boolean) => void,
  detailedNotes?: DetailedNoteManager
): Promise<void> {
  if (detailedNotes && !(await detailedNotes.guardAccountChange())) {
    return;
  }
  const workspacePath = currentAccountContextPath();
  const started = await runWithProgress(
    "Preparing secure sign-in",
    (token) => cli.runJson<DeviceLoginStartResult>(workspacePath, VS_CODE_LOGIN_START_ARGS, {
      label: "Start sign in",
      token,
      timeoutSeconds: 90
    })
  );
  const loginUrl = started?.verification_uri_complete;
  if (!started || !isTrustedDeviceLoginUrl(loginUrl)) {
    if (started) {
      void vscode.window.showErrorMessage("DocFerry returned an invalid sign-in link.");
    }
    return;
  }
  let browserOpened = await openExternal(loginUrl, false);
  if (!browserOpened) {
    const action = await vscode.window.showWarningMessage(
      "Open your system browser to connect DocFerry.",
      "Open sign-in page",
      "Copy link",
      "Cancel"
    );
    if (action === "Open sign-in page") {
      browserOpened = await openExternal(loginUrl, false);
    } else if (action === "Copy link") {
      await vscode.env.clipboard.writeText(loginUrl);
      void vscode.window.showInformationMessage("DocFerry sign-in link copied. Open it in your browser, then return to VS Code.");
      browserOpened = true;
    } else {
      return;
    }
    if (!browserOpened) {
      await vscode.env.clipboard.writeText(loginUrl);
      void vscode.window.showWarningMessage("Your system browser did not open. The DocFerry sign-in link was copied instead.");
    }
  }
  const result = await runWithProgress(
    "Waiting for browser approval",
    (token) => cli.run(workspacePath, VS_CODE_LOGIN_COMPLETE_ARGS, {
      label: "Complete sign in",
      token
    })
  );
  if (!result) {
    return;
  }
  await refreshAccountState(cli, setAccountState, setFolderShareEnabled);
  tree.refresh();
  const action = await vscode.window.showInformationMessage(
    "DocFerry is connected to your Bondie account.",
    "Open dashboard"
  );
  if (action === "Open dashboard") {
    await openDashboard(cli, "home");
  }
}

async function openDashboard(cli: DocFerryCli, section: DashboardSection): Promise<void> {
  const workspacePath = currentAccountContextPath();
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
  detailedNotes: DetailedNoteManager,
  setAccountState: (state: AccountState) => void
): Promise<void> {
  if (!(await detailedNotes.guardAccountChange())) {
    return;
  }
  const workspacePath = currentAccountContextPath();
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
  setAccountState("signedOut");
  tree.refresh();
  void vscode.window.showInformationMessage("Signed out of DocFerry.");
}

async function showMembership(
  cli: DocFerryCli,
  setFolderShareEnabled: (enabled: boolean) => void
): Promise<void> {
  const workspacePath = currentAccountContextPath();
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
  setFolderShareEnabled(canCreateFolderShare(membership));
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
    {
      modal: true,
      detail: "Supported local images, audio, video, and attachments referenced by this note will be included. Hidden, unsupported, and outside-workspace files stay private."
    },
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
      notifyAssetWarnings: true,
      timeoutSeconds: 120
    })
  );
  if (result) {
    tree.refreshAfterMutation();
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
      openLabel: "Choose folder"
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
  const confirmation = folderShareConfirmation(workspace.name, relative);
  const approved = await vscode.window.showWarningMessage(
    confirmation.message,
    { modal: true, detail: confirmation.detail },
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
      notifyAssetWarnings: true,
      timeoutSeconds: 300
    })
  );
  if (result) {
    tree.refreshAfterMutation();
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
        await vscode.commands.executeCommand("docferry.signIn");
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
    tree.refreshAfterMutation();
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
    tree.refreshAfterMutation();
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
      notifyAssetWarnings: true,
      timeoutSeconds: 120
    })
  );
  if (result) {
    tree.refreshAfterMutation();
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
      notifyAssetWarnings: true,
      timeoutSeconds: 300
    })
  );
  if (result) {
    tree.refreshAfterMutation();
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
    tree.refreshAfterMutation();
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

function currentAccountContextPath(): string {
  return accountContextPath(
    vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath),
    os.homedir()
  );
}

async function refreshAccountState(
  cli: DocFerryCli,
  setAccountState: (state: AccountState) => void,
  setFolderShareEnabled: (enabled: boolean) => void
): Promise<void> {
  setAccountState("checking");
  try {
    const status = await cli.runJson<AuthStatusSummary>(currentAccountContextPath(), ["auth", "status"], {
      label: "Check account",
      timeoutSeconds: 30
    });
    if (!status.authenticated) {
      setAccountState("signedOut");
      return;
    }
    setAccountState("signedIn");
    try {
      const membership = await cli.runJson<MembershipSummary>(
        currentAccountContextPath(),
        ["membership"],
        { label: "Refresh feature access", timeoutSeconds: 60 }
      );
      setFolderShareEnabled(canCreateFolderShare(membership));
    } catch {
      setFolderShareEnabled(false);
    }
  } catch (error) {
    setAccountState(isAuthenticationError(error) ? "signedOut" : "error");
  }
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

async function openExternal(value: string, showError = true): Promise<boolean> {
  try {
    const uri = vscode.Uri.parse(value, true);
    if (uri.scheme !== "https" || !uri.authority) {
      throw new Error("DocFerry only opens secure web links.");
    }
    return await vscode.env.openExternal(uri);
  } catch (error) {
    if (showError) {
      void vscode.window.showErrorMessage(errorMessage(error));
    }
    return false;
  }
}
