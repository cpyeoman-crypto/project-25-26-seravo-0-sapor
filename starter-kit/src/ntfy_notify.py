#!/usr/bin/env python3
"""One look and one delivery path for every push notification (ntfy).

Standard library only. Messages use ntfy's JSON publish API so titles and bodies
may carry UTF-8, delivery is retried, and messages are spooled to disk when the
server is unreachable so a network blip does not drop a report.

Safe by default: with no NTFY_TOPIC configured, or with NTFY_DRY_RUN=1, the
message is printed and nothing is sent.
"""
import json
import os
import socket
import time
import urllib.error
import urllib.request
from collections import namedtuple
from datetime import datetime
from pathlib import Path

DEFAULT_SERVER = "https://ntfy.sh"
DEFAULT_ENV_FILE = "./config/fleet.env"
MAX_MESSAGE_BYTES = 3800
RETRY_DELAYS = (0, 2, 6)
SPOOL_MAX_LINES = 200

Style = namedtuple("Style", "emoji tags priority label")

# kind -> look and default priority (1 min ... 3 default ... 5 urgent)
STYLES = {
    "client_connect": Style("🟢", ["white_check_mark", "electric_plug"], 3, "CLIENT CONNECT"),
    "client_disconnect": Style("🔴", ["x", "electric_plug"], 3, "CLIENT DISCONNECT"),
    "node_up": Style("🛰️", ["satellite", "white_check_mark"], 3, "NODE ONLINE"),
    "node_down": Style("📡", ["satellite", "warning"], 4, "NODE OFFLINE"),
    "wan_drop": Style("🚨", ["rotating_light", "warning"], 5, "WAN DROP"),
    "wan_restore": Style("🌐", ["white_check_mark", "globe_with_meridians"], 3, "WAN RESTORE"),
    "new_device": Style("🆕", ["rotating_light", "new"], 4, "UNKNOWN DEVICE"),
    "healer": Style("🔧", ["wrench", "zap"], 4, "FLEET HEALING"),
    "daily": Style("🩺", ["stethoscope", "robot"], 3, "DAILY STATUS"),
    "morning": Style("☀️", ["sun_with_face", "globe_with_meridians"], 3, "MORNING BRIEFING"),
    "stale": Style("🔭", ["telescope", "satellite"], 3, "ONLINE BUT NOT REPORTING"),
    "test": Style("🧪", ["test_tube"], 2, "TEST"),
    "error": Style("⚠️", ["warning", "sos"], 4, "REPORT FAILURE"),
}
PRIORITY_NAMES = {"min": 1, "low": 2, "default": 3, "high": 4, "max": 5, "urgent": 5}


def _env_file_value(name, path=None):
    path = path or os.environ.get("FLEET_ENV", DEFAULT_ENV_FILE)
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key == name:
                return value.strip().strip("\"'")
    except OSError:
        pass
    return None


def setting(name, default=None):
    return os.environ.get(name) or _env_file_value(name) or default


def topic():
    return setting("NTFY_TOPIC")


def server():
    return setting("NTFY_SERVER", DEFAULT_SERVER).rstrip("/")


def site_name():
    return setting("SITE_NAME", "my-network")


def now_stamp():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def bullets(items):
    return "\n".join(f"- {item}" for item in items)


def fields(pairs):
    """Bold-key / code-value lines, skipping empty values."""
    return "\n".join(f"- **{k}** `{v}`" for k, v in pairs if v not in (None, ""))


def section(heading, body):
    return f"**{heading}**\n{body}" if body else ""


def bar(value, total=100.0, width=10):
    """Unicode meter, e.g. ▰▰▰▱▱▱▱▱▱▱ for 30 of 100."""
    try:
        filled = round(max(0.0, min(1.0, float(value) / float(total))) * width)
    except (TypeError, ValueError, ZeroDivisionError):
        filled = 0
    return "▰" * filled + "▱" * (width - filled)


def compose(kind, headline=None, body="", details=None, footer=True):
    style = STYLES[kind]
    parts = [f"## {style.emoji} {headline or style.label}"]
    if body:
        parts.append(body.strip())
    if details:
        parts.append(fields(details.items() if isinstance(details, dict) else details))
    if footer:
        parts.append(f"*{site_name()} · {socket.gethostname()} · {now_stamp()}*")
    return "\n\n".join(part for part in parts if part)


def truncate(message, limit=MAX_MESSAGE_BYTES):
    raw = message.encode("utf-8")
    if len(raw) <= limit:
        return message
    cut = raw[:limit].decode("utf-8", "ignore")
    return cut.rsplit("\n", 1)[0] + "\n\n*…truncated*"


def _priority(value, default):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    return PRIORITY_NAMES.get(str(value).lower(), default)


def _spool_path():
    return Path(setting("NTFY_SPOOL", f"/var/tmp/fleet-kit-ntfy-spool-{os.getuid()}.jsonl"))


def _post(payload, timeout=10):
    request = urllib.request.Request(
        server() + "/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    token = setting("NTFY_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise urllib.error.HTTPError(request.full_url, response.status, "rejected", None, None)


def _spool(payload):
    path = _spool_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        lines.append(json.dumps(payload))
        tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
        tmp.write_text("\n".join(lines[-SPOOL_MAX_LINES:]) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[-] Unable to spool message: {exc}")


def flush_spool():
    """Re-send spooled messages; keep whatever still fails. Returns the number delivered."""
    path = _spool_path()
    if not path.exists():
        return 0
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    except OSError:
        return 0
    remaining, delivered = [], 0
    for index, line in enumerate(lines):
        try:
            _post(json.loads(line))
            delivered += 1
        except ValueError:
            continue  # a corrupt line must not block every later message
        except (urllib.error.URLError, OSError):
            remaining = lines[index:]
            break
    try:
        if remaining:
            path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            path.unlink()
    except OSError:
        pass
    return delivered


def build_payload(kind, body="", *, headline=None, title=None, details=None,
                  priority=None, tags=None, topic_name=None, click=None, preformatted=False):
    style = STYLES[kind]
    message = body if preformatted else compose(kind, headline, body, details)
    payload = {
        "topic": topic_name or topic() or "",
        "title": title or f"{site_name()} · {headline or style.label}",
        "message": truncate(message),
        "priority": _priority(priority, style.priority),
        "tags": list(tags) if tags else list(style.tags),
        "markdown": True,
    }
    if click:
        payload["click"] = click
    return payload


def send(kind, body="", *, sleep=time.sleep, **kwargs):
    """Publish one styled message. Returns True when accepted (or printed in dry-run)."""
    payload = build_payload(kind, body, **kwargs)
    if os.environ.get("NTFY_DRY_RUN") == "1" or not payload["topic"]:
        print(f"[dry-run] ntfy priority={payload['priority']} title={payload['title']!r}\n{payload['message']}\n")
        return True
    try:
        flush_spool()
    except Exception:
        pass
    last_error = None
    for delay in RETRY_DELAYS:
        if delay:
            sleep(delay)
        try:
            _post(payload)
            return True
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
    print(f"[-] ntfy delivery failed ({last_error}); message spooled for retry.")
    _spool(payload)
    return False


if __name__ == "__main__":
    ok = send("test", "If you can read this on your phone, delivery works.", headline="TEST")
    raise SystemExit(0 if ok else 1)
