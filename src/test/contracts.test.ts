import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  advancedImportDecision,
  buildCliArgs,
  classifyOperationError,
  dashboardCommandArgs,
  defaultCliCandidates,
  isCanonicalDocFerryShareUrl,
  isPathInside,
  isShareActionable,
  isShareHistoryDeletable,
  isSupportedAgentKitVersion,
  isTrustedDashboardHandoffUrl,
  isTrustedDeviceLoginUrl,
  mediaNoteProviderForUrl,
  mediaNoteFailureMessage,
  mediaNotePreview,
  mediaNoteStatusKind,
  membershipLabel,
  parseJsonOutput,
  redactOutput,
  resolveWorkspaceOutput,
  shareTreeFailureMessage,
  shouldUseAdvancedImport,
  VS_CODE_LOGIN_ARGS,
  validateImportFolder,
  workspaceRootForPath,
  workspaceRelativePath
} from "../contracts";

test("standard distribution CLI locations are cross-platform", () => {
  assert.deepEqual(defaultCliCandidates("/Users/alex", "darwin"), [
    "/Users/alex/.local/bin/docferry",
    "/Users/alex/.local/share/docferry-agent-kit/venv/bin/docferry"
  ]);
  assert.deepEqual(defaultCliCandidates("C:\\Users\\Alex", "win32"), [
    "C:\\Users\\Alex\\.local\\bin\\docferry.exe",
    "C:\\Users\\Alex\\.local\\share\\docferry-agent-kit\\venv\\Scripts\\docferry.exe"
  ]);
});

test("buildCliArgs keeps workspace before the command", () => {
  const root = path.resolve("/tmp/docferry-project");
  assert.deepEqual(buildCliArgs(root, ["publish", "notes/a b.md"]), [
    "--workspace",
    root,
    "publish",
    "notes/a b.md"
  ]);
});

test("parseJsonOutput accepts one JSON result and rejects noise", () => {
  assert.deepEqual(parseJsonOutput<{ ok: boolean }>(' {"ok":true}\n'), { ok: true });
  assert.throws(() => parseJsonOutput("status\n{\"ok\":true}"), /unreadable/);
});

test("redactOutput removes provider and session credentials", () => {
  const value = 'Bearer secret-token sk-or-v1-example {"session_token":"private"}';
  const redacted = redactOutput(value);
  assert.equal(redacted.includes("secret-token"), false);
  assert.equal(redacted.includes("sk-or-v1-example"), false);
  assert.equal(redacted.includes('"private"'), false);
});

test("workspace paths cannot escape their root", () => {
  const root = path.resolve("/tmp/project");
  assert.equal(isPathInside(root, path.join(root, "docs", "a.md")), true);
  assert.equal(isPathInside(root, path.resolve(root, "..", "private.md")), false);
  assert.equal(workspaceRelativePath(root, path.join(root, "docs")), "docs");
  assert.throws(() => workspaceRelativePath(root, path.resolve(root, "..")), /inside/);
  assert.equal(resolveWorkspaceOutput(root, "imports/note.md"), path.join(root, "imports", "note.md"));
  assert.throws(() => resolveWorkspaceOutput(root, "../private.md"), /outside/);
});

test("workspace paths resolve filesystem aliases without allowing symlink escapes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "docferry-paths-"));
  const workspace = path.join(root, "workspace");
  const alias = path.join(root, "workspace-alias");
  const outside = path.join(root, "outside");
  try {
    fs.mkdirSync(path.join(workspace, "docs"), { recursive: true });
    fs.mkdirSync(outside, { recursive: true });
    fs.writeFileSync(path.join(workspace, "docs", "note.md"), "# Note\n", "utf8");
    fs.symlinkSync(workspace, alias, process.platform === "win32" ? "junction" : "dir");
    fs.symlinkSync(outside, path.join(workspace, "escape"), process.platform === "win32" ? "junction" : "dir");

    assert.equal(isPathInside(alias, path.join(workspace, "docs", "note.md")), true);
    assert.equal(workspaceRelativePath(alias, path.join(workspace, "docs", "note.md")), path.join("docs", "note.md"));
    assert.equal(isPathInside(workspace, path.join(alias, "docs", "note.md")), true);
    assert.equal(isPathInside(workspace, path.join(workspace, "escape", "private.md")), false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("workspace matching resolves aliases and chooses the most specific root", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "docferry-workspaces-"));
  const outer = path.join(root, "workspace");
  const nested = path.join(outer, "packages", "app");
  const nestedAlias = path.join(root, "app-alias");
  try {
    fs.mkdirSync(path.join(nested, "docs"), { recursive: true });
    fs.symlinkSync(nested, nestedAlias, process.platform === "win32" ? "junction" : "dir");
    const candidate = path.join(nestedAlias, "docs", "note.md");

    assert.equal(workspaceRootForPath([outer, nestedAlias], candidate), nestedAlias);
    assert.equal(workspaceRootForPath([nestedAlias, outer], path.join(nested, "docs")), nestedAlias);
    assert.equal(workspaceRootForPath([outer, nestedAlias], path.join(root, "outside.md")), undefined);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Agent Kit version contract requires the current Marketplace runtime", () => {
  assert.equal(isSupportedAgentKitVersion("docferry 0.4.2\n"), true);
  assert.equal(isSupportedAgentKitVersion("docferry 0.5.0\n"), true);
  assert.equal(isSupportedAgentKitVersion("docferry 0.4.1\n"), false);
  assert.equal(isSupportedAgentKitVersion("unexpected output\n"), false);
});

test("Dashboard commands use a short-lived DocFerry-only handoff", () => {
  assert.deepEqual(dashboardCommandArgs("home"), ["dashboard", "--section", "home", "--no-browser"]);
  assert.equal(
    isTrustedDashboardHandoffUrl("https://docferry.bondie.io/v0/auth/dashboard-open?code=once"),
    true
  );
  assert.equal(isTrustedDashboardHandoffUrl("https://account.bondie.io/account?code=once"), false);
  assert.equal(
    isTrustedDashboardHandoffUrl("https://docferry.bondie.io.evil.test/v0/auth/dashboard-open?code=once"),
    false
  );
  assert.equal(
    isTrustedDashboardHandoffUrl("https://docferry.bondie.io/v0/auth/dashboard-open?code=once&next=bad"),
    false
  );
  assert.equal(isTrustedDashboardHandoffUrl("https://docferry.bondie.io/dashboard?code=once"), false);
});

test("VS Code sign-in uses its product-owned system-browser Device Code flow", () => {
  assert.deepEqual(VS_CODE_LOGIN_ARGS, ["login", "--device-code", "--client", "vscode", "--no-browser"]);
  assert.equal(
    isTrustedDeviceLoginUrl("https://docferry.bondie.io/activate?user_code=BOND-1234"),
    true
  );
  assert.equal(isTrustedDeviceLoginUrl("https://account.bondie.io/activate?user_code=BOND-1234"), false);
  assert.equal(
    isTrustedDeviceLoginUrl("https://docferry.bondie.io/activate?user_code=BOND-1234&next=bad"),
    false
  );
});

test("import folder must stay visible and relative", () => {
  assert.equal(validateImportFolder("./DocFerry Imports"), "DocFerry Imports");
  assert.throws(() => validateImportFolder("../private"), /visible/);
  assert.throws(() => validateImportFolder(".hidden/imports"), /visible/);
  assert.throws(() => validateImportFolder("/tmp/imports"), /visible/);
});

test("only the canonical DocFerry origin is treated as a share", () => {
  assert.equal(isCanonicalDocFerryShareUrl("https://docferry.bondie.io/s/abc123"), true);
  assert.equal(isCanonicalDocFerryShareUrl("https://example.com/s/abc123"), false);
  assert.equal(isCanonicalDocFerryShareUrl("http://docferry.bondie.io/s/abc123"), false);
  assert.equal(isCanonicalDocFerryShareUrl("https://docferry.bondie.io.evil.test/s/abc123"), false);
});

test("Advanced Import is automatic only for eligible non-share links", () => {
  const pro = {
    feature_gates: { "docferry.ai.assist": true },
    media_note: { enabled: true, supported_providers: ["web", "youtube"] }
  };
  assert.equal(shouldUseAdvancedImport("https://example.com/article", pro), true);
  assert.equal(shouldUseAdvancedImport("https://www.youtube.com/watch?v=abc", pro), true);
  assert.equal(shouldUseAdvancedImport("https://example.com/audio.mp3", pro), false);
  assert.equal(shouldUseAdvancedImport("https://docferry.bondie.io/s/abc123", pro), false);
  assert.equal(shouldUseAdvancedImport("https://example.com/article", {}), false);
  assert.equal(
    advancedImportDecision("https://example.com/audio.mp3", pro).reason,
    "provider_unsupported"
  );
  assert.equal(
    advancedImportDecision("https://www.tiktok.com/@bondie/video/1", pro).reason,
    "mandatory_provider_unavailable"
  );
  assert.equal(
    advancedImportDecision("https://example.com/article", {
      feature_gates: { "docferry.ai.assist": true },
      media_note: { enabled: false, supported_providers: ["web"] }
    }).reason,
    "runtime_disabled"
  );
});

test("Advanced Import provider classification matches the Agent Kit contract", () => {
  assert.equal(mediaNoteProviderForUrl("https://youtu.be/example"), "youtube");
  assert.equal(mediaNoteProviderForUrl("https://mp.weixin.qq.com/s/article"), "wechat");
  assert.equal(mediaNoteProviderForUrl("https://mp.weixin.qq.com.evil.example/s/article"), "web");
  assert.equal(mediaNoteProviderForUrl("https://cdn.example.com/clip.MP4?download=1"), "video");
  assert.equal(mediaNoteProviderForUrl("https://example.com/article"), "web");
});

test("background detailed-note status and preview stay bounded and user-readable", () => {
  assert.equal(mediaNoteStatusKind("queued"), "processing");
  assert.equal(mediaNoteStatusKind("fetching"), "processing");
  assert.equal(mediaNoteStatusKind("extracted"), "ready");
  assert.equal(mediaNoteStatusKind("degraded"), "ready");
  assert.equal(mediaNoteStatusKind("failed"), "failed");
  assert.deepEqual(
    mediaNotePreview({
      source_url: "https://www.youtube.com/watch?v=example",
      result_contract: {
        title: "  A useful  talk  ",
        summary: { text: "  Clear summary  with evidence. " }
      }
    }),
    { title: "A useful talk", summary: "Clear summary with evidence." }
  );
  assert.equal(
    mediaNotePreview({ source_url: "https://example.com/article" }).title,
    "example.com"
  );
  assert.match(mediaNoteFailureMessage({ status: "cancelled" }), /Nothing was saved/);
});

test("share status and tree failures expose only valid actions and useful guidance", () => {
  assert.equal(isShareActionable("published"), true);
  assert.equal(isShareActionable("active"), true);
  assert.equal(isShareActionable("stopped"), false);
  assert.equal(isShareActionable("revoked"), false);
  assert.equal(isShareHistoryDeletable("stopped"), true);
  assert.equal(isShareHistoryDeletable("revoked"), true);
  assert.equal(isShareHistoryDeletable("expired"), false);

  assert.equal(classifyOperationError(new Error("No DocFerry session. Sign in.")), "authentication");
  assert.equal(shareTreeFailureMessage(new Error("connect ECONNREFUSED 127.0.0.1")), "Could not reach DocFerry. Refresh to try again");
  assert.equal(shareTreeFailureMessage(new Error("502 Bad Gateway")), "DocFerry is temporarily unavailable");
  assert.equal(
    shareTreeFailureMessage({ kind: "missing", message: "CLI missing" }),
    "DocFerry Agent Kit needs attention"
  );
});

test("membership label renders server-managed organization limits without exposing its hidden role name", () => {
  assert.equal(
    membershipLabel({
      access_role: "admin",
      active_share_count: 12,
      active_share_limit: null,
      active_folder_share_count: 3,
      active_folder_share_limit: null
    }),
    "Organization · Notes 12/Unlimited · Folders 3/Unlimited"
  );
  assert.equal(membershipLabel({}), "Free · Notes 0/0 · Folders 0/0");
  assert.equal(
    membershipLabel({
      plan_display_name: "Pro",
      active_share_count: 1,
      active_share_limit: 20,
      active_folder_share_count: 1,
      active_folder_share_limit: 5,
      media_note: { enabled: true },
      media_note_usage: { monthly_jobs_used: 2, monthly_job_limit: 30 }
    }),
    "Pro · Notes 1/20 · Folders 1/5 · Detailed notes 2/30"
  );
});
