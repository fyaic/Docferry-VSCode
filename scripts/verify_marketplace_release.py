#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
EXPECTED_TARGETS = {"darwin-arm64", "darwin-x64", "linux-x64", "win32-x64"}
VSIX_NAMESPACE = {"vsix": "http://schemas.microsoft.com/developer/vsx-schema/2011"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify checksummed, platform-specific VSIX files before Marketplace publication."
    )
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--tag", required=True)
    return parser.parse_args()


def parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?([^/]+)", line.strip())
        if not match:
            raise SystemExit(f"Invalid SHA256SUMS line: {line!r}")
        digest, filename = match.groups()
        if filename in checksums:
            raise SystemExit(f"Duplicate SHA256SUMS entry: {filename}")
        checksums[filename] = digest
    return checksums


def read_target(vsix: zipfile.ZipFile) -> str:
    root = ElementTree.fromstring(vsix.read("extension.vsixmanifest"))
    identity = root.find(".//vsix:Identity", VSIX_NAMESPACE)
    if identity is None:
        raise SystemExit("VSIX manifest is missing its Identity element.")
    expected_identity = {
        "Id": MANIFEST["name"],
        "Publisher": MANIFEST["publisher"],
        "Version": MANIFEST["version"],
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise SystemExit(f"VSIX Identity {key} must be {expected!r}.")
    target = identity.get("TargetPlatform")
    if not target:
        raise SystemExit("VSIX manifest is missing TargetPlatform.")
    return target


def main() -> int:
    args = parse_args()
    release_dir = args.release_dir.resolve()
    version = MANIFEST["version"]
    expected_tag = f"v{version}"
    if args.tag != expected_tag:
        raise SystemExit(f"Release tag {args.tag!r} does not match package version {version!r}.")

    checksums_path = release_dir / "SHA256SUMS"
    if not checksums_path.is_file():
        raise SystemExit(f"Missing checksum file: {checksums_path}")

    expected_files = {
        f"docferry-vscode-{version}-{target}.vsix" for target in EXPECTED_TARGETS
    }
    vsix_files = sorted(release_dir.glob("*.vsix"))
    actual_files = {path.name for path in vsix_files}
    if actual_files != expected_files:
        raise SystemExit(
            "Marketplace release assets do not match the required platform set: "
            f"expected={sorted(expected_files)}, actual={sorted(actual_files)}"
        )

    checksums = parse_checksums(checksums_path)
    if set(checksums) != expected_files:
        raise SystemExit("SHA256SUMS must contain exactly the four Marketplace VSIX files.")

    observed_targets: set[str] = set()
    evidence: list[dict[str, str | int]] = []
    for path in vsix_files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != checksums[path.name]:
            raise SystemExit(f"Checksum mismatch: {path.name}")

        with zipfile.ZipFile(path) as archive:
            target = read_target(archive)
            packaged_manifest = json.loads(archive.read("extension/package.json"))
        if target not in EXPECTED_TARGETS:
            raise SystemExit(f"Unexpected VSIX target: {target}")
        if target in observed_targets:
            raise SystemExit(f"Duplicate VSIX target: {target}")
        if packaged_manifest.get("preview") is not True:
            raise SystemExit(f"{path.name} must retain Marketplace Preview metadata.")
        if packaged_manifest.get("pricing") != "Free":
            raise SystemExit(f"{path.name} must retain Marketplace Free pricing metadata.")
        observed_targets.add(target)
        evidence.append(
            {
                "file": path.name,
                "target": target,
                "sha256": digest,
                "size": path.stat().st_size,
            }
        )

    if observed_targets != EXPECTED_TARGETS:
        raise SystemExit(f"Missing VSIX targets: {sorted(EXPECTED_TARGETS - observed_targets)}")

    print(
        json.dumps(
            {
                "ok": True,
                "extension": f'{MANIFEST["publisher"]}.{MANIFEST["name"]}',
                "version": version,
                "tag": args.tag,
                "preview": True,
                "packages": evidence,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
