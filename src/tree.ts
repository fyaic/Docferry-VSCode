import * as vscode from "vscode";

import { DocFerryCli } from "./cli";
import type { DetailedNoteManager } from "./imports";
import {
  FolderShareListSummary,
  FolderShareSummary,
  isShareActionable,
  isShareHistoryDeletable,
  shareTreeFailureMessage,
  ShareListSummary,
  ShareSummary,
  workspaceRootForPath
} from "./contracts";

type TreeNode = ActionNode | GroupNode | MessageNode | NoteShareNode | FolderShareNode;

interface ActionNode {
  kind: "action";
  label: string;
  description: string;
  icon: string;
  command: string;
}

interface GroupNode {
  kind: "group";
  group: "notes" | "folders";
  label: string;
  icon: string;
}

interface MessageNode {
  kind: "message";
  label: string;
  icon: string;
}

export interface NoteShareNode {
  kind: "noteShare";
  shareId: string;
  label: string;
  status: string;
  workspacePath: string;
  url?: string;
  sourcePath?: string;
}

export interface FolderShareNode {
  kind: "folderShare";
  folderShareId: string;
  label: string;
  status: string;
  workspacePath: string;
  url?: string;
  sourcePath?: string;
}

const ACTIONS: ActionNode[] = [
  {
    kind: "action",
    label: "Save a link",
    description: "Add it to this workspace",
    icon: "link",
    command: "docferry.saveLink"
  },
  {
    kind: "action",
    label: "Share current Markdown",
    description: "Create a DocFerry link",
    icon: "cloud-upload",
    command: "docferry.shareCurrentFile"
  },
  {
    kind: "action",
    label: "Share a folder",
    description: "Publish its Markdown files",
    icon: "folder-opened",
    command: "docferry.shareFolder"
  },
  {
    kind: "action",
    label: "Plan and usage",
    description: "View your current access",
    icon: "account",
    command: "docferry.showMembership"
  },
  {
    kind: "action",
    label: "Sign in or switch account",
    description: "Continue in your system browser",
    icon: "sign-in",
    command: "docferry.signIn"
  },
  {
    kind: "action",
    label: "Open dashboard",
    description: "Manage DocFerry in your browser",
    icon: "globe",
    command: "docferry.openDashboard"
  }
];

const GROUPS: GroupNode[] = [
  { kind: "group", group: "notes", label: "Shared notes", icon: "files" },
  { kind: "group", group: "folders", label: "Shared folders", icon: "folder-library" }
];

export class DocFerryTreeProvider implements vscode.TreeDataProvider<TreeNode>, vscode.Disposable {
  private readonly changeEmitter = new vscode.EventEmitter<TreeNode | undefined>();
  private readonly detailedNoteSubscription?: vscode.Disposable;
  private readonly delayedRefreshes = new Set<NodeJS.Timeout>();
  readonly onDidChangeTreeData = this.changeEmitter.event;

  constructor(
    private readonly cli: DocFerryCli,
    private readonly detailedNotes?: DetailedNoteManager
  ) {
    this.detailedNoteSubscription = detailedNotes?.onDidChangeState(() => this.refresh());
  }

  dispose(): void {
    this.detailedNoteSubscription?.dispose();
    this.changeEmitter.dispose();
    for (const timer of this.delayedRefreshes) {
      clearTimeout(timer);
    }
    this.delayedRefreshes.clear();
  }

  refresh(): void {
    this.changeEmitter.fire(undefined);
  }

  refreshAfterMutation(): void {
    this.refresh();
    for (const delay of [1_200, 3_500]) {
      const timer = setTimeout(() => {
        this.delayedRefreshes.delete(timer);
        this.refresh();
      }, delay);
      this.delayedRefreshes.add(timer);
    }
  }

  getTreeItem(node: TreeNode): vscode.TreeItem {
    if (node.kind === "action") {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
      item.description = node.description;
      item.iconPath = new vscode.ThemeIcon(node.icon);
      item.command = { command: node.command, title: node.label };
      return item;
    }
    if (node.kind === "group") {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Collapsed);
      item.iconPath = new vscode.ThemeIcon(node.icon);
      return item;
    }
    if (node.kind === "message") {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
      item.iconPath = new vscode.ThemeIcon(node.icon);
      return item;
    }

    const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
    const actionable = isShareActionable(node.status);
    item.description = node.status;
    item.tooltip = `${node.label}\n${node.status}`;
    item.iconPath = new vscode.ThemeIcon(actionable ? "link-external" : "circle-slash");
    item.contextValue = node.kind === "noteShare"
      ? `docferry.noteShare.${actionable ? "active" : isShareHistoryDeletable(node.status) ? "deletable" : "inactive"}`
      : `docferry.folderShare.${actionable ? "active" : isShareHistoryDeletable(node.status) ? "deletable" : "inactive"}`;
    if (actionable && node.url) {
      item.command = {
        command: "docferry.openUrl",
        title: "Open share",
        arguments: [node.url]
      };
    }
    return item;
  }

  async getChildren(node?: TreeNode): Promise<TreeNode[]> {
    if (!node) {
      const actions = [...ACTIONS];
      const detailedNote = this.detailedNotes?.indicator();
      if (detailedNote) {
        actions.splice(1, 0, {
          kind: "action",
          label: detailedNote.label,
          description: detailedNote.description,
          icon: detailedNote.icon,
          command: "docferry.checkDetailedNote"
        });
      }
      return [...actions, ...GROUPS];
    }
    if (node.kind !== "group") {
      return [];
    }
    const workspacePath = this.workspaceContextPath();
    if (!workspacePath) {
      return [{ kind: "message", label: "Open a folder to use DocFerry", icon: "folder-opened" }];
    }
    try {
      return node.group === "notes"
        ? await this.noteShares(workspacePath)
        : await this.folderShares(workspacePath);
    } catch (error) {
      return [{ kind: "message", label: shareTreeFailureMessage(error), icon: "warning" }];
    }
  }

  private async noteShares(workspacePath: string): Promise<TreeNode[]> {
    const result = await this.cli.runJson<ShareListSummary>(workspacePath, ["list", "--limit", "30"], {
      label: "Refresh shared notes",
      timeoutSeconds: 60
    });
    const shares = Array.isArray(result.shares) ? result.shares : [];
    return shares.length > 0
      ? shares.map((share) => toNoteShareNode(share, workspacePath))
      : [{ kind: "message", label: "No shared notes yet", icon: "info" }];
  }

  private async folderShares(workspacePath: string): Promise<TreeNode[]> {
    const result = await this.cli.runJson<FolderShareListSummary>(workspacePath, ["folder", "list"], {
      label: "Refresh shared folders",
      timeoutSeconds: 60
    });
    const shares = Array.isArray(result.folder_shares) ? result.folder_shares : [];
    return shares.length > 0
      ? shares.map((share) => toFolderShareNode(share, workspacePath))
      : [{ kind: "message", label: "No shared folders yet", icon: "info" }];
  }

  private workspaceContextPath(): string | undefined {
    const workspaceRoots = vscode.workspace.workspaceFolders?.map((folder) => folder.uri.fsPath);
    if (!workspaceRoots?.length) {
      return undefined;
    }
    const activeResource = vscode.window.activeTextEditor?.document.uri;
    return activeResource?.scheme === "file"
      ? workspaceRootForPath(workspaceRoots, activeResource.fsPath) ?? workspaceRoots[0]
      : workspaceRoots[0];
  }
}

function toNoteShareNode(share: ShareSummary, workspacePath: string): NoteShareNode {
  return {
    kind: "noteShare",
    shareId: share.share_id,
    label: share.title?.trim() || "Untitled note",
    status: share.status || "published",
    workspacePath,
    url: share.url,
    sourcePath: share.source_path
  };
}

function toFolderShareNode(share: FolderShareSummary, workspacePath: string): FolderShareNode {
  return {
    kind: "folderShare",
    folderShareId: share.folder_share_id,
    label: share.title?.trim() || "Untitled folder",
    status: share.status || "published",
    workspacePath,
    url: share.url,
    sourcePath: share.source_folder
  };
}
