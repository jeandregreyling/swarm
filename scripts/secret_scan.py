#!/usr/bin/env python3
"""Fail when tracked files contain local secrets.

The scanner intentionally reports only paths and rule names. It must never echo
matched secret values into local logs or CI output.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SECRET_FILE_PATTERNS = (
    re.compile(r"(^|/)\.env($|\.)"),
    re.compile(r"(^|/).*_credentials\.json$"),
    re.compile(r"(^|/).*_token\.json$"),
    re.compile(r"(^|/).*_password\.txt$"),
    re.compile(r"(^|/).*tokens.*\.jsonl$"),
)

SECRET_VALUE_PATTERNS = {
    "github-token": re.compile(r"(github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}"),
    "groq-token": re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    "huggingface-token": re.compile(r"hf_[A-Za-z0-9]{20,}"),
    "openai-token": re.compile(r"(sk-proj-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{32,})"),
    "anthropic-token": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    "tavily-token": re.compile(r"tvly-[0-9A-Za-z_-]{20,}"),
    "slack-token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{20,}"),
    "sendgrid-token": re.compile(r"SG\.[0-9A-Za-z_-]{20,}\.[0-9A-Za-z_-]{20,}"),
    "private-key": re.compile(r"-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
}

ALLOWLIST_PATHS = {
    ".env.example",
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [p for p in result.stdout.decode("utf-8").split("\0") if p]


def is_secret_filename(path: str) -> bool:
    if path in ALLOWLIST_PATHS:
        return False
    return any(pattern.search(path) for pattern in SECRET_FILE_PATTERNS)


def main() -> int:
    failures: list[str] = []

    for relpath in tracked_files():
        if is_secret_filename(relpath):
            failures.append(f"{relpath}: tracked local secret filename")
            continue

        path = ROOT / relpath
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        for rule_name, pattern in SECRET_VALUE_PATTERNS.items():
            if pattern.search(text):
                failures.append(f"{relpath}: {rule_name}")

    if failures:
        print("Secret scan failed. Remove these tracked secrets or replace them with placeholders:")
        for failure in sorted(set(failures)):
            print(f"  - {failure}")
        return 1

    print("Secret scan passed: no tracked local secret files or known key patterns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
