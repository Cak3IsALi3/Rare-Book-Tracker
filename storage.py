"""
storage.py -- Tracks which listings have already been emailed about (so the
same item never triggers a second alert) and records a timestamp for each
run. Both files live under data/ and are committed back to the repo by the
GitHub Actions workflow after every run.
"""

import json
import os
from datetime import datetime, timezone

SEEN_FILE = os.path.join("data", "seen_items.json")
STATUS_FILE = os.path.join("data", "last_run.json")


def load_seen():
    if not os.path.exists(SEEN_FILE):
        return {}
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, sort_keys=True)


def write_status(books_checked, new_matches, errors=None):
    """
    Writes a small run summary that changes on *every* run, even when
    nothing new is found. That matters because GitHub auto-disables
    scheduled workflows after 60 days without a commit -- a quiet month
    where no book matches would otherwise mean no commits, and eventually
    the schedule would stop firing. This file's changing timestamp is what
    the workflow commits to keep itself alive.
    """
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "last_run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "books_checked": books_checked,
            "new_matches": new_matches,
            "errors": errors or [],
        }, f, indent=2)
