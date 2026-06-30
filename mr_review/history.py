"""MR review history tracking.

File format:
    <MR#>  <URL>
           <date>  <action> : <patch_count> patches, <conflict_count> conflicts
           <date>  <action> : <patch_count> patches, <conflict_count> conflicts
    <MR#>  <URL>
           ...

MR entries start at column 0; action lines are indented to align
with the URL on the header line.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from .config import Config

console = Console()

HISTORY_DIR = Path.home() / ".data" / "mr-review"
HISTORY_FILE = HISTORY_DIR / "mr-review-history.log"


def _ensure_history_file() -> Path:
    """Ensure the history directory and file exist."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.touch()
    return HISTORY_FILE


def _get_mr_url(mr_number: str) -> str:
    """Build the MR URL from .git/config origin."""
    git_config = Path(".git/config")
    if not git_config.exists():
        return ""

    url = ""
    in_origin = False
    for line in git_config.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("[remote"):
            in_origin = '"origin"' in stripped
        elif in_origin and "url" in stripped and "=" in stripped:
            url = stripped.split("=", 1)[1].strip()
            break

    if not url:
        return ""

    # git@gitlab.com:redhat/rhel/src/kernel/rhel-10.git → https URL
    url = re.sub(r"^.*@", "", url)      # strip git@
    url = re.sub(r"\.git$", "", url)     # strip .git
    url = url.replace(":", "/", 1)       # colon → slash
    return f"https://{url}/-/merge_requests/{mr_number}"


def _find_mr_line(lines: list[str], mr_number: str) -> Optional[int]:
    """Find the line index where an MR entry starts (0-based).

    MR entries start with the MR number at the beginning of the line.
    """
    pattern = re.compile(rf"^{re.escape(mr_number)}\b")
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def _find_next_mr_line(lines: list[str], after: int) -> Optional[int]:
    """Find the next MR header line after position 'after'."""
    for i in range(after + 1, len(lines)):
        if lines[i] and lines[i][0] not in (" ", "\t"):
            return i
    return None


def update_history(
    mr_number: str,
    action: str,
    patch_count: int = 0,
    conflict_count: int = 0,
):
    """Record an MR action in the history file."""
    hfile = _ensure_history_file()
    url = _get_mr_url(mr_number)
    now = datetime.now().strftime("%a %b %e %I:%M:%S %p %Z %Y")

    # Padding: MR number field width = len(mr_number) + 2
    fldwid = len(mr_number) + 2
    spc = " " * fldwid
    mridpad = mr_number.ljust(fldwid)

    action_line = f"{spc}{now}  {action}"
    if patch_count:
        action_line += f" : {patch_count} patches, {conflict_count} conflicts"

    lines = hfile.read_text().splitlines()
    mr_line = _find_mr_line(lines, mr_number)

    if mr_line is None:
        # New MR: append header + action
        with hfile.open("a") as f:
            f.write(f"{mridpad}{url}\n")
            f.write(f"{action_line}\n")
    else:
        # Existing MR: insert action before next MR entry
        next_mr = _find_next_mr_line(lines, mr_line)
        if next_mr is not None:
            lines.insert(next_mr, action_line)
        else:
            lines.append(action_line)
        hfile.write_text("\n".join(lines) + "\n")


def view_history_for_mr(mr_number: str) -> Optional[str]:
    """Return the history text for a specific MR, or None if not found."""
    hfile = _ensure_history_file()
    lines = hfile.read_text().splitlines()
    mr_line = _find_mr_line(lines, mr_number)

    if mr_line is None:
        return None

    next_mr = _find_next_mr_line(lines, mr_line)
    if next_mr is not None:
        block = lines[mr_line:next_mr]
    else:
        block = lines[mr_line:]

    return "\n".join(block)


def view_all_history() -> str:
    """Return the entire history file contents."""
    hfile = _ensure_history_file()
    return hfile.read_text()


def clear_history():
    """Clear all review history."""
    hfile = _ensure_history_file()
    hfile.write_text("")
