#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
TARGETS = ("darwin-arm64", "darwin-x64", "linux-x64", "win32-x64")


class MarketplaceReleaseVerificationTests(unittest.TestCase):
    def create_release(self, directory: Path, target_override: dict[str, str] | None = None) -> None:
        target_override = target_override or {}
        checksums: list[str] = []
        for target in TARGETS:
            path = directory / f'docferry-vscode-{MANIFEST["version"]}-{target}.vsix'
            packaged_manifest = {
                "name": MANIFEST["name"],
                "publisher": MANIFEST["publisher"],
                "version": MANIFEST["version"],
                "preview": True,
                "pricing": "Free",
            }
            packaged_target = target_override.get(target, target)
            vsix_manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Id="{MANIFEST["name"]}" Version="{MANIFEST["version"]}" Publisher="{MANIFEST["publisher"]}" TargetPlatform="{packaged_target}" />
  </Metadata>
</PackageManifest>
'''
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("extension.vsixmanifest", vsix_manifest)
                archive.writestr("extension/package.json", json.dumps(packaged_manifest))
            checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
        (directory / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")

    def verify(self, directory: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(ROOT / "scripts" / "verify_marketplace_release.py"),
                str(directory),
                "--tag",
                f'v{MANIFEST["version"]}',
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_accepts_exact_checksummed_platform_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.create_release(directory)
            result = self.verify(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = json.loads(result.stdout)
            self.assertTrue(evidence["ok"])
            self.assertEqual({package["target"] for package in evidence["packages"]}, set(TARGETS))

    def test_rejects_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.create_release(directory)
            path = directory / f'docferry-vscode-{MANIFEST["version"]}-linux-x64.vsix'
            path.write_bytes(path.read_bytes() + b"tampered")
            result = self.verify(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Checksum mismatch", result.stderr)

    def test_rejects_manifest_target_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            self.create_release(directory, {"linux-x64": "darwin-arm64"})
            result = self.verify(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Duplicate VSIX target", result.stderr)

    def test_public_export_refuses_to_delete_public_only_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "public"
            destination.mkdir()
            public_only = destination / "public-only.txt"
            public_only.write_text("keep\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "export_public_repo.py"), str(destination)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Public release files are missing", result.stderr)
            self.assertEqual(public_only.read_text(encoding="utf-8"), "keep\n")


if __name__ == "__main__":
    unittest.main()
