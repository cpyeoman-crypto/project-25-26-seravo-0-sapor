#!/usr/bin/env python3
"""Check local project evidence without executing report content or probing networks."""
import argparse
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path

import docs_publish

ROOT = Path(__file__).resolve().parent.parent
GATES = ("interface", "auth", "privacy", "compatibility", "verification", "approval")
STATUSES = ("planned", "blocked", "implemented", "verified")


def read_json(path):
    with Path(path).open("rb") as stream:
        text = stream.read(1024 * 1024 + 1)
    if len(text) > 1024 * 1024:
        raise ValueError("evidence too large")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return value


def fresh(stamp, now, max_age):
    try:
        return (type(stamp) in (int, float) and math.isfinite(stamp)
                and 0 <= now - stamp <= max_age)
    except OverflowError:
        return False


def snapshot(repo):
    """Fingerprint tracked and non-ignored new files, not just the last commit."""
    repo = Path(repo).resolve()
    result = subprocess.run(["git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                            check=True, capture_output=True, timeout=30)
    paths = sorted(set(p for p in result.stdout.decode("utf-8").split("\0") if p))
    if not paths:
        raise ValueError("no tracked project files")
    digest, docs = hashlib.sha256(), {}
    for name in paths:
        path = repo / name
        if path.is_symlink() or not path.resolve().is_relative_to(repo):
            raise ValueError("unsafe tracked path")
        content = path.read_bytes()
        digest.update(name.encode() + b"\0" + hashlib.sha256(content).digest())
        if path.suffix.lower() == ".md":
            docs[name] = hashlib.sha256(content).hexdigest()
    return digest.hexdigest(), docs


def evaluate(config, evidence, revision, docs, now):
    max_age = config.get("max_age_seconds", 86400)
    required = config.get("required_checks")
    connectors = config.get("connectors")
    if (type(max_age) not in (int, float) or not 0 < max_age <= 86400
            or not isinstance(required, list) or not required
            or any(not isinstance(x, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", x) for x in required)
            or len(set(required)) != len(required) or not isinstance(connectors, dict)
            or not {"ntfy", "rave"} <= connectors.keys()):
        raise ValueError("invalid monitoring configuration")
    checks = evidence.get("checks", {})
    reviews = evidence.get("docs", {})
    records = evidence.get("connectors", {})
    if not all(isinstance(x, dict) for x in (checks, reviews, records)):
        raise ValueError("invalid evidence")
    findings, check_rows, connector_rows, successes, expiries = [], [], [], [], []
    for index, name in enumerate(required, 1):
        record = checks.get(name)
        status = "missing"
        if isinstance(record, dict):
            status = record.get("status", "invalid")
            if status == "passed" and fresh(record.get("checked_at"), now, float("inf")):
                successes.append(record["checked_at"])
            if status not in ("passed", "pending", "failed"):
                status = "invalid"
            elif not fresh(record.get("checked_at"), now, max_age):
                status = "stale" if fresh(record.get("checked_at"), now, float("inf")) else "invalid"
            elif record.get("revision") != revision:
                status = "outdated"
            if status == "passed":
                expiries.append(record["checked_at"] + max_age)
        elif record is not None:
            status = "invalid"
        check_rows.append({"check": index, "status": status})
        if status != "passed":
            findings.append(f"check-{index}: {status}")
    review_paths = sorted(path for path, sha in docs.items() if reviews.get(path) != sha)
    obsolete = len(reviews.keys() - docs.keys())
    drift = len(review_paths) + obsolete
    if drift:
        findings.append(f"documentation: {drift} file(s) require review")
    for index, (name, policy) in enumerate(sorted(connectors.items()), 1):
        if not isinstance(policy, dict) or type(policy.get("implemented")) is not bool:
            raise ValueError("invalid connector policy")
        record = records.get(name, {})
        if not isinstance(record, dict):
            raise ValueError("invalid connector evidence")
        status = record.get("status", "planned")
        if status not in STATUSES:
            raise ValueError("invalid connector lifecycle")
        prerequisites = record.get("prerequisites", {})
        if not isinstance(prerequisites, dict):
            raise ValueError("invalid prerequisites")
        missing = [gate for gate in GATES if prerequisites.get(gate) is not True]
        if status in ("implemented", "verified") and (not policy["implemented"] or name == "rave"):
            status = "blocked"
            missing = sorted(set(missing) | {"interface", "verification"})
        if status == "verified" and (missing or record.get("revision") != revision
                                     or not fresh(record.get("checked_at"), now, max_age)):
            status = "blocked"
            missing = sorted(set(missing) | {"verification"})
        if status == "verified":
            expiries.append(record["checked_at"] + max_age)
        connector_rows.append({"connector": index, "status": status, "missing": missing})
        if status != "verified":
            findings.append(f"connector-{index}: {status}")
    return {
        "schema": 1, "checked_at": now, "revision": revision,
        "expires_at": min(expiries) if expiries else now,
        "health": "attention" if findings else "healthy",
        "last_successful_check": max(successes) if successes else None,
        "checks": check_rows, "documentation_review_count": drift,
        "documentation_review_paths": review_paths,
        "obsolete_documentation_approvals": obsolete,
        "connectors": connector_rows, "findings": findings,
    }


def run(repo, config_path, evidence_path, now=None):
    now = time.time() if now is None else now
    try:
        config = read_json(config_path)
        evidence = read_json(evidence_path)
        revision, docs = snapshot(repo)
        status = evaluate(config, evidence, revision, docs, now)
        publish_config = config.get("documentation_publish_config")
        publishing = (docs_publish.assess(publish_config, now, public_root=repo) if isinstance(publish_config, str)
                      else {"health": "unconfigured"})
        status["documentation_publishing"] = publishing
        if publishing["health"] != "healthy":
            status["health"] = "attention"
            status["findings"].append("documentation publishing: review required or unconfigured")
        else:
            status["expires_at"] = min(status["expires_at"], publishing["expires_at"])
        return status
    except (OSError, ValueError, TypeError, OverflowError, RecursionError, subprocess.SubprocessError):
        # Never reproduce untrusted report content, paths, or exception messages.
        return {"schema": 1, "checked_at": now, "health": "invalid",
                "last_successful_check": None, "findings": ["project evidence missing or invalid"]}


def summary(path, now=None):
    now = time.time() if now is None else now
    try:
        status = read_json(path)
        if (type(status.get("schema")) is not int or status["schema"] != 1
                or status.get("health") not in ("healthy", "attention", "invalid")
                or not fresh(status.get("checked_at"), now, 7200)):
            raise ValueError("invalid or stale status")
        checks = status.get("checks")
        connectors = status.get("connectors")
        if status["health"] == "invalid":
            return "Project: evidence missing or invalid", True
        if (not isinstance(checks, list) or not checks or not isinstance(connectors, list)
                or not connectors or type(status.get("documentation_review_count")) is not int
                or status["documentation_review_count"] < 0
                or not re.fullmatch(r"[0-9a-f]{64}", str(status.get("revision", "")))):
            raise ValueError("invalid status")
        passed = sum(row.get("status") == "passed" for row in checks)
        healthy = (status["health"] == "healthy" and passed == len(checks) and status["documentation_review_count"] == 0
                   and all(row.get("status") == "verified" and row.get("missing") == [] for row in connectors))
        stamp = status.get("last_successful_check")
        last = str(int(stamp)) if fresh(stamp, now, float("inf")) else "none"
        if last != "none" and not fresh(stamp, now, 86400):
            last += " (stale)"
        if last == "none":
            healthy = False
        expiry = status.get("expires_at")
        expired = type(expiry) not in (int, float) or not now <= expiry <= now + 86400
        if expired:
            healthy = False
        lines = [f"Project: {'healthy' if healthy else 'attention'}",
                 f"Monitoring run (epoch): {int(status['checked_at'])}",
                 f"Last successful check (epoch): {last}",
                 f"Checks: {passed}/{len(checks)} passed",
                 f"Documentation review needs: {status['documentation_review_count']}"]
        publishing = status.get("documentation_publishing", {"health": "unconfigured"})
        if not isinstance(publishing, dict) or publishing.get("health") != "healthy":
            healthy = False
            lines[0] = "Project: attention"
            lines.append("Documentation publishing: unconfigured or review required")
        else:
            if (not fresh(publishing.get("checked_at"), now, 7200)
                    or type(publishing.get("expires_at")) not in (int, float)
                    or not now <= publishing["expires_at"] <= now + 86400):
                healthy = False
                lines[0] = "Project: attention"
                lines.append("Documentation publishing: evidence expired")
            else:
                lines.append("Documentation publishing: vetted")
        if expired:
            lines.append("Evidence freshness: expired or invalid")
        for i, row in enumerate(checks, 1):
            state = row.get("status")
            if state not in ("passed", "pending", "failed", "missing", "stale", "invalid", "outdated"):
                raise ValueError("invalid check")
            lines.append(f"Check-{i}: {state}")
        for i, row in enumerate(connectors, 1):
            if row.get("status") not in STATUSES or not isinstance(row.get("missing"), list):
                raise ValueError("invalid connector")
            if any(gate not in GATES for gate in row["missing"]):
                raise ValueError("invalid prerequisite")
            gates = [gate for gate in GATES if gate in row["missing"]]
            lines.append(f"Connector-{i}: {row['status']}; prerequisites outstanding: {', '.join(gates) or 'none'}")
        return "\n".join(lines), not healthy
    except (OSError, ValueError, TypeError, AttributeError, OverflowError, RecursionError):
        return "Project: monitoring data missing, stale or invalid", True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--config", default=str(ROOT / "config/maintenance.example.json"))
    parser.add_argument("--evidence", default=str(ROOT / "state/maintenance_evidence.json"))
    parser.add_argument("--out", default=str(ROOT / "state/project_status.json"))
    args = parser.parse_args()
    status = run(args.repo, args.config, args.evidence)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out)
    print("Project monitoring: " + status["health"])
    return 0 if status["health"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
