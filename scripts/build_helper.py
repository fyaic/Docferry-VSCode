#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


EXTENSION_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = EXTENSION_ROOT / ".build" / "helper"
VENV_ROOT = EXTENSION_ROOT / ".build" / "pyinstaller-venv"
PYINSTALLER_VERSION = "6.22.0"
HOOKS_VERSION = "2026.6"


def venv_python() -> Path:
    return VENV_ROOT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def pyinstaller_python() -> Path:
    python = venv_python()
    if not python.is_file():
        venv.EnvBuilder(with_pip=True, clear=True).create(VENV_ROOT)
    probe_script = (
        "from importlib.metadata import version; "
        "print(version('pyinstaller'), version('pyinstaller-hooks-contrib'))"
    )
    probe = subprocess.run([str(python), "-c", probe_script], capture_output=True, text=True, check=False)
    if probe.returncode != 0 or probe.stdout.strip() != f"{PYINSTALLER_VERSION} {HOOKS_VERSION}":
        subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--upgrade",
                f"pyinstaller=={PYINSTALLER_VERSION}",
                f"pyinstaller-hooks-contrib=={HOOKS_VERSION}",
            ],
            check=True,
        )
    return python


def main() -> int:
    runtime_source = EXTENSION_ROOT / "runtime" / "src"
    if not (runtime_source / "docferry_agent_kit" / "cli.py").is_file():
        raise SystemExit("Run scripts/sync_agent_kit.py before building the helper.")
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    BUILD_ROOT.mkdir(parents=True)
    binary_name = "docferry.exe" if os.name == "nt" else "docferry"
    subprocess.run(
        [
            str(pyinstaller_python()),
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--onefile",
            "--name",
            Path(binary_name).stem,
            "--paths",
            str(runtime_source),
            "--distpath",
            str(EXTENSION_ROOT / "bin"),
            "--workpath",
            str(BUILD_ROOT / "work"),
            "--specpath",
            str(BUILD_ROOT / "spec"),
            str(EXTENSION_ROOT / "runtime" / "helper_entry.py"),
        ],
        check=True,
    )
    binary = EXTENSION_ROOT / "bin" / binary_name
    if not binary.is_file():
        raise SystemExit(f"Bundled helper was not created: {binary}")
    if os.name != "nt":
        binary.chmod(0o755)
    version = subprocess.run(
        [str(binary), "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"Built {binary.name}: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
