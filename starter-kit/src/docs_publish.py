#!/usr/bin/env python3
"""Local-only, reviewed private-to-public Markdown export and knowledge indexing."""
import argparse
import difflib
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import time

LIMIT = 2 * 1024 * 1024
MARKER = re.compile(r"<!--\s*(private:start|private:end|public-only:\s*.*?)\s*-->", re.S)
MAC = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])")
IP = re.compile(r"(?<![\w:])(?:\d{1,3}\.){3}\d{1,3}(?!\w|\.\d)|"
                r"(?<![\w:])(?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]+(?:%[\w-]+)?")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
IDENTIFIER = re.compile(
    r"(?i)(?:https?://)?(?:[a-z0-9-]+\.)+[a-z0-9-]+\.ts\.net"
    r"|https?://(?:ntfy\.sh|[a-z0-9.-]*omada[a-z0-9.-]*)/[^\s<>`\"')]+")
SECRET = re.compile(
    r"(?i)(?:gh[pousr]_[a-z0-9]{12,}|github_pat_[a-z0-9_]{12,}"
    r"|sk-[a-z0-9_-]{16,}|tskey-[a-z0-9_-]{12,}"
    r"|AKIA[A-Z0-9]{16}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"|-----BEGIN (?:[A-Z ]*PRIVATE KEY|OPENSSH PRIVATE KEY)-----)")
ASSIGNMENT = re.compile(
    r"(?im)(\b(?:password|passwd|token|api[_-]?key|secret|ntfy_topic|"
    r"omada[_-]?(?:user|site|controller|id))\b\s*[:=]\s*)[^\n]+")
EXAMPLE_NETS = tuple(ipaddress.ip_network(s) for s in (
    "192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"))


class Refusal(ValueError):
    """A generic error safe to include in a shared report."""


def fail():
    raise Refusal("Documentation input, permissions, review or privacy validation failed")


def secure(path, directory=False):
    path = Path(path).absolute()
    for parent in (path,) + tuple(path.parents):
        st = parent.lstat()
        if stat.S_ISLNK(st.st_mode):
            fail()
        if parent == path:
            if (st.st_uid != os.getuid() or st.st_mode & 0o077
                    or not (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode))):
                fail()
        elif not stat.S_ISDIR(st.st_mode) or (
                st.st_mode & 0o022 and not (parent == Path("/tmp") and st.st_mode & stat.S_ISVTX)):
            fail()
    return path


def read(path, private=False):
    path = Path(path)
    if private:
        secure(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > LIMIT:
        fail()
    return path.read_text(encoding="utf-8")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write(path, text):
    path = Path(path)
    if path.is_symlink():
        fail()
    fd, tmp = tempfile.mkstemp(prefix=".docs-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def encoded(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def relative(value):
    if not isinstance(value, str):
        fail()
    path = PurePosixPath(value)
    if (path.is_absolute() or not path.parts or "\\" in value
            or any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", p) or p in (".", "..")
                   for p in path.parts) or path.suffix.lower() != ".md"):
        fail()
    return path


def beneath(root, name):
    name = relative(name)
    path = root.joinpath(*name.parts)
    for item in (path,) + tuple(path.parents):
        if item == root:
            break
        if item.is_symlink():
            fail()
    if not path.resolve().is_relative_to(root):
        fail()
    return path


def load(config_path):
    config = json.loads(read(config_path, private=True))
    required = {"private_root", "public_root", "stage", "redaction_map", "documents"}
    if not isinstance(config, dict) or set(config) != required:
        fail()
    for key in required - {"documents"}:
        value = config[key]
        if not isinstance(value, str) or not Path(value).is_absolute() or ".." in Path(value).parts:
            fail()
        config[key] = Path(value).absolute()
    for key in ("private_root", "stage"):
        secure(config[key], directory=True)
    public = config["public_root"]
    if public.is_symlink() or public.resolve() != public or not public.is_dir():
        fail()
    roots = [config[k] for k in ("private_root", "public_root", "stage")]
    if any(a.is_relative_to(b) for i, a in enumerate(roots) for j, b in enumerate(roots) if i != j):
        fail()
    if (Path(config_path).absolute().is_relative_to(public)
            or config["redaction_map"].is_relative_to(public)):
        fail()
    mapping = json.loads(read(config["redaction_map"], private=True))
    if (not isinstance(mapping, dict) or not mapping
            or any(not isinstance(k, str) or len(k) < 3 or not isinstance(v, str)
                   or not v or k.casefold() in v.casefold() for k, v in mapping.items())):
        fail()
    # A replacement must never reintroduce a different private term.
    if any(k.casefold() in v.casefold() for k in mapping for v in mapping.values()):
        fail()
    docs = config["documents"]
    if not isinstance(docs, dict) or not docs or len(set(docs.values())) != len(docs):
        fail()
    for source, target in docs.items():
        beneath(config["private_root"], source)
        beneath(public, target)
        if scan(target, mapping):
            fail()
    config["mapping"] = mapping
    config["config_hash"] = sha(read(config_path, private=True))
    config["map_hash"] = sha(read(config["redaction_map"], private=True))
    return config


def address(match):
    value = match.group()
    try:
        addr = ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        # Invalid address-shaped text is still unsafe to publish.
        return True
    return not (addr.is_loopback or addr.is_unspecified
                or any(addr.version == net.version and addr in net for net in EXAMPLE_NETS))


def scan(text, mapping):
    findings = set()
    for term in mapping:
        for match in re.finditer(re.escape(term), text, re.I):
            findings.add(text.count("\n", 0, match.start()) + 1)
    for pattern in (MAC, EMAIL, IDENTIFIER, SECRET):
        for match in pattern.finditer(text):
            findings.add(text.count("\n", 0, match.start()) + 1)
    for match in IP.finditer(text):
        if address(match):
            findings.add(text.count("\n", 0, match.start()) + 1)
    for match in ASSIGNMENT.finditer(text):
        value = match.group()[len(match.group(1)):].strip(" \t`\"'")
        if value not in ("", "x", "xxxxxxxx"):
            findings.add(text.count("\n", 0, match.start()) + 1)
    return sorted(findings)


def render(text, mapping):
    if text.startswith("---\n"):
        header, sep, tail = text[4:].partition("\n---\n")
        if not sep:
            fail()
        if re.search(r"(?im)^publish:\s*false\s*$", header):
            return None
        text = "---\n" + header + "\n---\n" + tail
    if re.search(r"<!--\s*(?:private|public-only)\b", MARKER.sub("", text)):
        fail()
    output, offset, private = [], 0, False
    for match in MARKER.finditer(text):
        if not private:
            output.append(text[offset:match.start()])
        tag = match.group(1)
        if tag == "private:start":
            if private:
                fail()
            private = True
        elif tag == "private:end":
            if not private:
                fail()
            private = False
        else:
            if private:
                fail()
            output.append(tag.partition(":")[2].strip())
        offset = match.end()
    if private:
        fail()
    output.append(text[offset:])
    text = "".join(output)
    if re.search(r"<!--\s*(?:private|public-only)\b", text):
        fail()
    for key in sorted(mapping, key=len, reverse=True):
        text = re.sub(re.escape(key), lambda _: mapping[key], text, flags=re.I)
    if "PRIVATE KEY-----" in text:
        fail()
    text = MAC.sub("xx:xx:xx:xx:xx:xx", text)
    text = IP.sub(lambda m: ("x.x.x.x" if "." in m.group() else "xxxx:xxxx:xxxx:xxxx::x")
                  if address(m) else m.group(), text)
    for pattern in (EMAIL, IDENTIFIER, SECRET):
        text = pattern.sub("xxxxxxxx", text)
    text = ASSIGNMENT.sub(lambda m: m.group(1) + "xxxxxxxx", text)
    if scan(text, mapping):
        fail()
    return text


def prepare(config):
    outputs, sources = {}, {}
    for source, target in config["documents"].items():
        text = read(beneath(config["private_root"], source), private=True)
        sources[source] = sha(text)
        value = render(text, config["mapping"])
        if value is not None:
            outputs[target] = value
    return outputs, sources


def manifest(config, sources, outputs):
    return {"schema": 1, "config_hash": config["config_hash"], "map_hash": config["map_hash"],
            "sources": sources, "outputs": {name: sha(text) for name, text in outputs.items()}}


def stage(config):
    outputs, sources = prepare(config)
    directory = config["stage"] / "rendered"
    directory.mkdir(mode=0o700)  # Exclusive: preserve the previous review instead of overwriting it.
    diff, baseline = [], {}
    for name, text in outputs.items():
        dest = beneath(directory, name)
        dest.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        write(dest, text)
        current = beneath(config["public_root"], name)
        old = read(current) if current.exists() else ""
        baseline[name] = sha(old) if current.exists() else None
        # Even removed lines in a diff may contain identifying data.
        old = render(old, config["mapping"]) or ""
        diff.extend(difflib.unified_diff(old.splitlines(True), text.splitlines(True),
                                         fromfile="public/" + name, tofile="staged/" + name))
    write(config["stage"] / "review.diff", "".join(diff))
    record = manifest(config, sources, outputs)
    record["baseline"] = baseline
    write(config["stage"] / "manifest.json", encoded(record))
    return len(outputs)


def apply(config, reviewed=False):
    if not reviewed:
        fail()
    outputs, sources = prepare(config)
    expected = manifest(config, sources, outputs)
    staged = json.loads(read(config["stage"] / "manifest.json", private=True))
    baseline = staged.pop("baseline", None)
    if staged != expected or not isinstance(baseline, dict) or set(baseline) != set(outputs):
        fail()
    for name, text in outputs.items():
        if read(beneath(config["stage"] / "rendered", name), private=True) != text:
            fail()
        current = beneath(config["public_root"], name)
        if baseline[name] != (sha(read(current)) if current.exists() else None):
            fail()
    # Inspect the projected public tree, not just previously approved hashes.
    for name in public_docs(config["public_root"]) | set(outputs):
        text = outputs[name] if name in outputs else read(beneath(config["public_root"], name))
        if scan(name + "\n" + text, config["mapping"]):
            fail()
    for name, text in outputs.items():
        dest = beneath(config["public_root"], name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        write(dest, text)
    if audit(config):
        fail()
    expected["vetted_at"] = time.time()
    write(config["stage"] / "vetted.json", encoded(expected))
    return len(outputs)


def public_docs(root):
    # Public coverage includes all non-hidden Markdown, not just mapped outputs.
    return {str(p.relative_to(root)) for p in root.rglob("*")
            if p.suffix.lower() == ".md" and not any(part.startswith(".")
                                                    for part in p.relative_to(root).parts)}


def audit(config):
    findings = []
    for number, name in enumerate(sorted(public_docs(config["public_root"])), 1):
        lines = scan(read(beneath(config["public_root"], name)), config["mapping"])
        if scan(name, config["mapping"]):
            lines = [0] + lines
        if lines:
            findings.append({"file": number, "lines": lines})
    return findings


def assess(config_path, now=None):
    now = time.time() if now is None else now
    try:
        config = load(config_path)
        if audit(config):
            fail()
        outputs, sources = prepare(config)
        vetted = json.loads(read(config["stage"] / "vetted.json", private=True))
        stamp = vetted.pop("vetted_at", None)
        if type(stamp) not in (int, float) or not 0 <= now - stamp <= 86400:
            fail()
        if vetted != manifest(config, sources, outputs):
            fail()
        if set(outputs) != public_docs(config["public_root"]):
            fail()
        for name, text in outputs.items():
            if read(beneath(config["public_root"], name)) != text:
                fail()
        return {"health": "healthy", "checked_at": now, "expires_at": stamp + 86400,
                "vetted_count": len(outputs)}
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        return {"health": "attention", "checked_at": now, "vetted_count": 0}


def index(config):
    rows = []
    for tier, key in (("private", "private_root"), ("public", "public_root")):
        root = config[key]
        for name in sorted(public_docs(root)):
            path = beneath(root, name)
            text = read(path, private=tier == "private")
            title = next((line[2:].strip() for line in text.splitlines() if line.startswith("# ")), "")
            rows.append({"tier": tier, "path": str(path), "title": title, "sha256": sha(text),
                         "modified_at": path.stat().st_mtime, "knowledge_only": True})
    write(config["stage"] / "knowledge-index.json", encoded({"schema": 1, "documents": rows}))
    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "apply", "check", "audit", "index"))
    parser.add_argument("--config", required=True)
    parser.add_argument("--reviewed", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            result = assess(args.config)
            print("Documentation publishing: " + result["health"])
            return 0 if result["health"] == "healthy" else 1
        config = load(args.config)
        if args.action == "audit":
            findings = audit(config)
            write(config["stage"] / "audit.json", encoded({"findings": findings}))
            print(encoded({"privacy": "attention" if findings else "no-known-patterns",
                           "findings": findings}), end="")
            return 1 if findings else 0
        count = (apply(config, args.reviewed) if args.action == "apply" else
                 stage(config) if args.action == "stage" else index(config))
        print(f"Documentation {args.action}: {count} file(s); local only")
        return 0
    except (OSError, ValueError, TypeError, AttributeError, RecursionError):
        print("Documentation operation refused: input, permissions, privacy or review invalid",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
