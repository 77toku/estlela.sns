#!/usr/bin/env python3
"""Publish unsent ESTLELA update payloads to a Discord Incoming Webhook."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from render_update import render_update, validate_payload


ROOT = Path(__file__).resolve().parent
OUTBOX = ROOT / "outbox"
SENT = ROOT / "sent"
ATTEMPTS = ROOT / "attempts"
MAX_FILE_BYTES = 20 * 1024 * 1024
RETRYABLE_STATUS = {429}


def canonical_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def safe_release_id(payload: dict[str, Any]) -> str:
    validate_payload(payload)
    return str(payload["release_id"])


def discord_payload(payload: dict[str, Any], filename: str) -> dict[str, Any]:
    description_parts = []
    for item in payload["changes"]:
        kind = str(item.get("type", "更新")).strip()
        title = str(item["title"]).strip()
        benefit = str(item["benefit"]).strip()
        description_parts.append(f"**{kind}｜{title}**\n{benefit}")

    message = str(payload["message"]).strip()
    site_url = str(payload["site_url"]).strip()
    if site_url not in message:
        message = f"{message}\n\n{site_url}"
    if len(message) > 2000:
        raise ValueError("Discord content exceeds 2000 characters")

    return {
        "username": "ESTLELA UPDATE",
        "content": message,
        "embeds": [
            {
                "title": str(payload["headline"]).strip(),
                "url": site_url,
                "description": "\n\n".join(description_parts),
                "color": 15477115,
                "image": {"url": f"attachment://{filename}"},
                "footer": {"text": "ESTLELA BUSINESS SUPPORT"},
            }
        ],
        "allowed_mentions": {"parse": []},
    }


def multipart_body(payload_json: dict[str, Any], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----estlela-{uuid.uuid4().hex}"
    filename = file_path.name.replace('"', "")
    file_bytes = file_path.read_bytes()
    if len(file_bytes) > MAX_FILE_BYTES:
        raise ValueError("Generated image exceeds Discord's default 20 MiB upload limit")

    chunks: list[bytes] = []

    def add(value: str | bytes) -> None:
        chunks.append(value.encode("utf-8") if isinstance(value, str) else value)

    add(f"--{boundary}\r\n")
    add('Content-Disposition: form-data; name="payload_json"\r\n')
    add("Content-Type: application/json; charset=utf-8\r\n\r\n")
    add(json.dumps(payload_json, ensure_ascii=False, separators=(",", ":")))
    add("\r\n")
    add(f"--{boundary}\r\n")
    add(f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n')
    add("Content-Type: image/png\r\n\r\n")
    add(file_bytes)
    add("\r\n")
    add(f"--{boundary}--\r\n")
    return b"".join(chunks), boundary


def webhook_url_with_wait(webhook_url: str) -> str:
    separator = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{separator}wait=true"


def retry_delay(error: urllib.error.HTTPError, attempt: int) -> float:
    if error.code == 429:
        try:
            body = json.loads(error.read().decode("utf-8"))
            return min(max(float(body.get("retry_after", 1)), 0.5), 60)
        except Exception:
            header = error.headers.get("Retry-After")
            if header:
                try:
                    return min(max(float(header), 0.5), 60)
                except (TypeError, ValueError):
                    pass
    return float(min(2**attempt, 30))


def send_to_discord(webhook_url: str, payload: dict[str, Any], image_path: Path) -> str:
    request_payload = discord_payload(payload, image_path.name)
    body, boundary = multipart_body(request_payload, image_path)
    url = webhook_url_with_wait(webhook_url)
    last_error: Exception | None = None

    for attempt in range(1, 5):
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "ESTLELA-Update-Publisher/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                result = json.loads(raw)
                message_id = str(result.get("id", "")).strip()
                if not message_id:
                    raise RuntimeError("Discord returned success without a message ID")
                return message_id
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in RETRYABLE_STATUS or attempt == 4:
                raise RuntimeError(f"Discord webhook failed with HTTP {error.code}; inspect delivery before retrying") from None
            delay = retry_delay(error, attempt)
            print(f"Discord returned HTTP {error.code}; retrying in {delay:.1f}s")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError("Discord delivery is uncertain; inspect the channel before retrying") from None

    raise RuntimeError("Discord webhook failed") from last_error


def load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    validate_payload(payload)
    return payload


def write_marker(payload: dict[str, Any], message_id: str) -> Path:
    SENT.mkdir(parents=True, exist_ok=True)
    release_id = safe_release_id(payload)
    marker = SENT / f"{release_id}.json"
    marker.write_text(
        json.dumps(
            {
                "release_id": release_id,
                "content_hash": canonical_hash(payload),
                "discord_message_id": message_id,
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return marker


def render_only(payload_path: Path, output_path: Path) -> None:
    payload = load_payload(payload_path)
    render_update(payload, output_path)
    print(f"Rendered {output_path}")


def checkpoint(path: Path, message: str) -> None:
    """Persist before HTTP POST; failure must prevent sending."""
    if os.environ.get("ESTLELA_DURABLE_DELIVERY") != "1":
        raise RuntimeError("Live publishing requires ESTLELA_DURABLE_DELIVERY=1 and a writable main checkout")
    cwd = ROOT.parent
    subprocess.run(["git", "add", str(path.relative_to(cwd))], cwd=cwd, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=cwd, check=True)
    for attempt in range(3):
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=cwd, check=True)
        result = subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=cwd)
        if result.returncode == 0:
            return
    raise RuntimeError("Could not persist delivery state; automatic sending stopped")


def semantic_hash(payload: dict[str, Any]) -> str:
    return canonical_hash({k: payload[k] for k in ("headline", "changes", "message", "site_url")})


def check_queue() -> list[dict[str, Any]]:
    """Preflight the entire batch before sending any messages."""
    for marker in SENT.glob("*.json"):
        if not (OUTBOX / marker.name).exists():
            raise ValueError(f"Missing historical outbox for receipt: {marker.name}")
    pending = []
    versions: dict[int, str] = {}
    contents: dict[str, str] = {}
    for path in sorted(OUTBOX.glob("*.json")):
        payload = load_payload(path)
        rid = safe_release_id(payload)
        if path.stem != rid:
            raise ValueError("Outbox filename must equal release_id")
        source_versions = payload.get("source_versions", [])
        if not isinstance(source_versions, list) or any(type(v) is not int for v in source_versions):
            raise ValueError(f"Invalid source_versions: {rid}")
        if not source_versions and not rid.startswith("connection-test-"):
            raise ValueError(f"Missing source_versions: {rid}")
        for version in source_versions:
            if version in versions and versions[version] != rid:
                raise ValueError(f"Overlapping source version {version}: {rid}")
            versions[version] = rid
        digest = semantic_hash(payload)
        # Existing connection tests can intentionally contain the same text.
        if not rid.startswith("connection-test-"):
            if digest in contents:
                raise ValueError(f"Duplicate announcement content: {rid}")
            contents[digest] = rid
        marker = SENT / f"{rid}.json"
        if marker.exists():
            receipt = json.loads(marker.read_text())
            if (receipt.get("release_id") != rid or
                    receipt.get("content_hash") != canonical_hash(payload) or
                    not receipt.get("discord_message_id")):
                raise ValueError(f"Receipt mismatch: {rid}")
        elif (ATTEMPTS / f"{rid}.json").exists():
            raise RuntimeError(f"Unresolved delivery attempt: {rid}; reconcile before retry")
        else:
            pending.append(payload)
    return pending


def publish_all() -> int:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not configured")
    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        raise ValueError("DISCORD_WEBHOOK_URL is not a Discord webhook URL")

    OUTBOX.mkdir(parents=True, exist_ok=True)
    SENT.mkdir(parents=True, exist_ok=True)
    pending = check_queue()
    posted = 0

    for payload in pending:
        release_id = safe_release_id(payload)
        with tempfile.TemporaryDirectory(prefix="estlela-discord-") as temp_dir:
            image_path = Path(temp_dir) / f"{release_id}.png"
            render_update(payload, image_path)
            ATTEMPTS.mkdir(parents=True, exist_ok=True)
            intent = ATTEMPTS / f"{release_id}.json"
            intent.write_text(json.dumps({
                "release_id": release_id,
                "content_hash": canonical_hash(payload),
                "started_at": datetime.now(timezone.utc).isoformat(),
                "run_id": os.environ.get("GITHUB_RUN_ID", "manual"),
            }, indent=2) + "\n")
            checkpoint(intent, f"Reserve ESTLELA Discord delivery {release_id}")
            message_id = send_to_discord(webhook_url, payload, image_path)
            marker = write_marker(payload, message_id)
            checkpoint(marker, "Record ESTLELA Discord deliveries")
            print(f"Posted {release_id}; marker: {marker.name}")
            posted += 1

    if posted == 0:
        print("No unsent ESTLELA updates found.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--render-only", type=Path, help="Validate and render one payload without posting")
    parser.add_argument("--output", type=Path, default=Path("/tmp/estlela-update.png"))
    args = parser.parse_args()

    if args.check_only:
        print(f"Validated queue: {len(check_queue())} pending")
        return 0
    if args.render_only:
        render_only(args.render_only, args.output)
        return 0
    return publish_all()


if __name__ == "__main__":
    raise SystemExit(main())
