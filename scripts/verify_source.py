#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".build", ".git", ".vscode-test", "bin", "dist", "node_modules", "out", "__pycache__"}
SKIP_CONTENT_SCAN = {Path("scripts/verify_source.py"), Path("scripts/verify_vsix.py")}
TEXT_SUFFIXES = {"", ".cjs", ".css", ".html", ".js", ".json", ".md", ".mjs", ".py", ".sh", ".ts", ".txt", ".yaml", ".yml"}
FORBIDDEN_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]{40,}"),
    re.compile(r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"login\.fuyo-ai\.tech|docferry\.fuyo-ai\.tech|29\.226\.94\.19"),
    re.compile(r"Docferry-Private-Src"),
)


def source_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and not any(part in EXCLUDED_DIRECTORIES for part in path.relative_to(ROOT).parts)
    )


def verify_runtime() -> None:
    provenance = json.loads((ROOT / "runtime" / "PROVENANCE.json").read_text(encoding="utf-8"))
    if provenance.get("version") != "0.4.6":
        raise SystemExit("Bundled Agent Kit provenance must remain at 0.4.6.")
    runtime = ROOT / "runtime" / "src" / "docferry_agent_kit"
    for name, expected in provenance.get("files", {}).items():
        actual = hashlib.sha256((runtime / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"Bundled runtime differs from provenance: {name}")


def verify_workflows() -> None:
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            match = re.search(r"\buses:\s*[^\s]+@([^\s]+)", line)
            if match and not re.fullmatch(r"[0-9a-f]{40}", match.group(1)):
                raise SystemExit(f"GitHub Action is not pinned to a commit: {workflow.name}: {line.strip()}")


def main() -> int:
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    if manifest.get("repository", {}).get("url") != "https://github.com/fyaic/Docferry-VSCode.git":
        raise SystemExit("Marketplace repository metadata is not the public release repository.")
    if manifest.get("capabilities", {}).get("untrustedWorkspaces", {}).get("supported") is not False:
        raise SystemExit("Restricted Mode support must remain disabled.")

    for path in source_files():
        relative = path.relative_to(ROOT)
        if relative in SKIP_CONTENT_SCAN or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                raise SystemExit(f"Public source contains forbidden data: {relative}: {pattern.pattern}")

    verify_runtime()
    verify_workflows()
    print(json.dumps({"ok": True, "source_files": len(source_files()), "agent_kit": "0.4.6"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
