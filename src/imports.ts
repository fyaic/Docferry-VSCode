import * as vscode from "vscode";
import { randomUUID } from "node:crypto";

import { DocFerryCli } from "./cli";
import {
  canonicalPath,
  mediaNoteFailureMessage,
  mediaNotePreview,
  mediaNoteStatusKind,
  MediaNoteJobResult,
  resolveWorkspaceOutput,
  SaveResult
} from "./contracts";


const PENDING_IMPORT_KEY = "docferry.pendingDetailedNote.v1";
const POLL_INTERVAL_MS = 5_000;
const BACKGROUND_POLL_LIMIT = 240;

interface PendingDetailedNote {
  jobId: string;
  workspacePath: string;
  outputFolder: string;
  createdAt: string;
}


export class DetailedNoteManager implements vscode.Disposable {
  private disposed = false;
  private monitoring = false;

  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly cli: DocFerryCli
  ) {}

  dispose(): void {
    this.disposed = true;
  }

  hasPending(): boolean {
    return this.pending() !== undefined;
  }

  async guardAccountChange(): Promise<boolean> {
    if (!this.hasPending()) {
      return true;
    }
    const action = await vscode.window.showWarningMessage(
      "Finish or cancel the detailed note before changing the connected account.",
      "Check status",
      "Cancel import"
    );
    if (action === "Check status") {
      await this.check();
    } else if (action === "Cancel import") {
      await this.cancel();
      return !this.hasPending();
    }
    return false;
  }

  async start(workspacePath: string, url: string, outputFolder: string): Promise<boolean> {
    if (this.pending()) {
      const action = await vscode.window.showInformationMessage(
        "A detailed note is already being prepared.",
        "Check status",
        "Cancel"
      );
      if (action === "Check status") {
        await this.check();
      } else if (action === "Cancel") {
        await this.cancel();
      }
      return false;
    }
    const idempotencyKey = `vscode-${randomUUID()}`;
    const created = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: "Starting your detailed note",
        cancellable: true
      },
      async (_progress, token) => this.cli.runJson<MediaNoteJobResult>(
        workspacePath,
        ["media-note", "create", url, "--idempotency-key", idempotencyKey],
        { label: "Create detailed note", token, timeoutSeconds: 60 }
      )
    );
    if (!created.job_id) {
      throw new Error("DocFerry did not return a detailed-note job.");
    }
    await this.context.globalState.update(PENDING_IMPORT_KEY, {
      jobId: created.job_id,
      workspacePath,
      outputFolder,
      createdAt: new Date().toISOString()
    } satisfies PendingDetailedNote);
    const action = await vscode.window.showInformationMessage(
      "DocFerry is preparing your detailed note in the background.",
      "Check status"
    );
    if (action === "Check status") {
      await this.check();
    } else {
      void this.monitor();
    }
    return true;
  }

  async resume(): Promise<void> {
    if (!this.pending() || !this.workspaceIsOpen(this.pending()!.workspacePath)) {
      return;
    }
    void this.monitor();
  }

  async check(): Promise<void> {
    const pending = this.pending();
    if (!pending) {
      void vscode.window.showInformationMessage("No detailed note is being prepared.");
      return;
    }
    if (!this.workspaceIsOpen(pending.workspacePath)) {
      void vscode.window.showInformationMessage("Reopen the original workspace to finish this detailed note.");
      return;
    }
    const job = await this.readStatus(pending);
    await this.handleStatus(pending, job, true);
  }

  async cancel(): Promise<void> {
    const pending = this.pending();
    if (!pending) {
      void vscode.window.showInformationMessage("No detailed note is being prepared.");
      return;
    }
    if (!this.workspaceIsOpen(pending.workspacePath)) {
      void vscode.window.showInformationMessage("Reopen the original workspace before cancelling this detailed note.");
      return;
    }
    const approved = await vscode.window.showWarningMessage(
      "Cancel the detailed note currently being prepared?",
      { modal: true, detail: "No note will be written to your workspace." },
      "Cancel import"
    );
    if (approved !== "Cancel import") {
      return;
    }
    await this.cli.runJson<MediaNoteJobResult>(
      pending.workspacePath,
      ["media-note", "cancel", pending.jobId, "--confirm"],
      { label: "Cancel detailed note", timeoutSeconds: 60 }
    );
    await this.clear(pending.jobId);
    void vscode.window.showInformationMessage("Detailed note cancelled.");
  }

  private pending(): PendingDetailedNote | undefined {
    const value = this.context.globalState.get<PendingDetailedNote>(PENDING_IMPORT_KEY);
    return value?.jobId && value.workspacePath && value.outputFolder ? value : undefined;
  }

  private workspaceIsOpen(workspacePath: string): boolean {
    const expected = canonicalPath(workspacePath);
    return vscode.workspace.workspaceFolders?.some(
      (folder) => canonicalPath(folder.uri.fsPath) === expected
    ) === true;
  }

  private async monitor(): Promise<void> {
    if (this.monitoring || this.disposed) {
      return;
    }
    this.monitoring = true;
    try {
      for (let attempt = 0; attempt < BACKGROUND_POLL_LIMIT && !this.disposed; attempt += 1) {
        const pending = this.pending();
        if (!pending || !this.workspaceIsOpen(pending.workspacePath)) {
          return;
        }
        if (attempt > 0) {
          await delay(POLL_INTERVAL_MS);
        }
        try {
          const job = await this.readStatus(pending);
          if (await this.handleStatus(pending, job, false)) {
            return;
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          void vscode.window.showWarningMessage(
            `DocFerry paused background checks: ${message.slice(0, 240)}`,
            "Try again"
          ).then((action) => action === "Try again" && void this.check());
          return;
        }
      }
      void vscode.window.showInformationMessage(
        "Your detailed note is still processing. DocFerry will check again when you reopen this workspace.",
        "Check now"
      ).then((action) => action === "Check now" && void this.check());
    } finally {
      this.monitoring = false;
    }
  }

  private async readStatus(pending: PendingDetailedNote): Promise<MediaNoteJobResult> {
    return await this.cli.runJson<MediaNoteJobResult>(
      pending.workspacePath,
      ["media-note", "status", pending.jobId],
      { label: "Check detailed note", timeoutSeconds: 60 }
    );
  }

  private async handleStatus(
    pending: PendingDetailedNote,
    job: MediaNoteJobResult,
    announceProgress: boolean
  ): Promise<boolean> {
    const kind = mediaNoteStatusKind(job.status);
    if (kind === "processing") {
      if (announceProgress) {
        void vscode.window.showInformationMessage(
          job.status === "fetching"
            ? "DocFerry is reading the source. Longer audio and video can take a few minutes."
            : "Your detailed note is queued and will continue in the background."
        );
      }
      return false;
    }
    if (kind === "failed") {
      await this.clear(pending.jobId);
      void vscode.window.showErrorMessage(mediaNoteFailureMessage(job));
      return true;
    }

    const preview = mediaNotePreview(job);
    const action = await vscode.window.showInformationMessage(
      `Detailed note ready: ${preview.title}`,
      "Review"
    );
    if (action !== "Review") {
      return true;
    }
    if (job.markdown?.trim()) {
      const document = await vscode.workspace.openTextDocument({
        language: "markdown",
        content: job.markdown
      });
      await vscode.window.showTextDocument(document, { preview: true });
    }
    const saveAction = await vscode.window.showInformationMessage(
      `Save “${preview.title}” to this workspace?`,
      {
        modal: true,
        detail: preview.summary || "The reviewed Markdown will be saved in your DocFerry import folder."
      },
      "Save to workspace",
      "Later"
    );
    if (saveAction !== "Save to workspace") {
      return true;
    }
    const saved = await this.cli.runJson<SaveResult>(
      pending.workspacePath,
      ["media-note", "save", pending.jobId, "--output", pending.outputFolder, "--confirm"],
      { label: "Save detailed note", timeoutSeconds: 60 }
    );
    await this.clear(pending.jobId);
    if (saved.output) {
      const output = resolveWorkspaceOutput(pending.workspacePath, saved.output);
      const document = await vscode.workspace.openTextDocument(vscode.Uri.file(output));
      await vscode.window.showTextDocument(document, { preview: false });
    }
    void vscode.window.showInformationMessage(`Saved ${saved.title || preview.title}.`);
    return true;
  }

  private async clear(jobId: string): Promise<void> {
    if (this.pending()?.jobId === jobId) {
      await this.context.globalState.update(PENDING_IMPORT_KEY, undefined);
    }
  }
}


async function delay(milliseconds: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
}
