#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path


EXTENSION_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(os.environ.get("DOCFERRY_MONOREPO_ROOT", EXTENSION_ROOT.parent)).expanduser().resolve()
SOURCE = REPO_ROOT / "agent-kit" / "src" / "docferry_agent_kit"
TARGET = EXTENSION_ROOT / "runtime" / "src" / "docferry_agent_kit"
FILES = ("__init__.py", "cli.py", "conversation.py", "local_assets.py", "workspace_identity.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    TARGET.mkdir(parents=True, exist_ok=True)
    provenance_path = EXTENSION_ROOT / "runtime" / "PROVENANCE.json"
    copied: dict[str, str] = {}
    if SOURCE.is_dir():
        for name in FILES:
            source = SOURCE / name
            if not source.is_file():
                raise SystemExit(f"Agent Kit source is missing: {source}")
            target = TARGET / name
            shutil.copy2(source, target)
            copied[name] = sha256(target)
        version = json.loads((REPO_ROOT / "agent-kit" / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))["version"]
    else:
        if not provenance_path.is_file():
            raise SystemExit("Vendored Agent Kit provenance is missing.")
        existing = json.loads(provenance_path.read_text(encoding="utf-8"))
        version = existing.get("version")
        for name in FILES:
            target = TARGET / name
            if not target.is_file() or existing.get("files", {}).get(name) != sha256(target):
                raise SystemExit(f"Vendored Agent Kit source does not match provenance: {name}")
            copied[name] = sha256(target)
    provenance = {
        "schema_version": 1,
        "component": "docferry-agent-kit-cli-runtime",
        "version": version,
        "canonical_source": "agent-kit/src/docferry_agent_kit",
        "files": copied,
    }
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"ok": True, "version": version, "files": len(copied)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
