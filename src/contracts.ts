import fs from "node:fs";
import path from "node:path";

export const MIN_AGENT_KIT_VERSION = "0.4.4";
export const VS_CODE_LOGIN_START_ARGS = [
  "login",
  "--device-code-start",
  "--client",
  "vscode",
  "--no-browser"
] as const;
export const VS_CODE_LOGIN_COMPLETE_ARGS = [
  "login",
  "--device-code-complete",
  "--client",
  "vscode",
  "--no-browser"
] as const;

export interface DeviceLoginStartResult {
  verification_uri_complete?: string;
  user_code?: string;
  expires_at?: string;
  interval?: number;
}

export interface DetailedNoteIndicatorCopy {
  label: string;
  description: string;
  icon: string;
  ready: boolean;
}

export function detailedNoteIndicatorCopy(
  status: string | undefined,
  title?: string
): DetailedNoteIndicatorCopy {
  if (mediaNoteStatusKind(status || "queued") === "ready") {
    return {
      label: title ? `Detailed note ready: ${title}` : "Detailed note ready",
      description: "Review and save it",
      icon: "check",
      ready: true
    };
  }
  return {
    label: "Preparing detailed note",
    description: status === "fetching" ? "Reading the source" : "Running in the background",
    icon: "loading~spin",
    ready: false
  };
}

export function folderShareConfirmation(
  workspaceName: string,
  relativePath: string
): { message: string; detail: string } {
  if (relativePath === ".") {
    return {
      message: `Share the entire “${workspaceName}” workspace?`,
      detail: "This publishes every visible Markdown file in the workspace and its subfolders. Hidden and non-Markdown files stay private."
    };
  }
  return {
    message: `Share Markdown files in “${path.basename(relativePath)}”?`,
    detail: `Selected folder: ${relativePath}. Visible Markdown files in this folder and its subfolders will be published.`
  };
}

export type DashboardSection = "home" | "membership" | "plans" | "shares" | "support" | "account";

export interface DashboardLinkResult {
  opened?: boolean;
  section?: DashboardSection;
  target_path?: string;
  dashboard_url?: string;
}

export interface MembershipSummary {
  access_role?: string;
  plan_key?: string;
  plan_display_name?: string;
  active_share_count?: number;
  active_share_limit?: number | null;
  share_limit_unlimited?: boolean;
  active_folder_share_count?: number;
  active_folder_share_limit?: number | null;
  folder_share_limit_unlimited?: boolean;
  feature_gates?: Record<string, boolean>;
  media_note?: {
    enabled?: boolean;
    supported_providers?: string[];
    supported_source_kinds?: string[];
  };
  media_note_usage?: {
    active_jobs?: number;
    active_job_limit?: number | null;
    monthly_jobs_used?: number;
    monthly_job_limit?: number | null;
    resets_at?: string;
  };
}

export interface ShareSummary {
  share_id: string;
  title?: string;
  status?: string;
  url?: string;
  source_path?: string;
}

export interface ShareListSummary {
  shares?: ShareSummary[];
  total?: number;
}

export interface FolderShareSummary {
  folder_share_id: string;
  title?: string;
  status?: string;
  url?: string;
  source_folder?: string;
}

export interface FolderShareListSummary {
  folder_shares?: FolderShareSummary[];
  total?: number;
}

export interface SaveResult {
  output?: string;
  title?: string;
  url?: string;
  share_id?: string;
  folder_share_id?: string;
  status?: string;
}

export interface MediaNoteJobResult {
  job_id?: string;
  source_url?: string | null;
  status?: string;
  warnings?: string[];
  error_message?: string | null;
  result_contract?: Record<string, unknown> | null;
  markdown?: string | null;
}

export type MediaNoteStatusKind = "processing" | "ready" | "failed";

export function mediaNoteStatusKind(status: string | undefined): MediaNoteStatusKind {
  if (["extracted", "degraded"].includes(status || "")) {
    return "ready";
  }
  if (["unsupported", "failed", "cancelled", "expired"].includes(status || "")) {
    return "failed";
  }
  return "processing";
}

export function mediaNotePreview(job: MediaNoteJobResult): { title: string; summary: string } {
  const titleValue = job.result_contract?.title;
  const summaryValue = job.result_contract?.summary;
  const nestedSummary = typeof summaryValue === "object" && summaryValue !== null && "text" in summaryValue
    ? (summaryValue as { text?: unknown }).text
    : summaryValue;
  let fallback = "Imported note";
  if (job.source_url) {
    try {
      fallback = new URL(job.source_url).hostname.replace(/^www\./, "") || fallback;
    } catch {
      // Server validation owns the source URL; retained job shells may omit it.
    }
  }
  return {
    title: typeof titleValue === "string" && titleValue.trim()
      ? titleValue.replace(/\s+/g, " ").trim().slice(0, 160)
      : fallback,
    summary: typeof nestedSummary === "string"
      ? nestedSummary.replace(/\s+/g, " ").trim().slice(0, 320)
      : ""
  };
}

export function mediaNoteFailureMessage(job: MediaNoteJobResult): string {
  if (job.status === "cancelled") {
    return "This detailed note was cancelled. Nothing was saved.";
  }
  if (job.status === "expired") {
    return "This detailed note expired before it was saved.";
  }
  if (job.status === "unsupported") {
    return "DocFerry cannot prepare a detailed note from this source yet.";
  }
  return job.error_message || "DocFerry could not prepare this detailed note.";
}

export function defaultCliCandidates(homeDirectory: string, platform: NodeJS.Platform): string[] {
  const pathApi = platform === "win32" ? path.win32 : path.posix;
  if (platform === "win32") {
    return [
      pathApi.join(homeDirectory, ".local", "bin", "docferry.exe"),
      pathApi.join(
        homeDirectory,
        ".local",
        "share",
        "docferry-agent-kit",
        "venv",
        "Scripts",
        "docferry.exe"
      )
    ];
  }
  return [
    pathApi.join(homeDirectory, ".local", "bin", "docferry"),
    pathApi.join(homeDirectory, ".local", "share", "docferry-agent-kit", "venv", "bin", "docferry")
  ];
}

export function buildCliArgs(workspacePath: string, commandArgs: readonly string[]): string[] {
  if (!path.isAbsolute(workspacePath)) {
    throw new Error("DocFerry workspace path must be absolute.");
  }
  return ["--workspace", workspacePath, ...commandArgs];
}

export function dashboardCommandArgs(section: DashboardSection): string[] {
  return ["dashboard", "--section", section, "--no-browser"];
}

export function isTrustedDashboardHandoffUrl(value: string | undefined): value is string {
  if (!value) {
    return false;
  }
  try {
    const url = new URL(value);
    const keys = [...url.searchParams.keys()];
    return url.protocol === "https:"
      && url.hostname === "docferry.bondie.io"
      && url.port === ""
      && url.username === ""
      && url.password === ""
      && url.pathname === "/v0/auth/dashboard-open"
      && url.hash === ""
      && keys.length === 1
      && keys[0] === "code"
      && Boolean(url.searchParams.get("code"));
  } catch {
    return false;
  }
}

export function isTrustedDeviceLoginUrl(value: string | undefined): value is string {
  if (!value) {
    return false;
  }
  try {
    const url = new URL(value);
    const keys = [...url.searchParams.keys()];
    return url.protocol === "https:"
      && url.hostname === "docferry.bondie.io"
      && url.port === ""
      && url.username === ""
      && url.password === ""
      && url.pathname === "/activate"
      && url.hash === ""
      && keys.length === 1
      && keys[0] === "user_code"
      && /^[A-Z0-9-]{4,32}$/i.test(url.searchParams.get("user_code") || "");
  } catch {
    return false;
  }
}

export function parseJsonOutput<T>(stdout: string): T {
  const value = stdout.trim();
  if (!value) {
    throw new Error("DocFerry returned no result.");
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    throw new Error("DocFerry returned an unreadable result.");
  }
}

export function redactOutput(value: string): string {
  return value
    .replace(/Bearer\s+[^\s"']+/gi, "Bearer [redacted]")
    .replace(/sk-or-v1-[A-Za-z0-9_-]+/g, "sk-or-v1-[redacted]")
    .replace(/("(?:access_token|session_token|refresh_token)"\s*:\s*")[^"]+("?)/gi, "$1[redacted]$2");
}

export function canonicalPath(value: string): string {
  const resolved = path.resolve(value);
  let current = resolved;
  const missingParts: string[] = [];

  while (true) {
    try {
      const realPath = fs.realpathSync.native(current);
      return path.join(realPath, ...missingParts);
    } catch (error) {
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== "ENOENT" && code !== "ENOTDIR") {
        throw error;
      }
      const parent = path.dirname(current);
      if (parent === current) {
        throw error;
      }
      missingParts.unshift(path.basename(current));
      current = parent;
    }
  }
}

export function isPathInside(parent: string, candidate: string): boolean {
  const relative = path.relative(canonicalPath(parent), canonicalPath(candidate));
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
}

export function workspaceRootForPath(
  workspaceRoots: readonly string[],
  candidate: string
): string | undefined {
  const canonicalCandidate = canonicalPath(candidate);
  let bestMatch: { root: string; canonicalLength: number } | undefined;

  for (const root of workspaceRoots) {
    const canonicalRoot = canonicalPath(root);
    const relative = path.relative(canonicalRoot, canonicalCandidate);
    const containsCandidate = relative === ""
      || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative));
    if (containsCandidate && canonicalRoot.length > (bestMatch?.canonicalLength ?? -1)) {
      bestMatch = { root, canonicalLength: canonicalRoot.length };
    }
  }
  return bestMatch?.root;
}

export function workspaceRelativePath(workspacePath: string, candidate: string): string {
  if (!isPathInside(workspacePath, candidate)) {
    throw new Error("Choose a file or folder inside the current VS Code workspace.");
  }
  const relative = path.relative(canonicalPath(workspacePath), canonicalPath(candidate));
  return relative || ".";
}

export function resolveWorkspaceOutput(workspacePath: string, output: string): string {
  const value = output.trim();
  if (!value) {
    throw new Error("DocFerry returned no saved file path.");
  }
  const candidate = path.isAbsolute(value) ? path.resolve(value) : path.resolve(workspacePath, value);
  if (!isPathInside(workspacePath, candidate)) {
    throw new Error("DocFerry returned a file outside the current workspace.");
  }
  return candidate;
}

export function validateImportFolder(value: string): string {
  const candidate = value.trim().replaceAll("\\", "/").replace(/^\.\//, "");
  if (!candidate || candidate.startsWith("/") || candidate.split("/").some((part) => !part || part === ".." || part.startsWith("."))) {
    throw new Error("Choose a visible folder inside the workspace.");
  }
  return candidate;
}

export function isCanonicalDocFerryShareUrl(value: string): boolean {
  try {
    const url = new URL(value);
    const parts = url.pathname.split("/").filter(Boolean);
    return url.protocol === "https:" && url.hostname === "docferry.bondie.io" && parts.length === 2 && parts[0] === "s";
  } catch {
    return false;
  }
}

export type MediaNoteProvider =
  | "youtube"
  | "tiktok"
  | "bilibili"
  | "douyin"
  | "wechat"
  | "vimeo"
  | "audio"
  | "video"
  | "web";

export type AdvancedImportReason =
  | "eligible"
  | "docferry_share"
  | "not_entitled"
  | "runtime_disabled"
  | "provider_unsupported"
  | "mandatory_provider_unavailable";

export interface AdvancedImportDecision {
  eligible: boolean;
  provider?: MediaNoteProvider;
  reason: AdvancedImportReason;
}

export function mediaNoteProviderForUrl(value: string): MediaNoteProvider {
  const url = new URL(value);
  const hostname = url.hostname.toLowerCase();
  const host = hostname.startsWith("www.") ? hostname.slice(4) : hostname;

  if (host === "youtu.be" || host === "youtube.com" || host.endsWith(".youtube.com")) {
    return "youtube";
  }
  if (host === "tiktok.com" || host.endsWith(".tiktok.com")) {
    return "tiktok";
  }
  if (host === "bilibili.com" || host === "b23.tv" || host.endsWith(".bilibili.com")) {
    return "bilibili";
  }
  if (host === "douyin.com" || host === "v.douyin.com" || host.endsWith(".douyin.com")) {
    return "douyin";
  }
  if (host === "mp.weixin.qq.com") {
    return "wechat";
  }
  if (host === "vimeo.com" || host.endsWith(".vimeo.com")) {
    return "vimeo";
  }
  if (/\.(mp3|m4a|wav|ogg)$/i.test(url.pathname)) {
    return "audio";
  }
  if (/\.(mp4|webm|mov)$/i.test(url.pathname)) {
    return "video";
  }
  return "web";
}

export function advancedImportDecision(
  url: string,
  membership: MembershipSummary
): AdvancedImportDecision {
  if (isCanonicalDocFerryShareUrl(url)) {
    return { eligible: false, reason: "docferry_share" };
  }
  const provider = mediaNoteProviderForUrl(url);
  if (membership.feature_gates?.["docferry.ai.assist"] !== true) {
    return { eligible: false, provider, reason: "not_entitled" };
  }
  if (membership.media_note?.enabled !== true) {
    return { eligible: false, provider, reason: "runtime_disabled" };
  }
  if (!membership.media_note.supported_providers?.includes(provider)) {
    if (["bilibili", "tiktok", "douyin"].includes(provider)) {
      return { eligible: false, provider, reason: "mandatory_provider_unavailable" };
    }
    return { eligible: false, provider, reason: "provider_unsupported" };
  }
  return { eligible: true, provider, reason: "eligible" };
}

export function shouldUseAdvancedImport(url: string, membership: MembershipSummary): boolean {
  return advancedImportDecision(url, membership).eligible;
}

const INACTIVE_SHARE_STATUSES = new Set(["stopped", "revoked", "expired", "deleted"]);

export function isShareActionable(status: string | undefined): boolean {
  return !INACTIVE_SHARE_STATUSES.has((status || "published").trim().toLowerCase());
}

export function isShareHistoryDeletable(status: string | undefined): boolean {
  return ["stopped", "revoked"].includes((status || "").trim().toLowerCase());
}

export type OperationErrorKind =
  | "cancelled"
  | "missing"
  | "incompatible"
  | "authentication"
  | "entitlement"
  | "timeout"
  | "network"
  | "service"
  | "other";

export function operationErrorMessage(error: unknown): string {
  const value = error instanceof Error ? error.message : String(error);
  return value.replace(/^docferry:\s*/i, "").trim().slice(0, 500)
    || "DocFerry could not complete this action.";
}

export function classifyOperationError(error: unknown): OperationErrorKind {
  const structuralKind = typeof error === "object" && error !== null && "kind" in error
    ? String((error as { kind?: unknown }).kind || "")
    : "";
  if (["cancelled", "missing", "incompatible", "timeout"].includes(structuralKind)) {
    return structuralKind as OperationErrorKind;
  }

  const message = operationErrorMessage(error);
  if (/No DocFerry session|sign in|session.*expired|\b401\b/i.test(message)) {
    return "authentication";
  }
  if (/requires DocFerry Pro|paid access|Folder sharing requires/i.test(message)) {
    return "entitlement";
  }
  if (/timed?\s*out|timeout/i.test(message)) {
    return "timeout";
  }
  if (/ECONN|ENOTFOUND|EAI_AGAIN|network|could not connect|connection refused|fetch failed/i.test(message)) {
    return "network";
  }
  if (/\b5\d\d\b|bad gateway|service unavailable|server error|temporarily unavailable/i.test(message)) {
    return "service";
  }
  return "other";
}

export function shareTreeFailureMessage(error: unknown): string {
  switch (classifyOperationError(error)) {
    case "authentication":
      return "Sign in, then refresh";
    case "missing":
    case "incompatible":
      return "DocFerry Agent Kit needs attention";
    case "timeout":
      return "DocFerry timed out. Refresh to try again";
    case "network":
      return "Could not reach DocFerry. Refresh to try again";
    case "service":
      return "DocFerry is temporarily unavailable";
    case "cancelled":
      return "Refresh cancelled";
    default:
      return "Could not load shares. See DocFerry output";
  }
}

export function isSupportedAgentKitVersion(
  output: string,
  minimumVersion = MIN_AGENT_KIT_VERSION
): boolean {
  const match = output.trim().match(/^docferry\s+(\d+)\.(\d+)\.(\d+)(?:\b|[-+])/i);
  const minimum = minimumVersion.match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!match || !minimum) {
    return false;
  }
  const actualParts = match.slice(1, 4).map(Number);
  const minimumParts = minimum.slice(1, 4).map(Number);
  for (let index = 0; index < actualParts.length; index += 1) {
    if (actualParts[index] !== minimumParts[index]) {
      return actualParts[index] > minimumParts[index];
    }
  }
  return true;
}

export function membershipLabel(membership: MembershipSummary): string {
  const plan = membership.access_role === "admin"
    ? "Organization"
    : membership.plan_display_name || membership.plan_key || "Free";
  const noteLimit = membership.share_limit_unlimited || membership.active_share_limit === null
    ? "Unlimited"
    : String(membership.active_share_limit ?? 0);
  const folderLimit = membership.folder_share_limit_unlimited || membership.active_folder_share_limit === null
    ? "Unlimited"
    : String(membership.active_folder_share_limit ?? 0);
  const parts = [
    plan,
    `Notes ${membership.active_share_count ?? 0}/${noteLimit}`,
    `Folders ${membership.active_folder_share_count ?? 0}/${folderLimit}`
  ];
  if (membership.media_note?.enabled) {
    const importLimit = membership.media_note_usage?.monthly_job_limit === null
      ? "Unlimited"
      : String(membership.media_note_usage?.monthly_job_limit ?? 0);
    parts.push(`Detailed notes ${membership.media_note_usage?.monthly_jobs_used ?? 0}/${importLimit}`);
  }
  return parts.join(" · ");
}
