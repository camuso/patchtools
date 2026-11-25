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
    """Fetch a commit as a git-format-patch style email from GitLab.

    Only works for commits reachable from project branches.  Unmerged
    MR commits often 404 here — use :func:`download_mr_patches` instead.
    """
    return _get_text(
        f"/projects/{_encode(project)}/repository/commits/{sha}.patch"
    )


def _format_patch_date(iso_date: str) -> str:
    """Convert GitLab ISO date to an email Date: header value."""
    from datetime import datetime

    if not iso_date:
        return ""
    # e.g. 2026-11-23T01:29:22.000-05:00 or ...Z
    text = iso_date.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return iso_date
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _diffs_to_patch_body(diffs: list[dict]) -> str:
    """Turn GitLab compare/diff objects into a unified-diff body."""
    parts: list[str] = []
    for d in diffs:
        old = d.get("old_path") or d.get("new_path") or "unknown"
        new = d.get("new_path") or old
        parts.append(f"diff --git a/{old} b/{new}\n")
        if d.get("new_file"):
            mode = d.get("b_mode") or "100644"
            parts.append(f"new file mode {mode}\n")
            parts.append("--- /dev/null\n")
            parts.append(f"+++ b/{new}\n")
        elif d.get("deleted_file"):
            mode = d.get("a_mode") or "100644"
            parts.append(f"deleted file mode {mode}\n")
            parts.append(f"--- a/{old}\n")
            parts.append("+++ /dev/null\n")
        else:
            if d.get("renamed_file"):
                parts.append(f"rename from {old}\n")
                parts.append(f"rename to {new}\n")
            parts.append(f"--- a/{old}\n")
            parts.append(f"+++ b/{new}\n")
        diff = d.get("diff") or ""
        if diff and not diff.endswith("\n"):
            diff += "\n"
        parts.append(diff)
    return "".join(parts)


def _commit_and_diffs_to_patch(commit: dict, diffs: list[dict]) -> str:
    """Build a git-format-patch style email from API commit + diffs."""
    sha = commit["id"]
    author = commit.get("author_name") or "unknown"
    email = commit.get("author_email") or "unknown"
    date = _format_patch_date(
        commit.get("authored_date") or commit.get("created_at") or ""
    )
    title = (commit.get("title") or "").strip()
    message = commit.get("message") or title
    # Body under Subject: is the commit message without duplicating title
    body = message
    if title and body.startswith(title):
        body = body[len(title):].lstrip("\n")
    if body and not body.endswith("\n"):
        body += "\n"

    header = (
        f"From {sha} Mon Sep 17 00:00:00 2001\n"
        f"From: {author} <{email}>\n"
        f"Date: {date}\n"
        f"Subject: [PATCH] {title}\n"
        f"\n"
        f"{body}"
        f"---\n"
    )
    return header + _diffs_to_patch_body(diffs)


def _commit_diffs(project: str, sha: str) -> list[dict]:
    """Fetch file diffs for a commit (paginated)."""
    enc = _encode(project)
    return _paginated(f"/projects/{enc}/repository/commits/{sha}/diff")


def download_mr_patches(project: str, iid: int) -> dict[str, str]:
    """Download MR patches via the GitLab REST API (oldest-first).

    Uses /merge_requests/:iid/commits plus /repository/commits/:sha/diff
    for each commit.  Avoids the web UI ``/-/merge_requests/:iid.patch``
    URL, which Cloudflare often blocks with a 403 challenge page.
    """
    commits = get_mr_commits(project, iid)
    if not commits:
        return {}

    # API returns newest-first; review wants oldest-first numbering
    commits = list(reversed(commits))
    patches: dict[str, str] = {}

    for commit in commits:
        sha = commit["id"]
        try:
            diffs = _commit_diffs(project, sha)
        except GitLabAPIError as exc:
            raise GitLabAPIError(
                f"Failed to diff {sha[:12]} for MR !{iid}: {exc}",
                status=getattr(exc, "status", 0),
            ) from exc

        for d in diffs:
            if d.get("too_large") or d.get("collapsed"):
                raise GitLabAPIError(
                    f"Diff for {sha[:12]} in MR !{iid} is too large "
                    f"or collapsed ({d.get('new_path') or d.get('old_path')})"
                )

        patches[sha] = _commit_and_diffs_to_patch(commit, diffs)

    return patches


def get_mr_series_patch(project: str, iid: int) -> str:
    """Return MR patches concatenated as an mbox (API-based).

    Kept for callers that expect a single mbox string.
    """
    patches = download_mr_patches(project, iid)
    return "".join(patches.values())


def split_mr_series_patches(mbox_text: str) -> dict[str, str]:
    """Split an MR .patch mbox into {commit_sha: patch_text}.

    Keys are the 40-char hashes from each ``From <sha> ...`` header.
    """
    patches: dict[str, str] = {}
    parts = re.split(r"(?=^From [0-9a-f]{40} )", mbox_text, flags=re.MULTILINE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"From ([0-9a-f]{40}) ", part)
        if not m:
            continue
        if "diff --git" not in part and "Subject:" not in part:
            continue
        patches[m.group(1)] = part + "\n"
    return patches


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
