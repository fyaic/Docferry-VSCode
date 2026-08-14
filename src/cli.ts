import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import * as vscode from "vscode";

import {
  buildCliArgs,
  defaultCliCandidates,
  isSupportedAgentKitVersion,
  MIN_AGENT_KIT_VERSION,
  parseJsonOutput,
  redactOutput
} from "./contracts";

const MAX_OUTPUT_BYTES = 2 * 1024 * 1024;

export class DocFerryCliError extends Error {
  constructor(
    message: string,
    readonly kind: "missing" | "incompatible" | "cancelled" | "timeout" | "failed" = "failed"
  ) {
    super(message);
  }
}

export interface CliRunOptions {
  label: string;
  token?: vscode.CancellationToken;
  timeoutSeconds?: number;
  onStdout?: (chunk: string) => void;
}

export interface CliRunResult {
  stdout: string;
  stderr: string;
}

export class DocFerryCli {
  private readonly versionChecks = new Map<string, Promise<void>>();

  constructor(
    private readonly output: vscode.OutputChannel,
    private readonly extensionPath: string
  ) {}

  async run(
    workspacePath: string,
    commandArgs: readonly string[],
    options: CliRunOptions
  ): Promise<CliRunResult> {
    const executable = this.resolveExecutable();
    await this.ensureSupportedVersion(executable, workspacePath);
    return await this.runProcess(executable, workspacePath, commandArgs, options);
  }

  private async ensureSupportedVersion(executable: string, workspacePath: string): Promise<void> {
    if (executable === this.bundledExecutable()) {
      return;
    }
    const existing = this.versionChecks.get(executable);
    if (existing) {
      return await existing;
    }
    const check = this.runProcess(executable, workspacePath, ["--version"], {
      label: "Check Agent Kit version",
      timeoutSeconds: 30
    }).then((result) => {
      if (!isSupportedAgentKitVersion(result.stdout)) {
        throw new DocFerryCliError(
          `DocFerry Agent Kit ${MIN_AGENT_KIT_VERSION} or newer is required.`,
          "incompatible"
        );
      }
    }).catch((error: unknown) => {
      this.versionChecks.delete(executable);
      throw error;
    });
    this.versionChecks.set(executable, check);
    return await check;
  }

  private async runProcess(
    executable: string,
    workspacePath: string,
    commandArgs: readonly string[],
    options: CliRunOptions
  ): Promise<CliRunResult> {
    const args = buildCliArgs(workspacePath, commandArgs);
    const configuredTimeout = vscode.workspace
      .getConfiguration("docferry")
      .get<number>("commandTimeoutSeconds", 900);
    const timeoutSeconds = Math.max(30, Math.min(options.timeoutSeconds ?? configuredTimeout, 1800));

    this.output.appendLine(`[${new Date().toISOString()}] ${options.label}`);

    return await new Promise<CliRunResult>((resolve, reject) => {
      let stdout = "";
      let stderr = "";
      let settled = false;
      let timeout: NodeJS.Timeout | undefined;
      let cancellation: vscode.Disposable | undefined;
      const child = spawn(executable, args, {
        cwd: workspacePath,
        env: { ...process.env, PYTHONUNBUFFERED: "1" },
        shell: false,
        windowsHide: true
      });

      const finish = (error?: Error, result?: CliRunResult) => {
        if (settled) {
          return;
        }
        settled = true;
        if (timeout) {
          clearTimeout(timeout);
        }
        cancellation?.dispose();
        if (error) {
          reject(error);
        } else {
          resolve(result ?? { stdout, stderr });
        }
      };

      const append = (target: "stdout" | "stderr", chunk: Buffer) => {
        const text = chunk.toString("utf8");
        if (target === "stdout") {
          stdout += text;
          options.onStdout?.(text);
        } else {
          stderr += text;
        }
        if (Buffer.byteLength(stdout) + Buffer.byteLength(stderr) > MAX_OUTPUT_BYTES) {
          child.kill();
          finish(new DocFerryCliError("DocFerry returned too much output and was stopped."));
        }
      };

      child.stdout.on("data", (chunk: Buffer) => append("stdout", chunk));
      child.stderr.on("data", (chunk: Buffer) => append("stderr", chunk));
      child.on("error", (error: NodeJS.ErrnoException) => {
        const kind = error.code === "ENOENT" ? "missing" : "failed";
        const message = kind === "missing"
          ? "DocFerry CLI is not installed or its path is not configured."
          : `DocFerry could not start: ${error.message}`;
        finish(new DocFerryCliError(message, kind));
      });
      child.on("close", (code, signal) => {
        if (settled) {
          return;
        }
        if (code === 0) {
          this.output.appendLine("Completed.");
          finish(undefined, { stdout, stderr });
          return;
        }
        const detail = redactOutput(stderr.trim() || stdout.trim()).slice(0, 800);
        this.output.appendLine(`Failed: ${detail || `exit code ${code}`}`);
        finish(new DocFerryCliError(detail || `DocFerry stopped with ${signal ?? `exit code ${code}`}.`));
      });

      cancellation = options.token?.onCancellationRequested(() => {
        child.kill();
        finish(new DocFerryCliError("DocFerry operation was cancelled.", "cancelled"));
      }) ?? { dispose: () => undefined };
      timeout = setTimeout(() => {
        child.kill();
        finish(new DocFerryCliError("DocFerry took too long and was stopped. You can check the result later.", "timeout"));
      }, timeoutSeconds * 1000);
    });
  }

  async runJson<T>(
    workspacePath: string,
    commandArgs: readonly string[],
    options: CliRunOptions
  ): Promise<T> {
    const result = await this.run(workspacePath, commandArgs, options);
    return parseJsonOutput<T>(result.stdout);
  }

  private resolveExecutable(): string {
    const configured = vscode.workspace.getConfiguration("docferry").get<string>("cliPath", "").trim();
    if (configured) {
      return configured;
    }
    const executable = process.platform === "win32" ? "docferry.exe" : "docferry";
    const bundled = this.bundledExecutable();
    if (fs.existsSync(bundled)) {
      return bundled;
    }
    return defaultCliCandidates(os.homedir(), process.platform).find((candidate) => fs.existsSync(candidate))
      ?? executable;
  }

  private bundledExecutable(): string {
    const executable = process.platform === "win32" ? "docferry.exe" : "docferry";
    return path.join(this.extensionPath, "bin", "helper", executable);
  }
}
