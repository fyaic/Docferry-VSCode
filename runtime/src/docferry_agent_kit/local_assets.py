"""Local asset extraction, upload and rewriting for CLI/MCP publishing.

The Obsidian plugin uploads referenced local files (images, media,
attachments) and rewrites snapshot sources to ``docferry-asset://`` URLs.
CLI and MCP publishers send Markdown only, so the same contract is honored
here at the Markdown level: references are extracted in document order,
files inside the workspace are uploaded through ``POST /v0/assets``, and the
reference syntax is rewritten to ``docferry-asset://{asset_id}`` before the
payload reaches the server, which then renders them as public asset URLs.

Extraction mirrors ``plugin/src/local-image-refs.ts``: wiki embeds, wiki
links, Markdown images/links, and raw HTML ``src``/``href`` attributes on
media and anchor elements. References inside fenced code blocks, inline code
or HTML comments are masked and never leave the workspace.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

CONTENT_TYPES_BY_EXTENSION: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "avif": "image/avif",
    "bmp": "image/bmp",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "otf": "font/otf",
    "ttf": "font/ttf",
    "woff": "font/woff",
    "woff2": "font/woff2",
    "pdf": "application/pdf",
    "txt": "text/plain",
    "csv": "text/csv",
    "json": "application/json",
    "zip": "application/zip",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
    "ppt": "application/vnd.ms-powerpoint",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "avif", "bmp"}
VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}

WIKI_EMBED_PATTERN = re.compile(r"!\[\[([^\]\n]+)\]\]")
WIKI_LINK_PATTERN = re.compile(r"(?<!!)\[\[([^\]\n]+)\]\]")
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)")
HTML_MEDIA_SRC_PATTERN = re.compile(
    r"<(?:img|video|audio|source)\b[^>]*\bsrc\s*=\s*(?:\"([^\"\n]+)\"|'([^'\n]+)'|[^\s>]+)",
    flags=re.IGNORECASE,
)
HTML_ANCHOR_HREF_PATTERN = re.compile(
    r"<a\b[^>]*\bhref\s*=\s*(?:\"([^\"\n]+)\"|'([^'\n]+)'|[^\s>]+)",
    flags=re.IGNORECASE,
)


class AssetUploader(Protocol):
    def __call__(self, data: bytes, filename: str, content_type: str) -> str:
        """Upload one asset and return its server asset_id."""
        ...


@dataclass
class _Reference:
    family: str
    start: int
    end: int
    path: str
    alias: str | None = None
    value_start: int = 0
    value_end: int = 0


@dataclass
class PreparedAssets:
    markdown: str
    assets: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def asset_role_for_extension(extension: str) -> str:
    normalized = extension.lower()
    if normalized in IMAGE_EXTENSIONS:
        return "image"
    if normalized in VIDEO_EXTENSIONS:
        return "video"
    return "attachment"


def is_remote_reference(path: str) -> bool:
    return bool(re.match(r"^(?:https?:)?//", path, flags=re.IGNORECASE) or re.match(r"^(?:data|blob):", path, flags=re.IGNORECASE))


def _is_uploadable_path(path: str) -> bool:
    if not path:
        return False
    if is_remote_reference(path):
        return False
    if path.startswith(("obsidian://", "#", "mailto:", "tel:")):
        return False
    return True


def _masked_regions(markdown: str) -> list[tuple[int, int]]:
    regions: list[tuple[int, int]] = []
    offset = 0
    fence: str | None = None
    fence_indent = ""
    fence_start = 0
    for line in markdown.split("\n"):
        opener = re.match(r"^([ \t]*)(`{3,}|~{3,})", line)
        if fence is None and opener:
            fence = opener.group(2)[0] * 3
            fence_indent = opener.group(1)
            fence_start = offset
        elif fence is not None and opener and opener.group(1) == fence_indent and opener.group(2).startswith(fence):
            regions.append((fence_start, offset + len(line)))
            fence = None
        offset += len(line) + 1
    if fence is not None:
        regions.append((fence_start, len(markdown)))
    for match in re.finditer(r"`[^`\n]+`", markdown):
        regions.append((match.start(), match.end()))
    for match in re.finditer(r"<!--[\s\S]*?-->", markdown):
        regions.append((match.start(), match.end()))
    return regions


def _collect_references(markdown: str) -> list[_Reference]:
    regions = _masked_regions(markdown)
    references: list[_Reference] = []

    def masked(start: int) -> bool:
        return any(begin <= start < end for begin, end in regions)

    def split_wiki_target(raw: str) -> tuple[str, str | None]:
        parts = raw.split("|", 1)
        return parts[0].strip(), parts[1].strip() if len(parts) > 1 else None

    for match in WIKI_EMBED_PATTERN.finditer(markdown):
        path, alias = split_wiki_target(match.group(1))
        references.append(_Reference("wiki_embed", match.start(), match.end(), path, alias))
    for match in WIKI_LINK_PATTERN.finditer(markdown):
        path, alias = split_wiki_target(match.group(1))
        references.append(_Reference("wiki_link", match.start(), match.end(), path, alias))
    for pattern, family in (
        (MARKDOWN_IMAGE_PATTERN, "markdown_image"),
        (MARKDOWN_LINK_PATTERN, "markdown_link"),
    ):
        for match in pattern.finditer(markdown):
            raw = match.group(1)
            path = re.split(r"\s+[\"']", raw, maxsplit=1)[0].strip().strip("<>")
            references.append(
                _Reference(family, match.start(), match.end(), path, value_start=match.start(1), value_end=match.end(1))
            )
    for pattern, family in (
        (HTML_MEDIA_SRC_PATTERN, "html_src"),
        (HTML_ANCHOR_HREF_PATTERN, "html_href"),
    ):
        for match in pattern.finditer(markdown):
            # The value sits in group 1 (double-quoted), 2 (single-quoted) or
            # 3 (unquoted); only the participating group has a valid span.
            group_index = next(index for index in (1, 2, 3) if match.group(index) is not None)
            raw = match.group(group_index)
            references.append(
                _Reference(
                    family,
                    match.start(),
                    match.end(),
                    raw.strip(),
                    value_start=match.start(group_index),
                    value_end=match.end(group_index),
                )
            )

    return sorted(
        (reference for reference in references if not masked(reference.start) and _is_uploadable_path(reference.path)),
        key=lambda reference: reference.start,
    )


def _resolve_reference(path: str, workspace_root: Path, note_dir: Path) -> Path | None:
    cleaned = path.replace("\\", "/")
    candidate_parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not candidate_parts or any(part == ".." or part.startswith(".") for part in candidate_parts):
        return None
    for base in (note_dir, workspace_root):
        candidate = base.joinpath(*candidate_parts)
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_file() and resolved.is_relative_to(workspace_root):
            return resolved
    return None


def prepare_local_assets(
    markdown: str,
    workspace_root: Path,
    note_dir: Path,
    upload: AssetUploader,
) -> PreparedAssets:
    workspace_root = workspace_root.resolve()
    references = _collect_references(markdown)
    if not references:
        return PreparedAssets(markdown=markdown)

    asset_ids_by_path: dict[Path, str] = {}
    assets: list[dict[str, str]] = []
    warnings: list[str] = []
    replacements: list[tuple[int, int, str]] = []

    for reference in references:
        resolved = _resolve_reference(reference.path, workspace_root, note_dir)
        if resolved is None:
            warnings.append(f"not uploaded (missing or outside the workspace): {reference.path}")
            continue
        extension = resolved.suffix.lstrip(".").lower()
        content_type = CONTENT_TYPES_BY_EXTENSION.get(extension)
        if resolved.suffix.lower() == ".md" or content_type is None:
            warnings.append(f"not uploaded (unsupported type .{extension or 'unknown'}): {reference.path}")
            continue
        if resolved not in asset_ids_by_path:
            data = resolved.read_bytes()
            asset_id = upload(data, resolved.name, content_type)
            asset_ids_by_path[resolved] = asset_id
            assets.append(
                {
                    "asset_id": asset_id,
                    "role": asset_role_for_extension(extension),
                    "original_path": reference.path,
                }
            )
        asset_url = f"docferry-asset://{asset_ids_by_path[resolved]}"
        replacements.append(_replacement(reference, asset_url))

    for start, end, replacement in sorted(replacements, key=lambda item: item[0], reverse=True):
        markdown = markdown[:start] + replacement + markdown[end:]
    return PreparedAssets(markdown=markdown, assets=assets, warnings=warnings)


def _replacement(reference: _Reference, asset_url: str) -> tuple[int, int, str]:
    # Wiki syntax must be converted: the server renders raw wiki embeds as
    # "image unavailable" placeholders, so they become Markdown links toward
    # the uploaded asset instead.
    if reference.family in ("wiki_embed", "wiki_link"):
        label = reference.alias or Path(reference.path).stem
        prefix = "!" if reference.family == "wiki_embed" else ""
        return reference.start, reference.end, f"{prefix}[{label}]({asset_url})"
    return reference.value_start, reference.value_end, asset_url
