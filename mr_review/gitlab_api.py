"""Direct GitLab REST API client — no external dependencies.

Reads credentials from ~/.config/lab/lab.toml (shared with the lab CLI)
and provides the same data that the ``lab`` CLI subcommands return,
without the rate-limiter and subprocess overhead.

All HTTP is done via :mod:`urllib.request` (stdlib) so nothing beyond
the Python standard library is required.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional


# -------------------------------------------------------------------
# Configuration — reads the same lab.toml the lab CLI uses
# -------------------------------------------------------------------

_config_cache: Optional[dict[str, str]] = None


def _read_lab_toml() -> dict[str, str]:
    cfg_path = Path.home() / ".config" / "lab" / "lab.toml"
    if not cfg_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in cfg_path.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("[") and not line.startswith("#"):
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _cfg() -> dict[str, str]:
    global _config_cache
    if _config_cache is None:
        _config_cache = _read_lab_toml()
    return _config_cache


def get_token() -> Optional[str]:
    return _cfg().get("token")


def get_host() -> str:
    return _cfg().get("host", "https://gitlab.com")


def get_user() -> Optional[str]:
    return _cfg().get("user")


# -------------------------------------------------------------------
# Project-path helpers
# -------------------------------------------------------------------

def project_path_from_remote(remote_url: str) -> Optional[str]:
    """Extract the GitLab project path from a git remote URL.

    Handles both SSH and HTTPS forms::

        git@gitlab.com:group/sub/repo.git  →  group/sub/repo
        https://gitlab.com/group/sub/repo.git  →  group/sub/repo
    """
    m = re.match(r"git@[^:]+:(.+?)(?:\.git)?$", remote_url)
    if m:
        return m.group(1)
    m = re.match(r"https?://[^/]+/(.+?)(?:\.git)?/?$", remote_url)
    if m:
        return m.group(1)
    return None


def _encode(project_path: str) -> str:
    return urllib.parse.quote(project_path, safe="")


# -------------------------------------------------------------------
# Low-level HTTP
# -------------------------------------------------------------------

class GitLabAPIError(RuntimeError):
    """Raised when an API call fails."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def _request(
    endpoint: str,
    method: str = "GET",
    body: Optional[dict] = None,
    timeout: int = 30,
) -> Any:
    token = get_token()
    if not token:
        raise GitLabAPIError(
            "No GitLab token. Add one to ~/.config/lab/lab.toml under [core]."
        )
    url = f"{get_host().rstrip('/')}/api/v4{endpoint}"
    headers: dict[str, str] = {"PRIVATE-TOKEN": token}

    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitLabAPIError(
            f"GitLab API {exc.code} on {method} {endpoint}: {detail}",
            status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise GitLabAPIError(f"GitLab connection error: {exc.reason}") from exc


def _get_text(endpoint: str, timeout: int = 30) -> str:
    token = get_token()
    if not token:
        raise GitLabAPIError("No GitLab token configured.")
    url = f"{get_host().rstrip('/')}/api/v4{endpoint}"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitLabAPIError(
            f"GitLab API {exc.code}: {detail}", status=exc.code,
        ) from exc


def _paginated(endpoint: str, per_page: int = 100, timeout: int = 30) -> list:
    sep = "&" if "?" in endpoint else "?"
    results: list = []
    page = 1
    while True:
        chunk = _request(
            f"{endpoint}{sep}per_page={per_page}&page={page}",
            timeout=timeout,
        )
        if not chunk:
            break
        if isinstance(chunk, list):
            results.extend(chunk)
            if len(chunk) < per_page:
                break
        else:
            results.append(chunk)
            break
        page += 1
    return results


# -------------------------------------------------------------------
# Public MR operations
# -------------------------------------------------------------------

def list_mrs(
    project: str,
    state: str = "opened",
    author: Optional[str] = None,
    target_branch: Optional[str] = None,
) -> list[dict]:
    ep = f"/projects/{_encode(project)}/merge_requests?state={state}"
    if author:
        ep += f"&author_username={urllib.parse.quote(author)}"
    if target_branch:
        ep += f"&target_branch={urllib.parse.quote(target_branch)}"
    ep += "&order_by=created_at&sort=asc"
    return _paginated(ep)


def get_mr(project: str, iid: int) -> dict:
    return _request(f"/projects/{_encode(project)}/merge_requests/{iid}")


def get_mr_commits(project: str, iid: int) -> list[dict]:
    """Commits in the MR (newest-first from the API)."""
    return _paginated(
        f"/projects/{_encode(project)}/merge_requests/{iid}/commits"
    )


def get_mr_notes(project: str, iid: int) -> list[dict]:
    return _paginated(
        f"/projects/{_encode(project)}/merge_requests/{iid}/notes?sort=asc"
    )


def get_mr_approvals(project: str, iid: int) -> dict:
    return _request(
        f"/projects/{_encode(project)}/merge_requests/{iid}/approvals"
    )


def approve_mr(project: str, iid: int) -> dict:
    return _request(
        f"/projects/{_encode(project)}/merge_requests/{iid}/approve",
        method="POST",
    )


def unapprove_mr(project: str, iid: int) -> dict:
    return _request(
        f"/projects/{_encode(project)}/merge_requests/{iid}/unapprove",
        method="POST",
    )


def add_note(project: str, iid: int, body: str) -> dict:
    return _request(
        f"/projects/{_encode(project)}/merge_requests/{iid}/notes",
        method="POST",
        body={"body": body},
    )


def get_commit_patch(project: str, sha: str) -> str:
    """Fetch a commit as a git-format-patch style email from GitLab."""
    return _get_text(
        f"/projects/{_encode(project)}/repository/commits/{sha}.patch"
    )


def create_discussion(project: str, iid: int, body: str) -> dict:
    """Create a new discussion thread (blocking/unresolved) on the MR."""
    return _request(
        f"/projects/{_encode(project)}/merge_requests/{iid}/discussions",
        method="POST",
        body={"body": body},
    )


# -------------------------------------------------------------------
# Text formatting — produces output that existing parsers
# (Dependencies::, Approved By, etc.) can consume unchanged.
# -------------------------------------------------------------------

def format_mr_text(
    mr_data: dict,
    notes: list[dict],
    approvals: Optional[dict] = None,
    full: bool = False,
    comments_only: bool = False,
) -> str:
    """Render MR metadata + notes as plain text.

    Designed to be parse-compatible with ``lab mr show`` output so that
    code searching for ``Dependencies::`` or ``Approved By`` keeps working.
    """
    parts: list[str] = []

    if not comments_only:
        parts.append(f"!{mr_data['iid']} {mr_data.get('title', '')}")
        parts.append("")

    desc = mr_data.get("description") or ""
    if desc:
        parts.append(desc)
        parts.append("")

    for label in mr_data.get("labels", []):
        parts.append(label)
    if mr_data.get("labels"):
        parts.append("")

    if approvals:
        for entry in approvals.get("approved_by", []):
            user = entry.get("user", {})
            parts.append(f"Approved By: @{user.get('username', '?')}")
        if approvals.get("approved_by"):
            parts.append("")

    for note in notes:
        if note.get("system", False) and not full:
            continue
        author = note.get("author", {}).get("username", "?")
        created = note.get("created_at", "")
        body = note.get("body", "")
        parts.append(f"=== Comment by @{author} at {created} ===")
        parts.append(body)
        parts.append("")

    return "\n".join(parts)
