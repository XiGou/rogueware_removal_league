#!/usr/bin/env python3
"""Convert a submission issue form event into one submission JSON file."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_FILE = ROOT / "data" / "projects.json"
SUBMISSIONS_DIR = ROOT / "data" / "submissions"
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")


def clean_value(value: str) -> str:
    cleaned = value.strip()
    if cleaned == "_No response_":
        return ""
    return cleaned


def parse_issue_form(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current
        if current:
            sections[current] = clean_value("\n".join(buffer))
        buffer = []

    for line in body.splitlines():
        if line.startswith("### "):
            flush()
            current = line[4:].strip()
        elif current:
            buffer.append(line)

    flush()
    return sections


def require(sections: dict[str, str], label: str) -> str:
    value = clean_value(sections.get(label, ""))
    if not value:
        raise SystemExit(f"Missing required issue field: {label}")
    return value


def parse_steps(raw_steps: str) -> list[str]:
    steps: list[str] = []
    for raw_line in raw_steps.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^(?:[-*]|\d+[.)])\s+", "", line).strip()
        if line:
            steps.append(line)

    if not 1 <= len(steps) <= 6:
        raise SystemExit("Key steps must contain 1 to 6 non-empty items")
    return steps


def validate_url(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SystemExit(f"{label} must be an http(s) URL")
    return value


def validate_date(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise SystemExit("Completion date must use YYYY-MM-DD") from exc
    return value


def safe_name(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return safe[:32] or "runner"


def load_project_slugs() -> set[str]:
    projects = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {project["slug"] for project in projects}


def write_output(key: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output_file:
            output_file.write(f"{key}={value}\n")
    print(f"{key}={value}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: issue_to_submission.py <github-event-path>")

    event = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    issue = event["issue"]
    sections = parse_issue_form(issue.get("body") or "")

    project_slug = require(sections, "Project slug")
    if not SLUG_RE.match(project_slug):
        raise SystemExit("Project slug must use lowercase letters, numbers, and hyphens")
    if project_slug not in load_project_slugs():
        raise SystemExit(f"Unknown project slug: {project_slug}")

    submission_dir = SUBMISSIONS_DIR / project_slug
    if not submission_dir.is_dir():
        raise SystemExit(f"Missing submission directory: {submission_dir}")

    name = require(sections, "Name or handle")
    seconds_text = require(sections, "Total time in seconds")
    if not seconds_text.isdigit() or int(seconds_text) <= 0:
        raise SystemExit("Total time in seconds must be a positive integer")
    seconds = int(seconds_text)

    date = validate_date(require(sections, "Completion date"))
    issue_url = validate_url(issue["html_url"], "Issue URL")
    steps = parse_steps(require(sections, "Key steps"))
    message = require(sections, "Completion quote")

    submission = {
        "name": name,
        "time_seconds": seconds,
        "message": message,
        "evidence_url": issue_url,
        "issue_url": issue_url,
        "steps": steps,
        "date": date,
    }

    file_name = f"{date}-{seconds:06d}-{safe_name(name)}-issue-{issue['number']}.json"
    output_path = submission_dir / file_name
    output_path.write_text(json.dumps(submission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    relative_path = output_path.relative_to(ROOT)
    branch = f"submission/issue-{issue['number']}-{project_slug}"
    title = f"Add submission: {project_slug} / {name} - {seconds}s"

    write_output("path", str(relative_path))
    write_output("branch", branch)
    write_output("commit_message", title)
    write_output("pr_title", title)
    write_output("issue_number", str(issue["number"]))


if __name__ == "__main__":
    main()
