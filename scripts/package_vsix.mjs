import { readFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";

const manifest = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
const targets = {
  "darwin-arm64": "darwin-arm64",
  "darwin-x64": "darwin-x64",
  "linux-arm64": "linux-arm64",
  "linux-x64": "linux-x64",
  "win32-arm64": "win32-arm64",
  "win32-x64": "win32-x64"
};
const key = `${process.platform}-${process.arch}`;
const target = targets[key];
if (!target) {
  throw new Error(`Unsupported VS Code packaging target: ${key}`);
}
const output = `dist/docferry-vscode-${manifest.version}-${target}.vsix`;
const result = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["vsce", "package", "--target", target, "--no-dependencies", "--out", output],
  { stdio: "inherit" }
);
if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
