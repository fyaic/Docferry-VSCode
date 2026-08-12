import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runTests } from "@vscode/test-electron";


const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const workspace = path.join(root, ".build", "extension-test-workspace");
fs.mkdirSync(workspace, { recursive: true });
fs.writeFileSync(path.join(workspace, "README.md"), "# DocFerry Extension Host Smoke\n", "utf8");

const localCandidates = process.platform === "darwin"
  ? ["/Applications/Visual Studio Code.app/Contents/MacOS/Electron"]
  : process.platform === "win32"
    ? []
    : ["/usr/share/code/code", "/usr/bin/code"];
const localExecutable = process.env.DOCFERRY_VSCODE_TEST_EXECUTABLE
  || localCandidates.find((candidate) => fs.existsSync(candidate));

try {
  await runTests({
    ...(localExecutable
      ? { vscodeExecutablePath: localExecutable }
      : { version: process.env.DOCFERRY_VSCODE_TEST_VERSION || "1.96.4" }),
    extensionDevelopmentPath: root,
    extensionTestsPath: path.join(root, "out", "test", "suite", "index.js"),
    launchArgs: [
      workspace,
      "--disable-extensions",
      "--disable-workspace-trust",
      "--skip-welcome",
      "--skip-release-notes"
    ]
  });
} catch (error) {
  console.error(error);
  process.exit(1);
}
