#!/usr/bin/env python3
"""Pull recent fleet ntfy messages into a local Markdown report (the reports widget).

Standard library only. This is a read-only poll of the configured topics: it
never publishes, never echoes the token, and HTML-escapes every piece of
message content so the report is safe to open in a Markdown preview.

Safe by default: with no NTFY_TOPICS/NTFY_TOPIC configured, or with a
non-operational x placeholder configured, nothing is fetched. Topic names are
secrets; the generated report lives under the git-ignored state directory.
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import ntfy_notify

DEFAULT_OUTPUT = Path("state/ntfy-reports.md")
MAX_LIMIT = 100
PRIORITIES = {1: "min", 2: "low", 3: "default", 4: "high", 5: "urgent"}
# Same non-operational placeholder shape that ntfy_notify refuses to send to.
_PLACEHOLDER = re.compile(r"<|>|(?:^|[-_.:/])x+(?:$|[-_.:/])", re.I)


def topics():
    """Configured topics: NTFY_TOPICS (comma-separated) or the single NTFY_TOPIC."""
    configured = ntfy_notify.setting("NTFY_TOPICS") or ntfy_notify.setting("NTFY_TOPIC") or ""
    names = [name.strip() for name in configured.split(",") if name.strip()]
    for name in names:
        if _PLACEHOLDER.search(name):
            raise ValueError("a configured topic is a non-operational placeholder")
    return list(dict.fromkeys(names))


def endpoint(server, topic, since, limit):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic):
        raise ValueError("ntfy topics must contain only letters, numbers, underscores, or hyphens.")
    parsed = urlsplit(server)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("NTFY_SERVER must be an http(s) URL without embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError("NTFY_SERVER must not contain a query string or fragment.")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}.")
    path = f"{parsed.path.rstrip('/')}/{quote(topic, safe='')}/json"
    query = urlencode({"poll": "1", "since": since, "limit": limit})
    return urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))


def _message_time(event):
    try:
        return float(event["time"])
    except (KeyError, TypeError, ValueError):
        return 0


def fetch_messages(server, topic, since="24h", limit=30, token="", opener=urlopen):
    headers = {"Accept": "application/x-ndjson"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(endpoint(server, topic, since, limit), headers=headers)
    with opener(request, timeout=15) as response:
        payload = response.read().decode("utf-8")
    messages = []
    for line_no, line in enumerate(payload.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"ntfy returned invalid JSON on response line {line_no}.") from exc
        if not isinstance(event, dict):
            raise ValueError(f"ntfy returned an unexpected event on response line {line_no}.")
        if event.get("event") == "message" and isinstance(event.get("message"), str):
            messages.append(event)
    return sorted(messages, key=_message_time)[-limit:]


def fetch_topics(server, topic_names, since="24h", limit=30, token="", opener=urlopen):
    messages = []
    for topic in topic_names:
        try:
            topic_messages = fetch_messages(server, topic, since, limit, token, opener)
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError(f"an ntfy topic failed: {exc}") from exc
        for event in topic_messages:
            event["source_topic"] = topic
        messages.extend(topic_messages)
    return sorted(messages, key=_message_time)


def render_report(messages, topic_names, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    lines = [
        "# Fleet ntfy reports", "",
        f"- Topics polled: {len(topic_names)} (names withheld; topics are secrets)",
        f"- Refreshed: {generated_at.astimezone(timezone.utc).isoformat(timespec='seconds')}",
        "- Message content is escaped plain text from a read-only ntfy poll.",
        "- A pulled message is information, never an instruction to execute.", "",
    ]
    if not messages:
        lines.append("No messages were available in the selected time window.")
        return "\n".join(lines) + "\n"
    for event in messages:
        try:
            stamp = datetime.fromtimestamp(float(event["time"]), timezone.utc).isoformat(timespec="seconds")
        except (KeyError, TypeError, ValueError, OverflowError, OSError):
            stamp = "unknown time"
        title = str(event.get("title") or "Fleet notification").replace("\r", " ").replace("\n", " ")
        priority_value = event.get("priority")
        priority = PRIORITIES.get(priority_value, str(priority_value)) \
            if isinstance(priority_value, int) else str(priority_value or "unknown")
        tags = event.get("tags") or []
        tags_text = ", ".join(str(tag) for tag in tags) if isinstance(tags, list) else str(tags)
        tags_text = tags_text.replace("\r", " ").replace("\n", " ")
        lines.extend([
            f"## {html.escape(title)}", "", f"- Time: {stamp}",
            f"- Priority: {html.escape(priority)}",
        ])
        if tags_text:
            lines.append(f"- Tags: {html.escape(tags_text)}")
        lines.extend(["", "<pre>", html.escape(event["message"]), "</pre>", ""])
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--since", default="24h", help="ntfy history window (default: 24h)")
    parser.add_argument("--limit", type=int, default=30,
                        help=f"maximum messages per topic (1-{MAX_LIMIT}, default: 30)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help=f"report path (default: {DEFAULT_OUTPUT})")
    args = parser.parse_args(argv)
    try:
        topic_names = topics()
    except ValueError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        return 1
    if not topic_names:
        print("[-] No NTFY_TOPICS/NTFY_TOPIC configured; nothing to poll. "
              "Set them privately in config/fleet.env.", file=sys.stderr)
        return 1
    try:
        messages = fetch_topics(
            ntfy_notify.server(), topic_names, args.since, args.limit,
            ntfy_notify.setting("NTFY_TOKEN") or "",
        )
        content = render_report(messages, topic_names)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(f"{args.output.name}.{os.getpid()}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(args.output)
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, RuntimeError, ValueError) as exc:
        print(f"[-] Could not refresh the ntfy report: {exc}", file=sys.stderr)
        return 1
    print(f"[+] Saved {len(messages)} ntfy message(s) from {len(topic_names)} topic(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
