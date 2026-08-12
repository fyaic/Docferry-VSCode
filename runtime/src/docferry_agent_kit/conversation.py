from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal

MAX_CONVERSATION_MESSAGES = 200
MAX_CONVERSATION_BYTES = 256 * 1024
MAX_MESSAGE_BYTES = 64 * 1024
MAX_TITLE_LENGTH = 160
MAX_SUMMARY_LENGTH = 1_000
MAX_HIGHLIGHTS = 8
MAX_HIGHLIGHT_LENGTH = 280
MAX_TAGS = 12

ConversationRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationMessage:
    role: ConversationRole
    content: str


@dataclass(frozen=True)
class ConversationDraft:
    title: str
    markdown: str
    message_count: int
    redacted_value_count: int


@dataclass(frozen=True)
class ConversationDestination:
    workspace_kind: Literal["obsidian", "project"]
    relative_folder: str
    folder: Path


@dataclass(frozen=True)
class SavedConversation:
    title: str
    path: Path
    relative_path: str
    relative_folder: str
    workspace_kind: Literal["obsidian", "project"]
    message_count: int
    redacted_value_count: int


_PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----",
    flags=re.DOTALL,
)
_KNOWN_TOKEN_PATTERNS = (
    re.compile(r"\bsk-or-v1-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk-(?:proj|svcacct)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]{12,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)
_PREFIXED_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(\bAuthorization\s*:\s*Bearer\s+)[A-Za-z0-9._~+/=-]{12,}",
    ),
    re.compile(
        r"(?i)([?&](?:access_token|api_key|token|secret)=)[^&#\s]+",
    ),
    re.compile(
        r"(?im)(\b[A-Z][A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PASSWORD)"
        r"[A-Z0-9_]*\s*=\s*)[^\s#]{12,}",
    ),
)


def normalize_conversation_messages(values: object) -> tuple[list[ConversationMessage], int]:
    if not isinstance(values, list) or not values:
        raise ValueError("messages must be a non-empty list")
    if len(values) > MAX_CONVERSATION_MESSAGES:
        raise ValueError(f"Conversation supports at most {MAX_CONVERSATION_MESSAGES} messages.")

    messages: list[ConversationMessage] = []
    redacted_count = 0
    total_bytes = 0
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Message {index} must be an object with role and content.")
        role = item.get("role")
        if role not in {"user", "assistant"}:
            raise ValueError(
                f"Message {index} role must be user or assistant; system, developer, and tool messages are excluded."
            )
        raw_content = item.get("content")
        if not isinstance(raw_content, str):
            raise ValueError(f"Message {index} content must be text.")
        content = normalize_text(raw_content)
        if not content:
            continue
        message_bytes = len(content.encode("utf-8"))
        if message_bytes > MAX_MESSAGE_BYTES:
            raise ValueError(f"Message {index} exceeds the {MAX_MESSAGE_BYTES}-byte limit.")
        content, count = redact_sensitive_values(content)
        redacted_count += count
        total_bytes += message_bytes
        if total_bytes > MAX_CONVERSATION_BYTES:
            raise ValueError(f"Conversation exceeds the {MAX_CONVERSATION_BYTES}-byte limit.")
        messages.append(ConversationMessage(role=role, content=content))

    if not messages:
        raise ValueError("Conversation has no non-empty user or assistant messages.")
    return messages, redacted_count


def build_conversation_draft(
    values: object,
    *,
    title: str | None = None,
    agent_name: str | None = None,
    source_label: str | None = None,
    summary: str | None = None,
    highlights: list[str] | None = None,
    tags: list[str] | None = None,
    saved_at: datetime | None = None,
) -> ConversationDraft:
    messages, redacted_count = normalize_conversation_messages(values)
    timestamp = (saved_at or datetime.now().astimezone()).astimezone()
    resolved_title, title_redactions = normalize_title(title, messages, timestamp)
    redacted_count += title_redactions
    resolved_agent, agent_redactions = normalize_short_label(agent_name or "Assistant", "agent_name")
    redacted_count += agent_redactions
    resolved_source, source_redactions = normalize_short_label(
        source_label or resolved_agent,
        "source_label",
    )
    redacted_count += source_redactions
    resolved_summary, summary_redactions = normalize_optional_copy(
        summary,
        MAX_SUMMARY_LENGTH,
        "summary",
    )
    redacted_count += summary_redactions
    resolved_highlights, highlight_redactions = normalize_highlights(highlights)
    redacted_count += highlight_redactions
    resolved_tags, tag_redactions = normalize_tags(tags)
    redacted_count += tag_redactions

    lines = [
        "---",
        "docferry_conversation:",
        "  schema_version: 1",
        f"  source: {yaml_string(resolved_source)}",
        f"  agent: {yaml_string(resolved_agent)}",
        f"  saved_at: {yaml_string(timestamp.isoformat(timespec='seconds'))}",
        f"  message_count: {len(messages)}",
        f"  redacted_value_count: {redacted_count}",
        "tags:",
    ]
    lines.extend(f"  - {yaml_string(tag)}" for tag in resolved_tags)
    lines.extend(["---", "", f"# {markdown_heading_text(resolved_title)}", ""])

    overview = resolved_summary or "A saved conversation, kept as a readable note rather than a raw chat export."
    lines.extend(
        [
            "> [!abstract] Conversation",
            *quote_lines(overview),
            ">",
            *quote_lines(
                f"**Source:** {resolved_source} · **Messages:** {len(messages)} · "
                f"**Saved:** {timestamp.strftime('%Y-%m-%d %H:%M %Z').strip()}"
            ),
            "",
        ]
    )
    if redacted_count:
        lines.extend(
            [
                "> [!warning] Sensitive text omitted",
                *quote_lines(
                    f"DocFerry removed {redacted_count} value"
                    f"{'' if redacted_count == 1 else 's'} that looked like credentials before saving."
                ),
                "",
            ]
        )
    if resolved_highlights:
        lines.extend(["## What mattered", ""])
        lines.extend(f"- {item}" for item in resolved_highlights)
        lines.append("")

    lines.extend(["## Conversation", ""])
    for message in messages:
        label = "You" if message.role == "user" else resolved_agent
        lines.append(f"> [!{message.role}] {label}")
        lines.extend(quote_lines(message.content))
        lines.append("")

    return ConversationDraft(
        title=resolved_title,
        markdown="\n".join(lines).rstrip() + "\n",
        message_count=len(messages),
        redacted_value_count=redacted_count,
    )


def resolve_conversation_destination(
    root: Path,
    *,
    requested_folder: str | None = None,
    configured_folder: str | None = None,
) -> ConversationDestination:
    workspace_root = root.expanduser().resolve(strict=True)
    if not workspace_root.is_dir():
        raise ValueError("The configured DocFerry workspace is not a directory.")
    workspace_kind: Literal["obsidian", "project"] = (
        "obsidian" if (workspace_root / ".obsidian").is_dir() else "project"
    )
    folder_value = normalize_text(requested_folder or configured_folder or "")
    if not folder_value:
        if workspace_kind == "obsidian":
            folder_value = "DocFerry/Conversations"
        elif (workspace_root / "docs").is_dir():
            folder_value = "docs/conversations"
        else:
            folder_value = "conversations"

    relative = PurePosixPath(folder_value.replace("\\", "/"))
    if relative.as_posix() == ".":
        folder = workspace_root
        relative_folder = "."
    else:
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} or part.startswith(".") for part in relative.parts)
        ):
            raise ValueError("Conversation folder must be a visible relative path inside the workspace.")
        folder = (workspace_root / Path(*relative.parts)).resolve(strict=False)
        if not folder.is_relative_to(workspace_root):
            raise ValueError("Conversation folder escapes the configured workspace.")
        relative_folder = relative.as_posix()
    return ConversationDestination(
        workspace_kind=workspace_kind,
        relative_folder=relative_folder,
        folder=folder,
    )


def save_conversation(
    root: Path,
    values: object,
    *,
    requested_folder: str | None = None,
    configured_folder: str | None = None,
    title: str | None = None,
    agent_name: str | None = None,
    source_label: str | None = None,
    summary: str | None = None,
    highlights: list[str] | None = None,
    tags: list[str] | None = None,
    saved_at: datetime | None = None,
) -> SavedConversation:
    workspace_root = root.expanduser().resolve(strict=True)
    destination = resolve_conversation_destination(
        workspace_root,
        requested_folder=requested_folder,
        configured_folder=configured_folder,
    )
    timestamp = saved_at or datetime.now().astimezone()
    draft = build_conversation_draft(
        values,
        title=title,
        agent_name=agent_name,
        source_label=source_label,
        summary=summary,
        highlights=highlights,
        tags=tags,
        saved_at=timestamp,
    )
    destination.folder.mkdir(parents=True, exist_ok=True)
    filename = conversation_filename(draft.title, timestamp)
    path = write_unique_markdown(destination.folder, filename, draft.markdown)
    return SavedConversation(
        title=draft.title,
        path=path,
        relative_path=path.relative_to(workspace_root).as_posix(),
        relative_folder=destination.relative_folder,
        workspace_kind=destination.workspace_kind,
        message_count=draft.message_count,
        redacted_value_count=draft.redacted_value_count,
    )


def conversation_payload_from_json(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Conversation input must be valid JSON: {exc.msg}.") from exc
    if isinstance(parsed, list):
        return {"messages": parsed}
    if not isinstance(parsed, dict):
        raise ValueError("Conversation JSON must be a message list or an object containing messages.")
    return parsed


def nearest_obsidian_workspace(start: Path) -> Path | None:
    current = start.expanduser().resolve(strict=True)
    if not current.is_dir():
        return None
    for candidate in (current, *current.parents):
        if (candidate / ".obsidian").is_dir():
            return candidate
        if candidate == Path.home() or candidate.parent == candidate:
            break
    return None


def normalize_title(
    value: str | None,
    messages: list[ConversationMessage],
    timestamp: datetime,
) -> tuple[str, int]:
    candidate = normalize_text(value or "")
    if not candidate:
        first_user = next((item.content for item in messages if item.role == "user"), messages[0].content)
        candidate = first_meaningful_line(first_user)
    candidate, redacted_count = redact_sensitive_values(candidate)
    candidate = re.sub(r"^(?:#{1,6}|[-*+>])\s*", "", candidate)
    candidate = re.sub(r"\s+", " ", candidate).strip(" \t-:#")
    if "[redacted]" in candidate.lower() or not candidate:
        candidate = f"Conversation {timestamp.strftime('%Y-%m-%d')}"
    if len(candidate) > MAX_TITLE_LENGTH:
        candidate = candidate[: MAX_TITLE_LENGTH - 1].rstrip() + "…"
    return candidate, redacted_count


def normalize_short_label(value: str, label: str) -> tuple[str, int]:
    candidate = re.sub(r"\s+", " ", normalize_text(value)).strip()
    candidate, redacted_count = redact_sensitive_values(candidate)
    if not candidate:
        raise ValueError(f"{label} must not be empty")
    if len(candidate) > 80:
        raise ValueError(f"{label} must be at most 80 characters")
    return candidate, redacted_count


def normalize_optional_copy(value: str | None, limit: int, label: str) -> tuple[str | None, int]:
    if value is None:
        return None, 0
    candidate = normalize_text(value)
    if not candidate:
        return None, 0
    if len(candidate) > limit:
        raise ValueError(f"{label} must be at most {limit} characters")
    return redact_sensitive_values(candidate)


def normalize_highlights(values: list[str] | None) -> tuple[list[str], int]:
    if not values:
        return [], 0
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError("highlights must be a list of text values")
    if len(values) > MAX_HIGHLIGHTS:
        raise ValueError(f"highlights supports at most {MAX_HIGHLIGHTS} items")
    normalized: list[str] = []
    redacted_count = 0
    for value in values:
        item = re.sub(r"\s+", " ", normalize_text(value)).strip()
        if not item:
            continue
        if len(item) > MAX_HIGHLIGHT_LENGTH:
            raise ValueError(f"Each highlight must be at most {MAX_HIGHLIGHT_LENGTH} characters")
        item, count = redact_sensitive_values(item)
        redacted_count += count
        normalized.append(item)
    return normalized, redacted_count


def normalize_tags(values: list[str] | None) -> tuple[list[str], int]:
    if values is not None and (
        not isinstance(values, list) or any(not isinstance(value, str) for value in values)
    ):
        raise ValueError("tags must be a list of text values")
    tags = ["docferry/conversation"]
    redacted_count = 0
    for raw in values or []:
        candidate = normalize_text(raw).strip().lstrip("#")
        if not candidate:
            continue
        candidate, count = redact_sensitive_values(candidate)
        redacted_count += count
        if count:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_\-/\u0080-\uffff]{1,64}", candidate):
            raise ValueError("Tags may contain letters, numbers, Unicode text, slash, underscore, or hyphen.")
        if candidate not in tags:
            tags.append(candidate)
    if len(tags) > MAX_TAGS:
        raise ValueError(f"tags supports at most {MAX_TAGS} items including docferry/conversation")
    return tags, redacted_count


def redact_sensitive_values(value: str) -> tuple[str, int]:
    updated = value
    count = 0

    def replace_secret(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[redacted]"

    def replace_prefixed(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return f"{match.group(1)}[redacted]"

    updated = _PRIVATE_KEY_PATTERN.sub(replace_secret, updated)
    for pattern in _KNOWN_TOKEN_PATTERNS:
        updated = pattern.sub(replace_secret, updated)
    for pattern in _PREFIXED_SECRET_PATTERNS:
        updated = pattern.sub(replace_prefixed, updated)
    return updated, count


def normalize_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        character
        for character in normalized
        if character in {"\n", "\t"} or (ord(character) >= 32 and ord(character) != 127)
    )
    return normalized.strip()


def first_meaningful_line(value: str) -> str:
    for line in value.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate
    return ""


def quote_lines(value: str) -> list[str]:
    return [">" if not line else f"> {line}" for line in value.splitlines()]


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def markdown_heading_text(value: str) -> str:
    return re.sub(r"([\\`*_[\]<>])", r"\\\1", value)


def conversation_filename(title: str, saved_at: datetime) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', " ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if not stem:
        stem = "Conversation"
    stem = truncate_utf8(stem, 180).rstrip()
    return f"{saved_at.strftime('%Y-%m-%d')} - {stem}.md"


def truncate_utf8(value: str, max_bytes: int) -> str:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def write_unique_markdown(folder: Path, filename: str, markdown: str) -> Path:
    suffix = 2
    stem = Path(filename).stem
    candidate = folder / filename
    while True:
        try:
            with candidate.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(markdown)
            return candidate
        except FileExistsError:
            candidate = folder / f"{stem} {suffix}.md"
            suffix += 1
