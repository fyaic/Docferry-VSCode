#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import secrets
import socketserver
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from pathlib import PurePosixPath
from threading import Event, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

from .conversation import (
    conversation_payload_from_json,
    nearest_obsidian_workspace,
    resolve_conversation_destination,
    save_conversation,
)

DEFAULT_SERVER_URL = "https://docferry.bondie.io"
OFFICIAL_SANDBOX_SERVER_URL = "https://sandbox-docferry.bondie.io"
PERSISTED_SERVER_URLS = frozenset({DEFAULT_SERVER_URL, OFFICIAL_SANDBOX_SERVER_URL})
DOCFERRY_CLI_VERSION = "0.4.3"
DEVICE_LOGIN_MAX_TRANSIENT_FAILURES = 5
DEVICE_LOGIN_MAX_RETRY_SECONDS = 15
MANDATORY_ADVANCED_IMPORT_PROVIDERS = frozenset({"bilibili", "tiktok", "douyin"})
CONFIG_ENV = "DOCFERRY_CONFIG"
TOKEN_ENV_VARS = ("DOCFERRY_SESSION_TOKEN", "DOCFERRY_TOKEN")
PKCE_CODE_CHALLENGE_METHOD = "S256"
DASHBOARD_TARGET_PATHS = {
    "home": "/dashboard",
    "membership": "/dashboard/billing?refresh_membership=1",
    "plans": "/dashboard/plans?refresh_membership=1",
    "shares": "/dashboard/shares",
    "support": "/dashboard/support",
    "account": "/dashboard/account",
}
FRIENDLY_HELP = """DocFerry

Save conversations and move useful content into or out of your workspace.

  docferry login                     Connect your Bondie account
  docferry status                    Show connection, plan, and limits
  docferry save [chat.json|-]        Save the latest Agent exchange privately
  docferry share [source]            Share the latest exchange or a workspace path
  docferry import <url>              Save a shared document or public link
  docferry history                   View active and stopped shares
  docferry unshare <id> --confirm    Stop one exact public share
  docferry delete-history <id> --confirm
                                     Remove one stopped history record
  docferry help                      Show this guide

Inside an Agent, save/share with no argument use the latest completed exchange.
In a terminal, pass conversation JSON or stdin; share auto-detects Markdown files
and folders. share-file and share-folder remain available as explicit aliases.
Every public share and unshare requires confirmation.
"""


@dataclass
class Response:
    status_code: int
    text: str

    def json(self) -> dict[str, object]:
        return json.loads(self.text) if self.text else {}


@dataclass
class BinaryResponse:
    status_code: int
    body: bytes


@dataclass
class CliConfig:
    server_url: str | None = None
    session_token: str | None = None
    session_expires_at: str | None = None
    client_instance_id: str | None = None
    pending_code_verifier: str | None = None

    @classmethod
    def from_json(cls, value: object) -> "CliConfig":
        if not isinstance(value, dict):
            raise CliError("Invalid DocFerry config file.")
        return cls(
            server_url=string_or_none(value.get("server_url")),
            session_token=string_or_none(value.get("session_token")),
            session_expires_at=string_or_none(value.get("session_expires_at")),
            client_instance_id=string_or_none(value.get("client_instance_id")),
            pending_code_verifier=string_or_none(value.get("pending_code_verifier")),
        )

    def to_json(self) -> dict[str, str]:
        body: dict[str, str] = {}
        if self.server_url:
            body["server_url"] = self.server_url
        if self.session_token:
            body["session_token"] = self.session_token
        if self.session_expires_at:
            body["session_expires_at"] = self.session_expires_at
        if self.client_instance_id:
            body["client_instance_id"] = self.client_instance_id
        if self.pending_code_verifier:
            body["pending_code_verifier"] = self.pending_code_verifier
        return body


class Client:
    def __init__(self, base_url: str, token: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()), ProxyHandler({}))

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, object] | None = None,
        auth: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> Response:
        data = None
        headers = {"User-Agent": f"DocFerryCLI/{DOCFERRY_CLI_VERSION}"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if auth:
            if not self.token:
                raise CliError("No DocFerry session. Run `docferry login` first.")
            headers["Authorization"] = f"Bearer {self.token}"
        if extra_headers:
            headers.update(extra_headers)
        request = Request(urljoin(f"{self.base_url}/", path.lstrip("/")), data=data, headers=headers, method=method)
        try:
            response = self.opener.open(request, timeout=20)
            return Response(response.status, response.read().decode("utf-8"))
        except HTTPError as exc:
            return Response(exc.code, exc.read().decode("utf-8"))

    def get(self, path: str, *, auth: bool = False) -> Response:
        return self.request("GET", path, auth=auth)

    def get_bytes(self, path_or_url: str) -> BinaryResponse:
        parsed = urlparse(path_or_url)
        url = path_or_url if parsed.scheme and parsed.netloc else urljoin(f"{self.base_url}/", path_or_url.lstrip("/"))
        request = Request(url, headers={"User-Agent": f"DocFerryCLI/{DOCFERRY_CLI_VERSION}"}, method="GET")
        try:
            response = self.opener.open(request, timeout=30)
            return BinaryResponse(response.status, response.read())
        except HTTPError as exc:
            return BinaryResponse(exc.code, exc.read())

    def post(
        self,
        path: str,
        *,
        body: dict[str, object] | None = None,
        auth: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> Response:
        return self.request("POST", path, body=body, auth=auth, extra_headers=extra_headers)

    def put(self, path: str, *, body: dict[str, object], auth: bool = False) -> Response:
        return self.request("PUT", path, body=body, auth=auth)

    def delete(self, path: str, *, auth: bool = False) -> Response:
        return self.request("DELETE", path, auth=auth)


class CliError(Exception):
    pass


def add_conversation_input_arguments(
    command: argparse.ArgumentParser,
    *,
    command_name: str,
) -> None:
    command.add_argument(
        "input",
        nargs="?",
        default="-",
        help=(
            "Conversation JSON/stdin, or a Markdown file/folder path."
            if command_name == "share"
            else "JSON file containing messages, or - for stdin."
        ),
    )
    command.add_argument("--title")
    command.add_argument("--agent-name")
    command.add_argument("--source")
    command.add_argument("--summary")
    command.add_argument("--highlight", action="append")
    command.add_argument("--tag", action="append")
    command.add_argument("--output-folder")
    if command_name == "share":
        command.add_argument("--password")
        command.add_argument("--expires-at")
        command.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm that the saved Markdown may be uploaded and shared.",
        )


def add_note_publish_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("file")
    command.add_argument("--title")
    command.add_argument("--source-path")
    command.add_argument("--password")
    command.add_argument("--expires-at")


def add_folder_publish_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("folder")
    command.add_argument("--folder-share-id")
    command.add_argument("--title")
    command.add_argument("--password")
    command.add_argument("--clear-password", action="store_true")
    command.add_argument("--expires-at")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Docferry command line client.",
        add_help=False,
    )
    parser.add_argument(
        "-h",
        "--help",
        dest="show_help",
        action="store_true",
        help="Show the user-facing DocFerry command guide.",
    )
    parser.add_argument("--server-url", default=None, help=f"DocFerry server URL. Default: {DEFAULT_SERVER_URL}")
    parser.add_argument("--config", default=os.getenv(CONFIG_ENV), help="Config file path. Default: ~/.config/docferry/config.json")
    parser.add_argument(
        "--workspace",
        default=os.getenv("DOCFERRY_WORKSPACE_PATH"),
        help="Project or Obsidian vault root for folder and import commands. Default: current directory.",
    )
    parser.add_argument("--version", action="version", version=f"docferry {DOCFERRY_CLI_VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("health")
    subparsers.add_parser("help", help="Show the user-facing DocFerry command guide.")

    login = subparsers.add_parser("login")
    login_mode = login.add_mutually_exclusive_group()
    login_mode.add_argument("--device-code", action="store_true", help="Use Device Code login. This is the default.")
    login_mode.add_argument("--loopback", action="store_true", help="Use localhost callback login with PKCE.")
    login_mode.add_argument(
        "--manual-callback",
        action="store_true",
        help="Print a PKCE login URL and prompt for the final callback URL.",
    )
    login_mode.add_argument(
        "--callback-url",
        default=os.getenv("DOCFERRY_CALLBACK_URL"),
        help="Complete a previously started manual callback login.",
    )
    login_mode.add_argument(
        "--from-obsidian",
        metavar="PATH",
        help="Import and validate the session from an Obsidian vault or DocFerry data.json.",
    )
    login.add_argument(
        "--client",
        choices=("cli", "vscode"),
        default="cli",
        help="Login client surface. VS Code uses the product-owned completion page and local PKCE callback.",
    )
    login.add_argument("--no-browser", action="store_true", help="Print the login URL without opening a browser.")
    login.add_argument("--timeout", type=int, default=300, help="Seconds to wait for login approval.")

    logout = subparsers.add_parser("logout")
    logout.add_argument("--local-only", action="store_true", help="Only remove the local DocFerry session.")

    auth = subparsers.add_parser("auth")
    auth_subparsers = auth.add_subparsers(dest="auth_command", required=True)
    auth_subparsers.add_parser("status")

    subparsers.add_parser("whoami")
    subparsers.add_parser("membership")

    dashboard = subparsers.add_parser("dashboard", help="Open the signed-in DocFerry product dashboard.")
    dashboard.add_argument(
        "--section",
        choices=tuple(DASHBOARD_TARGET_PATHS),
        default="home",
        help="DocFerry dashboard section. Account is the product's Account & privacy page.",
    )
    dashboard.add_argument(
        "--no-browser",
        action="store_true",
        help="Return a short-lived DocFerry dashboard URL instead of opening the system browser.",
    )

    list_shares = subparsers.add_parser("list")
    list_shares.add_argument("--limit", type=int, default=50)

    publish = subparsers.add_parser("publish")
    add_note_publish_arguments(publish)

    share_file = subparsers.add_parser(
        "share-file",
        help="Share one Markdown file from the configured workspace.",
    )
    add_note_publish_arguments(share_file)

    share_folder = subparsers.add_parser(
        "share-folder",
        help="Share one visible Markdown folder with Pro access.",
    )
    share_folder.set_defaults(folder_command="publish")
    add_folder_publish_arguments(share_folder)

    history = subparsers.add_parser(
        "history",
        help="List note and folder sharing history.",
    )
    history.add_argument("--limit", type=int, default=50)

    unshare = subparsers.add_parser(
        "unshare",
        help="Stop one note or folder share by ID.",
    )
    unshare.add_argument("share_id")
    unshare.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that this public share should stop working.",
    )

    delete_history = subparsers.add_parser(
        "delete-history",
        help="Permanently remove one stopped note or folder share from history.",
    )
    delete_history.add_argument("share_id")
    delete_history.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm permanent removal of this stopped history record.",
    )

    update = subparsers.add_parser("update")
    update.add_argument("share_id")
    update.add_argument("file")
    update.add_argument("--title")
    update.add_argument("--source-path")
    update.add_argument("--password")
    update.add_argument("--password-mode", choices=["keep", "set", "clear"], default="keep")
    update.add_argument("--expires-at")

    status = subparsers.add_parser(
        "status",
        help="Show account and plan status, or inspect one share by ID.",
    )
    status.add_argument("share_id", nargs="?")

    events = subparsers.add_parser("events")
    events.add_argument("share_id")
    events.add_argument("--limit", type=int, default=50)

    links = subparsers.add_parser("links")
    links.add_argument("share_id")

    revoke = subparsers.add_parser("revoke")
    revoke.add_argument("share_id")

    import_url = subparsers.add_parser("import-url")
    import_url.add_argument("url")
    import_url.add_argument("--output", required=True)
    import_url.add_argument("--password")
    import_url.add_argument("--overwrite", action="store_true")

    save_to_workspace = subparsers.add_parser("import")
    save_to_workspace.add_argument("url")
    save_to_workspace.add_argument("--output", required=True)
    save_to_workspace.add_argument("--password")
    save_to_workspace.add_argument("--overwrite", action="store_true")
    save_to_workspace.add_argument(
        "--advanced",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    save_to_workspace.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm that the external URL may be fetched and processed by DocFerry.",
    )
    save_to_workspace.add_argument("--timeout", type=int, default=300)
    save_to_workspace.add_argument("--poll-interval", type=float, default=2.0)

    folder = subparsers.add_parser("folder")
    folder_commands = folder.add_subparsers(dest="folder_command", required=True)
    folder_publish = folder_commands.add_parser("publish")
    add_folder_publish_arguments(folder_publish)
    folder_commands.add_parser("list")
    folder_status = folder_commands.add_parser("status")
    folder_status.add_argument("folder_share_id")
    folder_revoke = folder_commands.add_parser("revoke")
    folder_revoke.add_argument("folder_share_id")
    folder_revoke.add_argument("--confirm", action="store_true")

    media_note = subparsers.add_parser("media-note")
    media_note_commands = media_note.add_subparsers(dest="media_note_command", required=True)
    media_note_create = media_note_commands.add_parser("create")
    media_note_create.add_argument("url")
    media_note_create.add_argument("--idempotency-key")
    media_note_status = media_note_commands.add_parser("status")
    media_note_status.add_argument("job_id")
    media_note_cancel = media_note_commands.add_parser("cancel")
    media_note_cancel.add_argument("job_id")
    media_note_cancel.add_argument("--confirm", action="store_true")
    media_note_save = media_note_commands.add_parser("save")
    media_note_save.add_argument("job_id")
    media_note_save.add_argument("--output", required=True)
    media_note_save.add_argument("--confirm", action="store_true")
    media_note_save.add_argument("--overwrite", action="store_true")
    media_note_wait = media_note_commands.add_parser("wait")
    media_note_wait.add_argument("job_id")
    media_note_wait.add_argument("--timeout", type=int, default=300)
    media_note_wait.add_argument("--poll-interval", type=float, default=2.0)

    conversation = subparsers.add_parser(
        "conversation",
        help="Save a readable Agent conversation locally, then optionally share it.",
    )
    conversation_commands = conversation.add_subparsers(dest="conversation_command", required=True)
    conversation_destination = conversation_commands.add_parser(
        "destination",
        help="Show where DocFerry will save conversations in this workspace.",
    )
    conversation_destination.add_argument("--output-folder")
    for command_name in ("save", "share"):
        command = conversation_commands.add_parser(
            command_name,
            help=(
                "Save a conversation as Markdown."
                if command_name == "save"
                else "Save and publish a conversation after explicit confirmation."
            ),
        )
        add_conversation_input_arguments(command, command_name=command_name)

    for command_name in ("save", "share"):
        command = subparsers.add_parser(
            command_name,
            help=(
                "Save an Agent conversation as Markdown."
                if command_name == "save"
                else "Save and publish an Agent conversation after explicit confirmation."
            ),
        )
        command.set_defaults(conversation_command=command_name)
        add_conversation_input_arguments(command, command_name=command_name)

    args = parser.parse_args()

    if args.show_help or args.command is None or args.command == "help":
        print(FRIENDLY_HELP.rstrip())
        return 0

    try:
        config_path = config_path_from_arg(args.config)
        config = load_config(config_path)
        server_url = resolve_server_url(args, config)
        migrate_stale_persisted_server(
            config,
            config_path,
            explicit_server=bool(args.server_url or os.getenv("DOCFERRY_SERVER_URL")),
        )
        token = resolve_token(config, server_url)
        client = Client(server_url, token)
        if args.command == "health":
            print_json(require_ok(client.get("/v0/health"), "health").json())
        elif args.command == "login":
            login_command(client, args, config, config_path, server_url)
        elif args.command == "logout":
            logout_command(client, args, config, config_path, token)
        elif args.command == "auth" and args.auth_command == "status":
            auth_status_command(client, token)
        elif args.command == "whoami":
            auth_status_command(client, token)
        elif args.command == "membership":
            print_json(membership_summary(client))
        elif args.command == "dashboard":
            print_json(dashboard_command(client, args))
        elif args.command == "list":
            print_json(list_share_summary(client, args.limit))
        elif args.command == "history":
            print_json(share_history_summary(client, args.limit))
        elif args.command in {"publish", "share-file"}:
            print_json(require_ok(client.post("/v0/shares", body=share_payload(args), auth=True), "publish").json())
        elif args.command == "share-folder":
            print_json(publish_folder(client, args))
        elif args.command == "update":
            share_id = normalized_share_id(args.share_id)
            print_json(
                require_ok(
                    client.put(f"/v0/shares/{share_id}", body=share_payload(args, is_update=True), auth=True),
                    "update",
                ).json()
            )
        elif args.command == "status":
            if args.share_id:
                share_id = normalized_share_id(args.share_id)
                print_json(require_ok(client.get(f"/v0/shares/{share_id}", auth=True), "status").json())
            else:
                print_json(account_status_summary(client, token))
        elif args.command == "events":
            share_id = normalized_share_id(args.share_id)
            print_json(
                require_ok(client.get(f"/v0/shares/{share_id}/events?limit={args.limit}", auth=True), "events").json()
            )
        elif args.command == "links":
            share_id = normalized_share_id(args.share_id)
            print_json(require_ok(client.get(f"/v0/shares/{share_id}/links", auth=True), "links").json())
        elif args.command == "revoke":
            share_id = normalized_share_id(args.share_id)
            print_json(require_ok(client.delete(f"/v0/shares/{share_id}", auth=True), "revoke").json())
        elif args.command == "unshare":
            print_json(unshare_command(client, args))
        elif args.command == "delete-history":
            print_json(delete_history_command(client, args))
        elif args.command == "import-url":
            print_json(import_share(args, expected_server_url=client.base_url))
        elif args.command == "import":
            print_json(import_command(client, args))
        elif args.command == "folder":
            print_json(folder_command(client, args))
        elif args.command == "media-note":
            print_json(media_note_command(client, args))
        elif args.command in {"conversation", "save"}:
            print_json(conversation_command(client, args))
        elif args.command == "share":
            print_json(share_command(client, args))
        else:
            raise CliError(f"Unsupported command: {args.command}")
    except CliError as exc:
        print(f"docferry: {exc}", file=sys.stderr)
        return 1
    return 0


def media_note_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    command = args.media_note_command
    if command == "create":
        parsed = validated_public_url(args.url)
        ensure_media_note_available(client, parsed)
        idempotency_key = normalized_media_note_idempotency_key(args.idempotency_key)
        return require_ok(
            client.post(
                "/v0/media-note/jobs",
                body={"source_url": parsed, "output_language": "source"},
                auth=True,
                extra_headers={"Idempotency-Key": idempotency_key},
            ),
            "create Advanced Import",
        ).json()
    job_id = normalized_media_note_job_id(args.job_id)
    if command == "status":
        return require_ok(client.get(f"/v0/media-note/jobs/{job_id}", auth=True), "Advanced Import status").json()
    if command == "wait":
        return wait_for_media_note(
            client,
            job_id,
            timeout_seconds=args.timeout,
            poll_interval=args.poll_interval,
        )
    if command == "cancel":
        if not args.confirm:
            raise CliError("media-note cancel requires --confirm")
        return require_ok(
            client.post(f"/v0/media-note/jobs/{job_id}/cancel", body={}, auth=True),
            "cancel Advanced Import",
        ).json()
    if command == "save":
        if not args.confirm:
            raise CliError("media-note save requires --confirm")
        body = require_ok(
            client.get(f"/v0/media-note/jobs/{job_id}", auth=True),
            "Advanced Import status",
        ).json()
        if body.get("status") not in {"extracted", "degraded"}:
            raise CliError("Advanced Import is not ready to save.")
        return save_media_note_result(body, Path(args.output), overwrite=args.overwrite)
    raise CliError(f"Unsupported media-note command: {command}")


def conversation_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    root = conversation_workspace_root(args.workspace)
    requested_folder = getattr(args, "output_folder", None)
    configured_folder = os.getenv("DOCFERRY_CONVERSATION_DIR")
    if args.conversation_command == "destination":
        try:
            destination = resolve_conversation_destination(
                root,
                requested_folder=requested_folder,
                configured_folder=configured_folder,
            )
        except ValueError as exc:
            raise CliError(str(exc)) from exc
        return {
            "workspace_kind": destination.workspace_kind,
            "folder": destination.relative_folder,
            "exists": destination.folder.is_dir(),
            "network_requested": False,
        }

    if args.conversation_command == "share" and not args.confirm:
        raise CliError("conversation share requires --confirm before uploading the saved Markdown")

    payload = read_conversation_payload(args.input)
    try:
        saved = save_conversation(
            root,
            payload.get("messages"),
            requested_folder=requested_folder,
            configured_folder=configured_folder,
            title=conversation_text_option(args.title, payload, "title"),
            agent_name=conversation_text_option(args.agent_name, payload, "agent_name"),
            source_label=conversation_text_option(args.source, payload, "source"),
            summary=conversation_text_option(args.summary, payload, "summary"),
            highlights=conversation_list_option(args.highlight, payload, "highlights"),
            tags=conversation_list_option(args.tag, payload, "tags"),
        )
    except ValueError as exc:
        raise CliError(str(exc)) from exc

    local_result: dict[str, object] = {
        "saved": True,
        "title": saved.title,
        "path": saved.relative_path,
        "workspace_kind": saved.workspace_kind,
        "message_count": saved.message_count,
        "redacted_value_count": saved.redacted_value_count,
    }
    if args.conversation_command == "save":
        local_result["published"] = False
        local_result["network_requested"] = False
        return local_result

    share_args = argparse.Namespace(
        workspace=str(root),
        file=saved.relative_path,
        title=saved.title,
        source_path=saved.relative_path,
        password=args.password,
        expires_at=args.expires_at,
    )
    response = require_ok(
        client.post("/v0/shares", body=share_payload(share_args), auth=True),
        "share conversation",
    ).json()
    return {
        **local_result,
        "published": True,
        "share_id": response.get("share_id"),
        "url": response.get("url"),
    }


def share_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    source_kind = share_source_kind(args.workspace, args.input)
    if source_kind == "conversation":
        return conversation_command(client, args)
    if not args.confirm:
        raise CliError("share requires --confirm before publishing the selected workspace path")
    if source_kind == "file":
        share_args = argparse.Namespace(
            workspace=args.workspace,
            file=args.input,
            title=args.title,
            source_path=None,
            password=args.password,
            expires_at=args.expires_at,
        )
        return require_ok(
            client.post(
                "/v0/shares",
                body=share_payload(share_args),
                auth=True,
            ),
            "share file",
        ).json()
    folder_args = argparse.Namespace(
        workspace=args.workspace,
        folder=args.input,
        folder_share_id=None,
        title=args.title,
        password=args.password,
        clear_password=False,
        expires_at=args.expires_at,
    )
    return publish_folder(client, folder_args)


def share_source_kind(workspace: str | None, value: str) -> str:
    if value == "-":
        return "conversation"
    root = conversation_workspace_root(workspace)
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return "conversation"
    if resolved.is_dir():
        return "folder"
    if resolved.is_file() and resolved.suffix.lower() == ".md":
        return "file"
    return "conversation"


def conversation_workspace_root(value: str | None) -> Path:
    if value:
        return cli_workspace_root(value)
    current = Path.cwd().resolve(strict=True)
    return nearest_obsidian_workspace(current) or current


def read_conversation_payload(value: str) -> dict[str, object]:
    max_input_bytes = 512 * 1024
    try:
        if value == "-":
            raw = sys.stdin.read(max_input_bytes + 1)
        else:
            input_path = Path(value).expanduser().resolve(strict=True)
            if not input_path.is_file():
                raise CliError(f"Conversation input is not a file: {value}")
            if input_path.stat().st_size > max_input_bytes:
                raise CliError(f"Conversation input exceeds the {max_input_bytes}-byte limit.")
            raw = input_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CliError(f"Could not read conversation input: {value}") from exc
    if len(raw.encode("utf-8")) > max_input_bytes:
        raise CliError(f"Conversation input exceeds the {max_input_bytes}-byte limit.")
    try:
        return conversation_payload_from_json(raw)
    except ValueError as exc:
        raise CliError(str(exc)) from exc


def conversation_text_option(
    explicit: str | None,
    payload: dict[str, object],
    key: str,
) -> str | None:
    if explicit is not None:
        return explicit
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliError(f"{key} must be text")
    return value


def conversation_list_option(
    explicit: list[str] | None,
    payload: dict[str, object],
    key: str,
) -> list[str] | None:
    if explicit is not None:
        return explicit
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise CliError(f"{key} must be a list of text values")
    return value


def membership_summary(client: Client) -> dict[str, object]:
    body = require_ok(client.get("/v0/membership", auth=True), "membership").json()
    media = body.get("media_note") if isinstance(body.get("media_note"), dict) else {}
    media_usage = body.get("media_note_usage") if isinstance(body.get("media_note_usage"), dict) else {}
    return {
        "access_role": body.get("access_role") or "member",
        "plan_key": body.get("plan_key"),
        "plan_display_name": body.get("plan_display_name"),
        "active_share_count": body.get("active_share_count"),
        "active_share_limit": body.get("active_share_limit"),
        "share_limit_unlimited": body.get("share_limit_unlimited") is True,
        "active_folder_share_count": body.get("active_folder_share_count"),
        "active_folder_share_limit": body.get("active_folder_share_limit"),
        "folder_share_limit_unlimited": body.get("folder_share_limit_unlimited") is True,
        "max_single_file_size_bytes": body.get("max_single_file_size_bytes"),
        "max_folder_document_count": body.get("max_folder_document_count"),
        "max_folder_total_bytes": body.get("max_folder_total_bytes"),
        "feature_gates": body.get("feature_gates") if isinstance(body.get("feature_gates"), dict) else {},
        "media_note": {
            "enabled": media.get("enabled") is True,
            "supported_providers": media.get("supported_providers") or [],
        },
        "media_note_usage": {
            "active_jobs": media_usage.get("active_jobs") or 0,
            "active_job_limit": media_usage.get("active_job_limit"),
            "monthly_jobs_used": media_usage.get("monthly_jobs_used") or 0,
            "monthly_job_limit": media_usage.get("monthly_job_limit"),
            "resets_at": media_usage.get("resets_at"),
        },
    }


def dashboard_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    target_path = DASHBOARD_TARGET_PATHS[args.section]
    body = require_ok(
        client.post(
            "/v0/auth/dashboard-link",
            body={"target_path": target_path},
            auth=True,
        ),
        "dashboard",
    ).json()
    dashboard_url = validated_dashboard_handoff_url(client.base_url, body.get("dashboard_url"))
    opened = False
    if not args.no_browser:
        opened = bool(webbrowser.open(dashboard_url, new=2))
    result: dict[str, object] = {
        "opened": opened,
        "section": args.section,
        "target_path": target_path,
    }
    if args.no_browser or not opened:
        result["dashboard_url"] = dashboard_url
    return result


def validated_dashboard_handoff_url(server_url: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CliError("DocFerry did not return a dashboard link.")
    try:
        server = urlparse(server_url)
        candidate = urlparse(value.strip())
        server_port = server.port or (443 if server.scheme == "https" else 80)
        candidate_port = candidate.port or (443 if candidate.scheme == "https" else 80)
    except ValueError as exc:
        raise CliError("DocFerry returned an invalid dashboard link.") from exc
    same_origin = (
        candidate.scheme == server.scheme
        and candidate.hostname == server.hostname
        and candidate_port == server_port
    )
    query = parse_qs(candidate.query, keep_blank_values=True)
    valid_code = set(query) == {"code"} and len(query["code"]) == 1 and bool(query["code"][0])
    if (
        not same_origin
        or candidate.username is not None
        or candidate.password is not None
        or candidate.path != "/v0/auth/dashboard-open"
        or candidate.fragment
        or not valid_code
    ):
        raise CliError("DocFerry returned an untrusted dashboard link.")
    return value.strip()


def list_share_summary(client: Client, limit: int) -> dict[str, object]:
    bounded = max(1, min(limit, 100))
    body = require_ok(client.get(f"/v0/shares?limit={bounded}", auth=True), "list shares").json()
    return {
        "shares": body.get("shares") if isinstance(body.get("shares"), list) else [],
        "total": body.get("total"),
    }


def share_history_summary(client: Client, limit: int) -> dict[str, object]:
    note_history = list_share_summary(client, limit)
    membership = membership_summary(client)
    feature_gates = membership.get("feature_gates")
    folder_enabled = (
        isinstance(feature_gates, dict)
        and feature_gates.get("docferry.publish.folder") is True
    )
    folder_shares: list[object] = []
    folder_total = 0
    if folder_enabled:
        body = require_ok(
            client.get("/v0/folder-shares", auth=True),
            "list folder shares",
        ).json()
        folder_shares = (
            body.get("folder_shares")
            if isinstance(body.get("folder_shares"), list)
            else []
        )
        folder_total = int(body.get("total") or len(folder_shares))
    note_shares = (
        note_history.get("shares")
        if isinstance(note_history.get("shares"), list)
        else []
    )
    note_total = int(note_history.get("total") or len(note_shares))
    return {
        "note_shares": note_shares,
        "folder_shares": folder_shares,
        "total": note_total + folder_total,
        "folder_history_available": folder_enabled,
    }


def unshare_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    if not args.confirm:
        raise CliError("unshare requires --confirm after reviewing the exact share")
    candidate = args.share_id.strip()
    if candidate.startswith("fsh_"):
        share_id = normalized_folder_share_id(candidate)
        result = require_ok(
            client.delete(f"/v0/folder-shares/{share_id}", auth=True),
            "unshare folder",
        ).json()
        return {**result, "share_type": "folder"}
    share_id = normalized_share_id(candidate)
    result = require_ok(
        client.delete(f"/v0/shares/{share_id}", auth=True),
        "unshare note",
    ).json()
    return {**result, "share_type": "note"}


def delete_history_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    if not args.confirm:
        raise CliError("delete-history requires --confirm after reviewing the stopped share")
    candidate = args.share_id.strip()
    if candidate.startswith("fsh_"):
        share_id = normalized_folder_share_id(candidate)
        result = require_ok(
            client.delete(f"/v0/folder-shares/{share_id}/record", auth=True),
            "delete folder share history",
        ).json()
        return {**result, "deleted": True, "share_type": "folder"}
    share_id = normalized_share_id(candidate)
    result = require_ok(
        client.delete(f"/v0/shares/{share_id}/record", auth=True),
        "delete share history",
    ).json()
    return {**result, "deleted": True, "share_type": "note"}


def folder_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    if args.folder_command == "list":
        return require_ok(client.get("/v0/folder-shares", auth=True), "list folder shares").json()
    if args.folder_command == "status":
        folder_share_id = normalized_folder_share_id(args.folder_share_id)
        return require_ok(
            client.get(f"/v0/folder-shares/{folder_share_id}", auth=True),
            "folder share status",
        ).json()
    if args.folder_command == "revoke":
        folder_share_id = normalized_folder_share_id(args.folder_share_id)
        if not args.confirm:
            raise CliError("folder revoke requires --confirm")
        return require_ok(
            client.delete(f"/v0/folder-shares/{folder_share_id}", auth=True),
            "revoke folder share",
        ).json()
    return publish_folder(client, args)


def publish_folder(client: Client, args: argparse.Namespace) -> dict[str, object]:
    if args.password and args.clear_password:
        raise CliError("--password and --clear-password cannot be used together")
    root = cli_workspace_root(args.workspace)
    folder, source_folder, documents = cli_folder_documents(root, args.folder)
    if not documents:
        raise CliError("The selected folder contains no visible Markdown files.")
    membership = require_ok(client.get("/v0/membership", auth=True), "membership").json()
    feature_gates = membership.get("feature_gates")
    if not isinstance(feature_gates, dict) or feature_gates.get("docferry.publish.folder") is not True:
        raise CliError("Folder sharing requires DocFerry Pro access.")
    max_documents = int(membership.get("max_folder_document_count") or 0)
    max_total_bytes = int(membership.get("max_folder_total_bytes") or 0)
    total_bytes = sum(path.stat().st_size for path in documents)
    if len(documents) > max_documents:
        raise CliError(f"This folder has {len(documents)} notes; current access allows {max_documents}.")
    if total_bytes > max_total_bytes:
        raise CliError(f"This folder is {total_bytes} bytes; current access allows {max_total_bytes}.")
    existing_id = normalized_folder_share_id(args.folder_share_id) if args.folder_share_id else None
    if not existing_id and membership.get("can_create_folder_share") is not True:
        raise CliError("The active folder-share limit has been reached.")
    client_info = {
        "plugin_id": "docferry-cli",
        "plugin_version": DOCFERRY_CLI_VERSION,
        "obsidian_version": "cli",
        "vault_name": root.name,
    }
    draft = require_ok(
        client.post(
            "/v0/folder-shares/drafts",
            body={
                "folder_share_id": existing_id,
                "vault_id": workspace_id(root),
                "source_folder": source_folder,
                "title": (args.title or folder.name or root.name).strip(),
                "expected_document_count": len(documents),
                "theme_mode": "reader",
                "css_asset_id": None,
                "client": client_info,
            },
            auth=True,
        ),
        "prepare folder revision",
    ).json()
    revision_id = str(draft.get("revision_id") or "")
    if not revision_id:
        raise CliError("DocFerry did not return a folder revision id.")
    for index, path in enumerate(documents):
        markdown = path.read_text(encoding="utf-8")
        relative = path.relative_to(folder).as_posix()
        route_key = hashlib.sha256(relative.casefold().encode()).hexdigest()[:20]
        require_ok(
            client.put(
                f"/v0/folder-shares/drafts/{revision_id}/documents/{route_key}",
                body={
                    "route_key": route_key,
                    "relative_path": relative,
                    "source_hash": f"sha256:{hashlib.sha256(markdown.encode()).hexdigest()}",
                    "title": title_from_markdown(markdown) or path.stem,
                    "markdown": markdown,
                    "html_snapshot": None,
                    "css_asset_id": None,
                    "assets": [],
                    "navigation_order": index,
                },
                auth=True,
            ),
            f"upload folder document {relative}",
        )
    password_mode = "clear" if args.clear_password else "set" if args.password else "keep"
    return require_ok(
        client.post(
            f"/v0/folder-shares/drafts/{revision_id}/commit",
            body={
                "password": args.password,
                "password_mode": password_mode,
                "expires_at": args.expires_at,
            },
            auth=True,
        ),
        "publish folder",
    ).json()


def import_command(client: Client, args: argparse.Namespace) -> dict[str, object]:
    parsed = urlparse(validated_public_url(args.url))
    output = cli_workspace_output_path(args.workspace, args.output)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) == 2 and parts[0] == "s":
        return import_share(args, expected_server_url=client.base_url, output_path=output)
    mode = media_note_import_mode(
        client,
        parsed.geturl(),
        force_advanced=bool(args.advanced),
    )
    if mode == "link_only":
        return save_link_note(parsed.geturl(), output, overwrite=args.overwrite)
    if not args.confirm:
        raise CliError(
            "Advanced Import is available for this link. Rerun with --confirm after the user "
            "approves external processing; nothing was saved."
        )
    created = require_ok(
        client.post(
            "/v0/media-note/jobs",
            body={"source_url": parsed.geturl(), "output_language": "source"},
            auth=True,
            extra_headers={"Idempotency-Key": normalized_media_note_idempotency_key(None)},
        ),
        "create advanced import",
    ).json()
    job_id = normalized_media_note_job_id(str(created.get("job_id") or ""))
    ready = wait_for_media_note(
        client,
        job_id,
        timeout_seconds=args.timeout,
        poll_interval=args.poll_interval,
    )
    return save_media_note_result(ready, output, overwrite=args.overwrite)


def wait_for_media_note(
    client: Client,
    job_id: str,
    *,
    timeout_seconds: int,
    poll_interval: float,
) -> dict[str, object]:
    timeout = max(1, min(timeout_seconds, 1800))
    interval = max(0.25, min(poll_interval, 30.0))
    deadline = time.monotonic() + timeout
    while True:
        body = require_ok(client.get(f"/v0/media-note/jobs/{job_id}", auth=True), "advanced import status").json()
        status = str(body.get("status") or "")
        if status in {"extracted", "degraded"}:
            return body
        if status in {"unsupported", "failed", "cancelled", "expired"}:
            raise CliError(f"Advanced Import ended with status {status}: {body.get('error_message') or 'No result.'}")
        if time.monotonic() >= deadline:
            raise CliError(f"Advanced Import is still processing. Check later with `docferry media-note status {job_id}`.")
        time.sleep(interval)


def save_media_note_result(body: dict[str, object], output_arg: Path, *, overwrite: bool) -> dict[str, object]:
    markdown = body.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        raise CliError("Advanced Import result is empty.")
    result_contract = body.get("result_contract") if isinstance(body.get("result_contract"), dict) else {}
    title = str(result_contract.get("title") or "DocFerry Import")
    output = resolve_output_path(output_arg.expanduser(), title)
    if output.is_symlink():
        raise CliError(f"Output must not be a symbolic link: {output}")
    if output.exists() and not overwrite:
        raise CliError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    return {
        "saved": True,
        "job_id": body.get("job_id"),
        "output": str(output.resolve()),
        "title": title,
        "status": body.get("status"),
    }


def share_payload(args: argparse.Namespace, *, is_update: bool = False) -> dict[str, object]:
    _root, file_path, relative_path = cli_workspace_markdown_path(args.workspace, args.file)
    markdown = file_path.read_text(encoding="utf-8")
    title = args.title or title_from_markdown(markdown) or file_path.stem
    payload: dict[str, object] = {
        "source_path": normalized_cli_source_path(args.source_path, fallback=relative_path),
        "source_hash": f"sha256:{hashlib.sha256(markdown.encode('utf-8')).hexdigest()}",
        "title": title,
        "markdown": markdown,
        "html_snapshot": None,
        "theme_mode": "reader",
        "css_asset_id": None,
        "assets": [],
        "expires_at": args.expires_at,
        "client": {
            "plugin_id": "docferry-cli",
            "plugin_version": DOCFERRY_CLI_VERSION,
            "obsidian_version": "cli",
        },
    }
    if args.password:
        payload["password"] = args.password
    if is_update:
        payload["password_mode"] = args.password_mode
    return payload


def login_command(
    client: Client,
    args: argparse.Namespace,
    config: CliConfig,
    config_path: Path,
    server_url: str,
) -> None:
    login_client = str(args.client or "cli")
    login_instance_type = "vscode_extension" if login_client == "vscode" else "cli"
    if login_client == "vscode" and not (
        args.device_code or args.loopback or args.manual_callback or args.callback_url
    ):
        raise CliError("VS Code login requires Device Code, loopback, or manual callback mode.")

    if args.from_obsidian:
        plugin_token = session_token_from_obsidian(args.from_obsidian)
        complete_login_from_session_token(
            config,
            config_path,
            server_url,
            plugin_token,
            source="obsidian",
            persist=True,
        )
        return

    if args.callback_url:
        complete_login_from_callback(
            client,
            config,
            config_path,
            server_url,
            config.client_instance_id,
            str(args.callback_url),
            redirect_uri=redirect_uri_from_callback(str(args.callback_url), "manual-callback"),
            code_verifier=config.pending_code_verifier,
            expected_instance_type=login_instance_type,
        )
        return

    explicit_browser_mode = bool(args.device_code or args.loopback or args.manual_callback)
    env_token = session_token_from_env()
    if env_token and not explicit_browser_mode:
        complete_login_from_session_token(
            config,
            config_path,
            server_url,
            env_token,
            source="environment",
            persist=False,
        )
        return

    if not args.loopback and not args.manual_callback:
        complete_login_from_device_code(client, args, config, config_path, server_url)
        return

    auth_config = require_ok(client.get("/v0/auth/config"), "auth config").json()
    provider = auth_config.get("provider")
    login_url = auth_config.get("login_url")
    if provider != "synapsehub" or not isinstance(login_url, str) or not login_url:
        raise CliError("Bondie account login is not configured on this DocFerry server.")

    client_instance_id = config.client_instance_id or f"dfcli_{secrets.token_urlsafe(18)}"
    code_verifier = generate_pkce_code_verifier()
    config.client_instance_id = client_instance_id
    config.server_url = server_url
    config.pending_code_verifier = code_verifier
    save_config(config_path, config)
    callback_server = LoopbackCallbackServer(login_client)
    try:
        auth_url = login_url_with_context(
            login_url,
            client_instance_id=client_instance_id,
            plugin_version=DOCFERRY_CLI_VERSION,
            platform=f"{platform.system()} {platform.release()}",
            completion_redirect_uri=callback_server.redirect_uri,
            code_challenge=pkce_code_challenge(code_verifier),
            instance_type=login_instance_type,
        )
        browser_opened = False
        if not args.no_browser:
            browser_opened = webbrowser.open(auth_url)
        print("Open this URL to sign in:")
        print(auth_url)
        print()
        if not browser_opened and not args.no_browser:
            print("The browser did not report opening. Copy the URL above into a browser.", file=sys.stderr)
        if args.manual_callback:
            callback_url = prompt_for_callback_url()
        else:
            print(f"Waiting for Bondie to return to {callback_server.redirect_uri}...")
            try:
                callback_url = callback_server.wait(max(1, args.timeout))
            except CliError as exc:
                if sys.stdin.isatty():
                    print(str(exc), file=sys.stderr)
                    print("Paste the final callback URL to continue.", file=sys.stderr)
                    callback_url = prompt_for_callback_url()
                else:
                    raise CliError(
                        f"{exc} Rerun `docferry login --manual-callback --no-browser` and paste the final callback URL."
                    ) from exc
    finally:
        callback_server.close()
    complete_login_from_callback(
        client,
        config,
        config_path,
        server_url,
        client_instance_id,
        callback_url,
        redirect_uri=redirect_uri_from_callback(callback_url, callback_server.redirect_uri),
        code_verifier=code_verifier,
        expected_instance_type=login_instance_type,
    )


def complete_login_from_session_token(
    config: CliConfig,
    config_path: Path,
    server_url: str,
    session_token: str,
    *,
    source: str,
    persist: bool,
) -> None:
    token_client = Client(server_url, session_token)
    status = require_ok(token_client.get("/v0/auth/whoami", auth=True), f"{source} session").json()
    expires_at = string_or_none(status.get("expires_at"))
    if persist:
        config.server_url = server_url
        config.session_token = session_token
        config.session_expires_at = expires_at
        config.pending_code_verifier = None
        save_config(config_path, config)
    print_json(
        {
            "authenticated": True,
            "auth_type": "synapsehub-session",
            "server_url": server_url,
            "expires_at": expires_at,
            "source": source,
            "persisted": persist,
            "config": str(config_path) if persist else None,
        }
    )


def complete_login_from_device_code(
    client: Client,
    args: argparse.Namespace,
    config: CliConfig,
    config_path: Path,
    server_url: str,
) -> None:
    login_client = str(getattr(args, "client", None) or "cli")
    instance_type = "vscode_extension" if login_client == "vscode" else "cli_device"
    client_instance_id = config.client_instance_id or f"dfcli_{secrets.token_urlsafe(18)}"
    config.client_instance_id = client_instance_id
    config.server_url = server_url
    config.pending_code_verifier = None
    save_config(config_path, config)
    device = require_ok(
        client.post(
            "/v0/auth/device/code",
            body={
                "client_instance_id": client_instance_id,
                "plugin_version": DOCFERRY_CLI_VERSION,
                "platform": f"{platform.system()} {platform.release()}",
                "instance_type": instance_type,
            },
        ),
        "device login start",
    ).json()
    device_code = string_or_none(device.get("device_code"))
    user_code = string_or_none(device.get("user_code"))
    verification_uri = string_or_none(device.get("verification_uri"))
    verification_uri_complete = string_or_none(device.get("verification_uri_complete")) or verification_uri
    expires_in = int(device.get("expires_in") or args.timeout)
    interval = max(1, int(device.get("interval") or 5))
    if not device_code or not user_code or not verification_uri:
        raise CliError("Device login start did not return a complete authorization response.")
    browser_opened = False
    if not args.no_browser and verification_uri_complete:
        browser_opened = webbrowser.open(verification_uri_complete)
    print("Open this URL to sign in:")
    print(verification_uri_complete or verification_uri)
    print()
    print(f"One-time code: {user_code}")
    print("Waiting for approval...")
    if not browser_opened and not args.no_browser:
        print("The browser did not report opening. Copy the URL above into a browser.", file=sys.stderr)
    deadline = time.monotonic() + min(max(1, args.timeout), max(1, expires_in))
    transient_failures = 0
    while time.monotonic() < deadline:
        try:
            response = client.post("/v0/auth/device/token", body={"device_code": device_code})
        except URLError:
            transient_failures += 1
            if transient_failures > DEVICE_LOGIN_MAX_TRANSIENT_FAILURES:
                raise CliError("Device login could not reach DocFerry after several retries.") from None
            sleep_device_login_retry(interval, transient_failures, deadline)
            continue
        if 200 <= response.status_code < 300:
            complete_login_from_exchange_body(
                config,
                config_path,
                server_url,
                response.json(),
                source="device_code",
            )
            return
        if response.status_code in {502, 503, 504}:
            transient_failures += 1
            if transient_failures > DEVICE_LOGIN_MAX_TRANSIENT_FAILURES:
                raise CliError("Device login was temporarily unavailable after several retries.")
            sleep_device_login_retry(interval, transient_failures, deadline)
            continue
        transient_failures = 0
        code = response_error_code(response)
        if code == "authorization_pending":
            time.sleep(min(interval, max(0.1, deadline - time.monotonic())))
            continue
        if code == "slow_down":
            interval += 5
            time.sleep(min(interval, max(0.1, deadline - time.monotonic())))
            continue
        if code == "access_denied":
            raise CliError("Device login was denied in the browser.")
        if code == "expired_device_code":
            raise CliError("Device login code expired. Run `docferry login` again.")
        raise CliError(f"Device login failed: {response.status_code} {response.text[:500]}")
    raise CliError("Device login timed out before browser approval completed.")


def sleep_device_login_retry(interval: int, failures: int, deadline: float) -> None:
    delay = min(interval * (2 ** (failures - 1)), DEVICE_LOGIN_MAX_RETRY_SECONDS)
    time.sleep(min(delay, max(0.1, deadline - time.monotonic())))


def complete_login_from_exchange_body(
    config: CliConfig,
    config_path: Path,
    server_url: str,
    exchange: dict[str, object],
    *,
    source: str,
) -> None:
    access_token = exchange.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise CliError("Login exchange did not return a DocFerry session token.")
    config.server_url = server_url
    config.session_token = access_token
    config.session_expires_at = string_or_none(exchange.get("expires_at"))
    config.pending_code_verifier = None
    save_config(config_path, config)
    print_json(
        {
            "authenticated": True,
            "auth_type": "synapsehub-session",
            "server_url": server_url,
            "expires_at": config.session_expires_at,
            "source": source,
            "config": str(config_path),
        }
    )


def complete_login_from_callback(
    client: Client,
    config: CliConfig,
    config_path: Path,
    server_url: str,
    client_instance_id: str | None,
    callback_url: str,
    *,
    redirect_uri: str,
    code_verifier: str | None,
    expected_instance_type: str = "cli",
) -> None:
    code, state = auth_code_from_callback(callback_url)
    state_client_instance_id = validate_callback_state(
        state,
        client_instance_id,
        expected_instance_type=expected_instance_type,
    )
    exchange = require_ok(
        client.post(
            "/v0/auth/exchange",
            body=auth_exchange_payload(code, state, redirect_uri, code_verifier),
        ),
        "login exchange",
    ).json()
    config.client_instance_id = state_client_instance_id or client_instance_id
    complete_login_from_exchange_body(
        config,
        config_path,
        server_url,
        exchange,
        source="loopback_pkce",
    )


def prompt_for_callback_url() -> str:
    print("Paste the final callback URL, or the code=... query string, then press Enter:")
    value = input("> ").strip()
    if not value:
        raise CliError("No callback URL was provided.")
    return value


def generate_pkce_code_verifier() -> str:
    return secrets.token_urlsafe(64)[:96]


def pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def auth_exchange_payload(
    code: str,
    state: str | None,
    redirect_uri: str,
    code_verifier: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {"code": code, "state": state, "redirect_uri": redirect_uri}
    if code_verifier:
        payload["code_verifier"] = code_verifier
    return payload


def logout_command(
    client: Client,
    args: argparse.Namespace,
    config: CliConfig,
    config_path: Path,
    token: str | None,
) -> None:
    remote_status = "not_sent"
    if token and not args.local_only:
        response = client.post("/v0/auth/logout", auth=True)
        remote_status = "ok" if 200 <= response.status_code < 300 else f"failed_{response.status_code}"
    config.session_token = None
    config.session_expires_at = None
    save_config(config_path, config)
    print_json({"authenticated": False, "remote_logout": remote_status, "config": str(config_path)})


def auth_status_command(client: Client, token: str | None) -> None:
    if not token:
        print_json({"authenticated": False, "auth_type": None})
        return
    response = require_ok(client.get("/v0/auth/whoami", auth=True), "auth status")
    print_json(sanitize_whoami(response.json()))


def account_status_summary(client: Client, token: str | None) -> dict[str, object]:
    if not token:
        return {
            "authenticated": False,
            "auth_type": None,
            "next_action": "Run `docferry login`.",
        }
    response = require_ok(client.get("/v0/auth/whoami", auth=True), "auth status")
    return {
        **sanitize_whoami(response.json()),
        "membership": membership_summary(client),
    }


def sanitize_whoami(body: dict[str, object]) -> dict[str, object]:
    return {
        "authenticated": bool(body.get("authenticated")),
        "auth_type": string_or_none(body.get("auth_type")),
        "billing_session_ready": bool(body.get("billing_session_ready")),
        "product_key": string_or_none(body.get("product_key")),
        "product_subject": "present" if body.get("product_subject_id") else None,
        "product_instance": "present" if body.get("product_instance_id") else None,
        "display_user": "present" if body.get("display_user") else None,
        "scopes": body.get("scopes") if isinstance(body.get("scopes"), list) else [],
        "expires_at": string_or_none(body.get("expires_at")),
    }


def login_url_with_context(
    login_url: str,
    *,
    client_instance_id: str,
    plugin_version: str,
    platform: str,
    completion_redirect_uri: str,
    code_challenge: str,
    instance_type: str = "cli",
) -> str:
    parsed = urlparse(login_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["client_instance_id"] = [client_instance_id]
    query["plugin_version"] = [plugin_version]
    query["platform"] = [platform]
    query["instance_type"] = [instance_type]
    query["prompt"] = ["login"]
    query["completion_redirect_uri"] = [completion_redirect_uri]
    query["code_challenge"] = [code_challenge]
    query["code_challenge_method"] = [PKCE_CODE_CHALLENGE_METHOD]
    encoded = urlencode(query, doseq=True)
    return parsed._replace(query=encoded).geturl()


def auth_code_from_callback(value: str) -> tuple[str, str | None]:
    parsed = urlparse(value.strip())
    query = parse_qs(parsed.query)
    code_values = query.get("code")
    if not code_values and (value.startswith("code=") or value.startswith("?code=")):
        query = parse_qs(value[1:] if value.startswith("?") else value)
        code_values = query.get("code")
    if not code_values or not code_values[0]:
        raise CliError("Callback URL is missing the login code.")
    state_values = query.get("state")
    return code_values[0], state_values[0] if state_values else None


def redirect_uri_from_callback(value: str, fallback: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme and parsed.netloc and parsed.path:
        return parsed._replace(params="", query="", fragment="").geturl()
    return fallback


def validate_callback_state(
    state: str | None,
    expected_client_instance_id: str | None,
    *,
    expected_instance_type: str = "cli",
) -> str | None:
    if not state:
        raise CliError("Callback URL is missing the login state.")
    payload = unsigned_state_payload(state)
    state_client_instance_id = string_or_none(payload.get("client_instance_id"))
    if expected_client_instance_id and state_client_instance_id != expected_client_instance_id:
        raise CliError("Callback state does not match this CLI login attempt.")
    instance_type = string_or_none(payload.get("instance_type"))
    if instance_type and instance_type != expected_instance_type:
        raise CliError("Callback state was not issued for this login client.")
    return state_client_instance_id


def unsigned_state_payload(state: str) -> dict[str, object]:
    payload_part = state.split(".", 1)[0]
    try:
        decoded = base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4)).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        raise CliError("Callback URL contains an unreadable login state.") from None
    if not isinstance(payload, dict):
        raise CliError("Callback URL contains an invalid login state.")
    return payload


class LoopbackCallbackHandler(BaseHTTPRequestHandler):
    server: "LoopbackHttpServer"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.server.ignored_paths.append(parsed.path or "/")
            body = b"DocFerry CLI is waiting for /callback."
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.server.callback_url = f"{self.server.redirect_uri}{'?' + parsed.query if parsed.query else ''}"
        body = loopback_completion_body(self.server.login_client)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        finally:
            self.server.callback_event.set()

    def log_message(self, format: str, *args: object) -> None:
        return


def loopback_completion_body(login_client: str) -> bytes:
    if login_client == "vscode":
        return (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>DocFerry connected</title></head><body>"
            "<main><h1>DocFerry is connected</h1>"
            "<p>You can close this page and continue in Visual Studio Code.</p>"
            "<p><a href='vscode://bondie.docferry/auth/complete'>Open Visual Studio Code</a></p>"
            "</main><script>window.location.href='vscode://bondie.docferry/auth/complete';</script>"
            "</body></html>"
        ).encode("utf-8")
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>DocFerry login complete</title></head>"
        "<body><main><h1>Login complete</h1><p>You can return to the terminal.</p></main></body></html>"
    ).encode("utf-8")


class LoopbackHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    callback_url: str | None = None
    callback_event: Event
    redirect_uri: str
    ignored_paths: list[str]
    login_client: str


class LoopbackCallbackServer:
    def __init__(self, login_client: str = "cli") -> None:
        self.httpd = LoopbackHttpServer(("127.0.0.1", 0), LoopbackCallbackHandler)
        self.redirect_uri = f"http://127.0.0.1:{self.httpd.server_port}/callback"
        self.httpd.redirect_uri = self.redirect_uri
        self.httpd.ignored_paths = []
        self.httpd.login_client = login_client
        self.httpd.callback_event = Event()

    def wait(self, timeout: int) -> str:
        server_thread = Thread(
            target=self.httpd.serve_forever,
            kwargs={"poll_interval": 0.05},
            daemon=True,
        )
        server_thread.start()
        try:
            if self.httpd.callback_event.wait(timeout):
                callback_url = self.httpd.callback_url
                if callback_url:
                    return callback_url
            detail = ""
            if self.httpd.ignored_paths:
                ignored = ", ".join(self.httpd.ignored_paths[:5])
                detail = f" Received non-callback requests first: {ignored}."
            raise CliError(f"Login timed out before Bondie returned to the CLI.{detail}")
        finally:
            self.httpd.shutdown()
            server_thread.join(timeout=2)

    def close(self) -> None:
        self.httpd.server_close()


def config_path_from_arg(value: str | None) -> Path:
    if value:
        return Path(value).expanduser()
    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        root = Path(xdg_config_home).expanduser()
    elif platform.system() == "Windows" and (os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")):
        root = Path(os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or "")
    else:
        root = Path.home() / ".config"
    return root / "docferry" / "config.json"


def load_config(path: Path) -> CliConfig:
    if not path.exists():
        return CliConfig()
    try:
        return CliConfig.from_json(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise CliError(f"Invalid DocFerry config JSON: {path}") from exc


def save_config(path: Path, config: CliConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    data = json.dumps(config.to_json(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
        os.replace(tmp_path, path)
        path.chmod(0o600)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def resolve_server_url(args: argparse.Namespace, config: CliConfig) -> str:
    explicit = args.server_url or os.getenv("DOCFERRY_SERVER_URL")
    if explicit:
        return explicit.rstrip("/")
    persisted = normalized_persisted_server_url(config.server_url)
    return persisted or DEFAULT_SERVER_URL


def migrate_stale_persisted_server(
    config: CliConfig,
    config_path: Path,
    *,
    explicit_server: bool,
) -> bool:
    if explicit_server or not config.server_url or normalized_persisted_server_url(config.server_url):
        return False
    config.server_url = DEFAULT_SERVER_URL
    config.session_token = None
    config.session_expires_at = None
    config.pending_code_verifier = None
    save_config(config_path, config)
    return True


def normalized_persisted_server_url(value: str | None) -> str | None:
    candidate = (value or "").strip().rstrip("/")
    return candidate if candidate in PERSISTED_SERVER_URLS else None


def resolve_token(config: CliConfig, server_url: str | None = None) -> str | None:
    environment_token = session_token_from_env()
    if environment_token:
        return environment_token
    if not config.session_token or not server_url:
        return config.session_token
    persisted = normalized_persisted_server_url(config.server_url or DEFAULT_SERVER_URL)
    return config.session_token if persisted == server_url.rstrip("/") else None


def session_token_from_env() -> str | None:
    for name in TOKEN_ENV_VARS:
        token = (os.getenv(name) or "").strip()
        if token:
            return token
    return None


def session_token_from_obsidian(value: str) -> str:
    root = Path(value).expanduser()
    candidates = [
        root,
    ] if root.is_file() else [
        root / ".obsidian" / "plugins" / "docferry" / "data.json",
        root / "data.json",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            body = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"Invalid Obsidian DocFerry data JSON: {candidate}") from exc
        if not isinstance(body, dict):
            raise CliError(f"Invalid Obsidian DocFerry data file: {candidate}")
        token = string_or_none(body.get("sessionToken")) or string_or_none(body.get("session_token"))
        if token:
            return token
        raise CliError(f"Obsidian DocFerry data file does not contain a sessionToken: {candidate}")
    raise CliError(
        "Could not find DocFerry plugin data.json. Pass the Obsidian vault path or "
        "the full .obsidian/plugins/docferry/data.json path."
    )


def string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def import_share(
    args: argparse.Namespace,
    *,
    expected_server_url: str,
    output_path: Path | None = None,
) -> dict[str, object]:
    base_url, slug = parse_share_url(args.url, expected_base_url=expected_server_url)
    client = Client(base_url, None)
    response = client.get(f"/s/{slug}/import")
    if response.status_code == 401 and args.password:
        require_ok(client.post(f"/s/{slug}/password", body={"password": args.password}), "password")
        response = client.get(f"/s/{slug}/import")
    body = require_ok(response, "import-url").json()
    output = resolve_output_path(output_path or Path(args.output), str(body["title"]))
    if output.exists() and not args.overwrite:
        raise CliError(f"Output already exists: {output}. Use --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(str(body["markdown"]), encoding="utf-8")
    imported_assets = import_assets(client, output.parent, body.get("assets", []), args.overwrite)
    return {
        "imported": True,
        "source_type": "docferry_share",
        "output": str(output.resolve()),
        "slug": body["slug"],
        "title": body["title"],
        "assets": imported_assets,
    }


def import_assets(client: Client, root: Path, assets: object, overwrite: bool) -> list[dict[str, str]]:
    if not isinstance(assets, list):
        return []
    imported: list[dict[str, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        url = asset.get("url")
        if not isinstance(url, str) or not url:
            continue
        if not url_has_origin(url, client.base_url):
            raise CliError("Imported asset URL is outside the configured DocFerry origin.")
        output = resolve_asset_output_path(
            root,
            str(asset.get("original_path") or ""),
            str(asset.get("filename") or asset.get("asset_id") or "attachment"),
        )
        if output.exists() and not overwrite:
            raise CliError(f"Asset already exists: {output}. Use --overwrite to replace it.")
        response = client.get_bytes(url)
        if response.status_code != 200:
            raise CliError(f"asset import failed: {response.status_code}: {url}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response.body)
        imported.append({"asset_id": str(asset.get("asset_id") or ""), "output": str(output)})
    return imported


def parse_share_url(value: str, *, expected_base_url: str) -> tuple[str, str]:
    parsed = urlparse(validated_public_url(value))
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] != "s":
        raise CliError("Share URL must look like https://host/s/{slug}.")
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    if canonical_origin(base_url) != canonical_origin(expected_base_url):
        raise CliError("Share URL must use the configured DocFerry origin.")
    return base_url, parts[1]


def url_has_origin(value: str, expected_base_url: str) -> bool:
    parsed = urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return value.startswith("/") and not value.startswith("//")
    try:
        return canonical_origin(value) == canonical_origin(expected_base_url)
    except CliError:
        return False


def canonical_origin(value: str) -> tuple[str, str, int]:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise CliError("DocFerry origin must be a public http(s) URL without embedded credentials.")
    default_port = 443 if parsed.scheme == "https" else 80
    try:
        port = parsed.port or default_port
    except ValueError:
        raise CliError("DocFerry origin contains an invalid port.") from None
    return parsed.scheme, parsed.hostname.lower(), port


def validated_public_url(value: str) -> str:
    normalized = value.strip()
    if re.search(r"[\x00-\x20\x7f<>]", normalized):
        raise CliError("URL must not contain spaces, control characters, or angle brackets.")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise CliError("URL must be a public http(s) link without embedded credentials.")
    return parsed.geturl()


def media_note_provider_for_url(value: str) -> str:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube"
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "tiktok"
    if host in {"bilibili.com", "b23.tv"} or host.endswith(".bilibili.com"):
        return "bilibili"
    if host in {"douyin.com", "v.douyin.com"} or host.endswith(".douyin.com"):
        return "douyin"
    if host == "mp.weixin.qq.com":
        return "wechat"
    if host == "vimeo.com" or host.endswith(".vimeo.com"):
        return "vimeo"
    if re.search(r"\.(mp3|m4a|wav|ogg)$", parsed.path, flags=re.IGNORECASE):
        return "audio"
    if re.search(r"\.(mp4|webm|mov)$", parsed.path, flags=re.IGNORECASE):
        return "video"
    return "web"


def ensure_media_note_available(client: Client, source_url: str) -> None:
    provider = media_note_provider_for_url(source_url)
    mandatory_provider = provider in MANDATORY_ADVANCED_IMPORT_PROVIDERS
    membership = require_ok(client.get("/v0/membership", auth=True), "membership").json()
    feature_gates = membership.get("feature_gates")
    if not isinstance(feature_gates, dict) or feature_gates.get("docferry.ai.assist") is not True:
        raise CliError("Advanced Import requires DocFerry Pro access.")
    runtime = membership.get("media_note")
    if not isinstance(runtime, dict) or runtime.get("enabled") is not True:
        suffix = "Nothing was saved." if mandatory_provider else "Save the link instead."
        raise CliError(f"Advanced Import is not enabled on this DocFerry service. {suffix}")
    providers = runtime.get("supported_providers")
    if not isinstance(providers, list) or provider not in providers:
        suffix = "Nothing was saved." if mandatory_provider else "Save the link instead."
        raise CliError(f"Advanced Import is not available for provider '{provider}'. {suffix}")


def media_note_import_mode(
    client: Client,
    source_url: str,
    *,
    force_advanced: bool = False,
) -> str:
    """Choose the import path from session, entitlement, and runtime state."""
    if force_advanced:
        ensure_media_note_available(client, source_url)
        return "advanced"
    if not getattr(client, "token", None):
        return "link_only"

    provider = media_note_provider_for_url(source_url)
    membership = require_ok(client.get("/v0/membership", auth=True), "membership").json()
    feature_gates = membership.get("feature_gates")
    entitled = (
        isinstance(feature_gates, dict)
        and feature_gates.get("docferry.ai.assist") is True
    )
    if not entitled:
        return "link_only"

    runtime = membership.get("media_note")
    runtime_enabled = isinstance(runtime, dict) and runtime.get("enabled") is True
    providers = runtime.get("supported_providers") if isinstance(runtime, dict) else None
    provider_enabled = isinstance(providers, list) and provider in providers
    if runtime_enabled and provider_enabled:
        return "advanced"
    if provider in MANDATORY_ADVANCED_IMPORT_PROVIDERS:
        raise CliError(
            f"Advanced Import is unavailable for provider '{provider}'. Nothing was saved."
        )
    return "link_only"


def normalized_media_note_idempotency_key(value: str | None) -> str:
    candidate = value.strip() if value else f"cli-{secrets.token_hex(18)}"
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", candidate):
        raise CliError("Idempotency key must contain 8-128 letters, numbers, dots, colons, underscores, or hyphens.")
    return candidate


def normalized_media_note_job_id(value: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"mnj_[A-Za-z0-9]+", candidate):
        raise CliError("A valid DocFerry Media Note job id is required.")
    return candidate


def normalized_folder_share_id(value: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"fsh_[A-Za-z0-9]+", candidate):
        raise CliError("A valid DocFerry folder share id is required.")
    return candidate


def normalized_share_id(value: str) -> str:
    candidate = value.strip()
    if not re.fullmatch(r"sh_[A-Za-z0-9]+", candidate):
        raise CliError("A valid DocFerry share id is required.")
    return candidate


def cli_workspace_root(value: str | None) -> Path:
    root = Path(value or os.getcwd()).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise CliError("The configured DocFerry workspace is not a directory.")
    return root


def cli_workspace_markdown_path(workspace: str | None, value: str) -> tuple[Path, Path, str]:
    root = cli_workspace_root(workspace)
    raw = Path(value).expanduser()
    unresolved = raw if raw.is_absolute() else root / raw
    try:
        candidate = unresolved.resolve(strict=True)
    except OSError as exc:
        raise CliError(f"Markdown file does not exist: {value}") from exc
    if not candidate.is_file() or not candidate.is_relative_to(root):
        raise CliError("The Markdown file must stay inside the configured DocFerry workspace.")
    relative = candidate.relative_to(root)
    if candidate.suffix.lower() != ".md" or any(part.startswith(".") for part in relative.parts):
        raise CliError("DocFerry can publish only visible Markdown files inside the workspace.")
    return root, candidate, relative.as_posix()


def normalized_cli_source_path(value: str | None, *, fallback: str) -> str:
    candidate = (value or fallback).strip().replace("\\", "/")
    path_value = PurePosixPath(candidate)
    if (
        not candidate
        or path_value.is_absolute()
        or any(part in {"", ".", ".."} or part.startswith(".") for part in path_value.parts)
        or any(ord(character) < 32 or ord(character) == 127 for character in candidate)
    ):
        raise CliError("Source path must be a visible relative workspace path.")
    return path_value.as_posix()


def cli_workspace_output_path(workspace: str | None, value: str) -> Path:
    root = cli_workspace_root(workspace)
    raw = Path(value).expanduser()
    candidate = (raw if raw.is_absolute() else root / raw).resolve(strict=False)
    if not candidate.is_relative_to(root):
        raise CliError("Import output must stay inside the configured DocFerry workspace.")
    relative = candidate.relative_to(root)
    if any(part.startswith(".") or part == ".." for part in relative.parts):
        raise CliError("Import output must use a visible path inside the configured workspace.")
    return candidate


def cli_folder_documents(root: Path, value: str) -> tuple[Path, str, list[Path]]:
    raw = Path(value).expanduser()
    candidate = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
    if not candidate.is_dir() or not candidate.is_relative_to(root):
        raise CliError("The folder must stay inside the configured DocFerry workspace.")
    relative = candidate.relative_to(root)
    if relative.parts and any(part.startswith(".") or part == ".." for part in relative.parts):
        raise CliError("Hidden workspace folders cannot be shared.")
    documents: list[Path] = []
    for path in candidate.rglob("*.md"):
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_file() or not resolved.is_relative_to(candidate):
            continue
        document_relative = resolved.relative_to(candidate)
        if any(part.startswith(".") for part in document_relative.parts):
            continue
        documents.append(resolved)
    documents.sort(key=lambda path: path.relative_to(candidate).as_posix().casefold())
    source_folder = root.name if candidate == root else relative.as_posix()
    return candidate, source_folder, documents


def workspace_id(root: Path) -> str:
    return f"workspace_{hashlib.sha256(str(root).encode()).hexdigest()[:24]}"


def save_link_note(url: str, output_arg: Path, *, overwrite: bool) -> dict[str, object]:
    parsed = urlparse(url)
    provider = media_note_provider_for_url(url)
    host = (parsed.hostname or "Saved link").removeprefix("www.")
    title = f"Saved from {host}"
    output = resolve_output_path(output_arg.expanduser(), title)
    if output.is_symlink():
        raise CliError(f"Output must not be a symbolic link: {output}")
    if output.exists() and not overwrite:
        raise CliError(f"Output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        (
            f"# {title}\n\n"
            "> [!info] Saved link\n"
            "> DocFerry saved this link without remote processing.\n\n"
            f"[Open original]({url})\n\n"
            f"Source: {provider}\n"
        ),
        encoding="utf-8",
    )
    return {
        "saved": True,
        "source_type": "public_link",
        "provider": provider,
        "advanced": False,
        "output": str(output.resolve()),
        "title": title,
    }


def resolve_output_path(path: Path, title: str) -> Path:
    if path.exists() and path.is_dir():
        return path / f"{safe_filename(title)}.md"
    if path.suffix:
        return path
    return path / f"{safe_filename(title)}.md"


def resolve_asset_output_path(root: Path, original_path: str, filename: str) -> Path:
    candidate = original_path.split("#", 1)[0].split("?", 1)[0].replace("\\", "/").strip()
    if not candidate:
        candidate = f"attachments/{filename}"
    parts = [
        safe_filename(part)
        for part in PurePosixPath(candidate).parts
        if part not in {"", ".", "..", "/"}
    ]
    if not parts:
        parts = ["attachments", safe_filename(filename)]
    output = root.joinpath(*parts)
    root_resolved = root.resolve()
    output_resolved = output.resolve()
    if not output_resolved.is_relative_to(root_resolved):
        return root / "attachments" / safe_filename(filename)
    return output


def title_from_markdown(markdown: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", markdown, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    name = re.sub(r"[\\/:*?\"<>|]+", "-", normalized).strip().strip(".")
    return name[:120] or f"docferry-import-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"


def require_ok(response: Response, label: str) -> Response:
    if 200 <= response.status_code < 300:
        return response
    try:
        body = response.json()
        error = body.get("error")
        if isinstance(error, dict):
            raise CliError(f"{label} failed: {response.status_code} {error.get('code')}: {error.get('message')}")
    except json.JSONDecodeError:
        pass
    raise CliError(f"{label} failed: {response.status_code}: {response.text[:500]}")


def response_error_code(response: Response) -> str | None:
    try:
        body = response.json()
    except json.JSONDecodeError:
        return None
    error = body.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
