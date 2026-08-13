#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
VERSION = MANIFEST["version"]
machine = os.environ.get("PROCESSOR_ARCHITECTURE", "x64") if os.name == "nt" else os.uname().machine
architecture = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "x64",
    "x86_64": "x64",
}.get(machine.lower(), machine.lower())
platform_name = "win32" if os.name == "nt" else sys.platform
TARGET = f"{platform_name}-{architecture}"
VSIX = ROOT / "dist" / f"docferry-vscode-{VERSION}-{TARGET}.vsix"
REQUIRED = {
    "extension/package.json",
    "extension/readme.md",
    "extension/LICENSE.txt",
    "extension/PRIVACY.md",
    "extension/SECURITY.md",
    "extension/SUPPORT.md",
    "extension/THIRD_PARTY_NOTICES.md",
    "extension/resources/docferry-256.png",
    "extension/dist/extension.js",
}
FORBIDDEN_PATTERNS = (
    re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(rb"login\.fuyo-ai\.tech|docferry\.fuyo-ai\.tech|29\.226\.94\.19"),
    re.compile(rb"Docferry-Private-Src"),
)


def safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    for info in archive.infolist():
        member = PurePosixPath(info.filename)
        if member.is_absolute() or ".." in member.parts:
            raise SystemExit(f"Unsafe VSIX member: {info.filename}")
    archive.extractall(target)


def main() -> int:
    if not VSIX.is_file():
        raise SystemExit(f"VSIX is missing: {VSIX}")
    with zipfile.ZipFile(VSIX) as archive:
        names = set(archive.namelist())
        missing = sorted(REQUIRED - names)
        if missing:
            raise SystemExit(f"Required VSIX files are missing: {missing}")
        if any(name.endswith((".map", ".ts", ".py")) for name in names if name.startswith("extension/")):
            raise SystemExit("VSIX contains source or source-map files.")
        binary_name = "docferry.exe" if os.name == "nt" else "docferry"
        binary_member = f"extension/bin/{binary_name}"
        if binary_member not in names:
            raise SystemExit("VSIX does not contain the platform helper.")
        payload = b"\n".join(archive.read(name) for name in sorted(names) if not name.endswith("/"))
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(payload):
                raise SystemExit(f"VSIX contains forbidden data: {pattern.pattern!r}")

        extension_manifest = json.loads(archive.read("extension/package.json"))
        if extension_manifest.get("pricing") != "Free" or extension_manifest.get("preview") is not True:
            raise SystemExit("Marketplace pricing or Preview metadata is incorrect.")
        if extension_manifest.get("capabilities", {}).get("untrustedWorkspaces", {}).get("supported") is not False:
            raise SystemExit("Restricted Mode support must remain disabled.")

        with tempfile.TemporaryDirectory(prefix="docferry-vsix-") as directory:
            target = Path(directory)
            safe_extract(archive, target)
            binary = target / binary_member
            if os.name != "nt":
                binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
            output = subprocess.run(
                [str(binary), "--version"],
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            ).stdout.strip()
            if output != "docferry 0.4.2":
                raise SystemExit(f"Unexpected bundled helper version: {output}")
            health = subprocess.run(
                [str(binary), "health"],
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            ).stdout.strip()
            health_body = json.loads(health)
            if health_body.get("ok") is not True or health_body.get("service") != "docferry-share":
                raise SystemExit(f"Bundled helper HTTPS health check failed: {health_body}")

    digest = hashlib.sha256(VSIX.read_bytes()).hexdigest()
    print(
        json.dumps(
            {
                "ok": True,
                "vsix": VSIX.name,
                "sha256": digest,
                "helper": "0.4.2",
                "https_health": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
