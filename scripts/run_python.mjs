import { spawnSync } from "node:child_process";
import process from "node:process";

const [script, ...scriptArgs] = process.argv.slice(2);
if (!script) {
  console.error("Usage: node scripts/run_python.mjs <script.py> [args...]");
  process.exit(2);
}

const candidates = [];
if (process.env.PYTHON) {
  candidates.push({ command: process.env.PYTHON, prefix: [] });
}
if (process.platform === "win32") {
  candidates.push(
    { command: "python", prefix: [] },
    { command: "python3", prefix: [] },
    { command: "py", prefix: ["-3"] }
  );
} else {
  candidates.push(
    { command: "python3", prefix: [] },
    { command: "python", prefix: [] }
  );
}

for (const candidate of candidates) {
  const probe = spawnSync(
    candidate.command,
    [
      ...candidate.prefix,
      "-c",
      "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
    ],
    { stdio: "ignore" }
  );
  if (probe.status !== 0) {
    continue;
  }
  const result = spawnSync(
    candidate.command,
    [...candidate.prefix, script, ...scriptArgs],
    { stdio: "inherit" }
  );
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status ?? 1);
}

console.error("Python 3.11 or newer was not found.");
process.exit(127);
