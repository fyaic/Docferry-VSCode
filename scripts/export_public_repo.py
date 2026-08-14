#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    ".build",
    ".git",
    ".vscode-test",
    "bin",
    "dist",
    "node_modules",
    "out",
}
IGNORED_FILES = {".DS_Store"}


def ignored(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in EXCLUDED or name in IGNORED_FILES or name == "__pycache__"
    }


def managed_files(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.rglob("*")
        if (path.is_file() or path.is_symlink())
        and path.name not in IGNORED_FILES
        and not any(part in EXCLUDED or part == "__pycache__" for part in path.relative_to(root).parts)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the self-contained public VS Code release source.")
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise SystemExit("Destination must be outside the extension source directory.")
    destination.mkdir(parents=True, exist_ok=True)
    public_only = sorted(managed_files(destination) - managed_files(ROOT))
    if public_only:
        rendered = "\n".join(f"- {path.as_posix()}" for path in public_only)
        raise SystemExit(
            "Public release files are missing from the canonical source. "
            f"Sync or remove them before export:\n{rendered}"
        )
    for item in destination.iterdir():
        if item.name != ".git":
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    for source in ROOT.iterdir():
        if source.name in EXCLUDED:
            continue
        target = destination / source.name
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignored)
        else:
            shutil.copy2(source, target)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
