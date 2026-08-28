from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path


def canonical_workspace_path(root: Path) -> str:
    value = root.expanduser().resolve().as_posix().rstrip("/")
    value = unicodedata.normalize("NFC", value)
    # Match the Obsidian/Electron implementation. JavaScript lowercasing is
    # not Unicode casefolding (for example, German sharp-s), so casefold()
    # would create a different vault id for the same Windows workspace.
    return value.lower() if os.name == "nt" else value


def workspace_id(root: Path) -> str:
    """Return the stable vault identity used by the Obsidian plugin."""
    path = canonical_workspace_path(root)
    name = unicodedata.normalize("NFC", path.rsplit("/", 1)[-1])
    source = f"{name}|{path}"
    return f"vlt_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:24]}"


def unresolved_workspace_path(value: str | None) -> Path:
    raw = Path(value).expanduser() if value else Path(os.environ.get("PWD") or os.getcwd()).expanduser()
    return Path(os.path.abspath(raw))


def legacy_workspace_ids(root: Path, raw_root: Path | None = None) -> tuple[str, ...]:
    """Return prior Agent Kit and Obsidian ids for explicit migration only."""
    resolved = root.expanduser().resolve()
    unresolved = (raw_root or root).expanduser()
    if not unresolved.is_absolute():
        unresolved = Path(os.path.abspath(unresolved))

    candidates: list[tuple[str, str]] = []
    path_values = {
        str(unresolved),
        unresolved.as_posix(),
        str(resolved),
        resolved.as_posix(),
    }
    for path_value in path_values:
        candidates.append(("workspace", path_value))
    for name in {unresolved.name, resolved.name}:
        for path_value in path_values:
            candidates.append(("vlt", f"{name}|{path_value}"))

    values: list[str] = []
    for prefix, source in candidates:
        value = f"{prefix}_{hashlib.sha256(source.encode('utf-8')).hexdigest()[:24]}"
        if value != workspace_id(resolved) and value not in values:
            values.append(value)
    return tuple(values)


def workspace_source_aliases(
    root: Path,
    relative_path: str,
    raw_root: Path | None = None,
) -> tuple[str, ...]:
    """Return exact physical source paths that can prove workspace ownership."""
    relative = Path(relative_path.replace("\\", "/"))
    if relative.is_absolute() or ".." in relative.parts:
        return ()
    resolved_root = root.expanduser().resolve()
    unresolved_root = (raw_root or root).expanduser()
    if not unresolved_root.is_absolute():
        unresolved_root = Path(os.path.abspath(unresolved_root))
    candidates = [
        unresolved_root / relative,
        resolved_root / relative,
    ]
    try:
        resolved_source = (resolved_root / relative).resolve(strict=True)
        resolved_source.relative_to(resolved_root)
        candidates.append(resolved_source)
    except (OSError, ValueError):
        pass
    aliases: list[str] = []
    for candidate in candidates:
        value = unicodedata.normalize("NFC", candidate.as_posix())
        if value not in aliases:
            aliases.append(value)
    return tuple(aliases)


def source_path_matches_workspace(
    source_path: object,
    root: Path,
    relative_path: str,
    raw_root: Path | None = None,
) -> bool:
    if not isinstance(source_path, str) or not source_path.strip():
        return False
    candidate = unicodedata.normalize("NFC", source_path.replace("\\", "/"))
    aliases = workspace_source_aliases(root, relative_path, raw_root)
    if os.name == "nt":
        candidate = candidate.lower()
        return any(candidate == alias.lower() for alias in aliases)
    return candidate in aliases


def source_paths_match(candidate: object, target: object, *, case_insensitive: bool = False) -> bool:
    """Match Share source paths with the same normalization as the service."""
    if not isinstance(candidate, str) or not isinstance(target, str):
        return False

    def normalize(value: str) -> str:
        path = "/".join(part for part in value.replace("\\", "/").strip().strip("/").split("/") if part)
        return unicodedata.normalize("NFC", path)

    def is_windows_path(value: str) -> bool:
        stripped = value.strip()
        return stripped.startswith(("\\\\", "//")) or re.match(r"^[A-Za-z]:[\\/]", stripped) is not None

    left = normalize(candidate)
    right = normalize(target)
    if case_insensitive or is_windows_path(candidate) or is_windows_path(target):
        return left.casefold() == right.casefold()
    return left == right
