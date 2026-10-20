"""GitLab Merge Request integration via direct REST API.

Uses the gitlab_api module for all GitLab communication.
No dependency on the lab CLI.  Credentials are read from
~/.config/lab/lab.toml for backward compatibility.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import gitlab_api
from .gitlab_api import GitLabAPIError
from .config import Config
from .utils import run_git, git_get_current_branch

console = Console()


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _get_origin() -> str:
    """Extract the first remote name from .git/config."""
    config_path = Path(".git/config")
    if not config_path.exists():
        return "origin"
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("[remote"):
            name = line.split('"')[1] if '"' in line else "origin"
            return name
    return "origin"


def _get_project_path(origin: Optional[str] = None) -> Optional[str]:
    """Derive the GitLab project path from the git remote URL."""
    if origin is None:
        origin = _get_origin()
    r = run_git("remote", "get-url", origin, check=False)
    if r.returncode != 0:
        return None
    return gitlab_api.project_path_from_remote(r.stdout.strip())


def _check_api() -> bool:
    """Verify we have a GitLab token configured."""
    if not gitlab_api.get_token():
        console.print(
            "[bold red]No GitLab token found.[/bold red]\n"
            "Add one to [bold]~/.config/lab/lab.toml[/bold] under [core]:\n\n"
            "  [core]\n"
            '    host = "https://gitlab.com"\n'
            '    token = "<your-gitlab-token>"\n'
            '    user = "<your-gitlab-username>"'
        )
        return False
    return True


def _edit_text(prompt_header: str = "") -> Optional[str]:
    """Open $EDITOR for the user to compose text; return the result.

    Returns the text entered, or None if the user left it empty / aborted.
    Works the same way as ``git commit`` — writes a temp file with an
    optional header comment, opens the editor, reads the result.
    """
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    header = ""
    if prompt_header:
        header = "\n".join(f"# {line}" for line in prompt_header.splitlines())
        header += "\n# Lines starting with '#' will be stripped.\n\n"

    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, prefix="mr-review-",
        ) as tmp:
            tmp.write(header)
            tmp_path = tmp.name

        subprocess.run([editor, tmp_path], check=True)

        text = Path(tmp_path).read_text()
        lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
        result = "\n".join(lines).strip()
        return result if result else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _fetch_mr_ref(mr_iid: int, origin: str) -> bool:
    """Fetch the MR head ref so its commits are available locally.

    Uses GitLab's refs/merge-requests/<iid>/head convention.
    """
    r = run_git(
        "fetch", origin,
        f"refs/merge-requests/{mr_iid}/head",
        check=False,
    )
    return r.returncode == 0


def _parse_dependency(mrcomments: Optional[str]) -> Optional[str]:
    """Extract the dependency base commit from MR comments text.

    Looks for ``Dependencies::<sha>`` where sha is NOT 'OK' or 'none'.
    Returns the base commit SHA, or None if there is no dependency.
    """
    if not mrcomments:
        return None
    for m in re.finditer(r"Dependencies::([^,\s]*)", mrcomments):
        val = m.group(1).strip()
        if val.lower() not in ("ok", "none", ""):
            return val
    return None


# -------------------------------------------------------------------
# MR listing
# -------------------------------------------------------------------

def mr_list(
    specifier: Optional[str] = None,
    origin: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Get list of merge requests.

    Returns list of (mr_number, description) tuples.
    """
    if not _check_api():
        return []

    if origin is None:
        origin = _get_origin()

    project = _get_project_path(origin)
    if not project:
        console.print("[bold red]Could not determine GitLab project path.[/bold red]")
        return []

    # Parse specifier into API parameters
    state = "opened"
    author = None
    target = None
    if specifier:
        parts = specifier.split()
        for i, p in enumerate(parts):
            if p == "--state" and i + 1 < len(parts):
                state = parts[i + 1]
            elif p == "--author" and i + 1 < len(parts):
                author = parts[i + 1]
            elif p in ("-t", "--target") and i + 1 < len(parts):
                target = parts[i + 1]

    try:
        mrs_data = gitlab_api.list_mrs(
            project, state=state, author=author, target_branch=target,
        )
    except GitLabAPIError as exc:
        console.print(f"[bold red]GitLab API error: {exc}[/bold red]")
        return []

    results = []
    for mr in mrs_data:
        mr_num = str(mr["iid"])
        desc = mr.get("title", "")
        results.append((mr_num, desc))

    results.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
    return results


# -------------------------------------------------------------------
# MR show (comments / details)
# -------------------------------------------------------------------

def mr_show(
    mr_number: str,
    full: bool = False,
    comments_only: bool = False,
    origin: Optional[str] = None,
) -> str:
    """Show MR details.  Returns the output text."""
    if origin is None:
        origin = _get_origin()

    project = _get_project_path(origin)
    if not project:
        return ""

    iid = int(mr_number)
    try:
        mr_data = gitlab_api.get_mr(project, iid)
        notes = gitlab_api.get_mr_notes(project, iid)
        try:
            approvals = gitlab_api.get_mr_approvals(project, iid)
        except GitLabAPIError:
            approvals = None
        return gitlab_api.format_mr_text(
            mr_data, notes,
            approvals=approvals,
            full=full,
            comments_only=comments_only,
        )
    except GitLabAPIError as exc:
        console.print(f"[bold red]API error fetching MR {mr_number}: {exc}[/bold red]")
        return ""


# -------------------------------------------------------------------
# MR commit extraction (the critical patch-retrieval path)
# -------------------------------------------------------------------

def mr_get_commits(
    mr_number: str,
    bp_commits_file: Path,
    mrcomments: Optional[str] = None,
    origin: Optional[str] = None,
) -> int:
    """Extract commit hashes from MR into bp_commits_file.

    Strategy:
      1. Check for Dependencies:: in mrcomments.
      2. Normal MR  → API /commits gives us the exact set.
      3. Dependency MR → fetch the MR ref, then
         ``git log <dep_base>..FETCH_HEAD`` to isolate new commits.

    In both cases we ``git fetch`` the MR ref so that the commits
    are available locally for ``git format-patch`` later.

    Returns the number of commits found.
    """
    if origin is None:
        origin = _get_origin()

    project = _get_project_path(origin)
    iid = int(mr_number)

    dep_base = _parse_dependency(mrcomments)

    # ------------------------------------------------------------------
    # Dependency MR: we must filter out the dependency's commits
    # ------------------------------------------------------------------
    if dep_base:
        console.print(
            f"[bold cyan]Dependency MR — base {dep_base}; "
            f"fetching MR ref to isolate new commits.[/bold cyan]"
        )
        if not _fetch_mr_ref(iid, origin):
            console.print(
                "[bold red]git fetch of MR ref failed.[/bold red]"
            )
            bp_commits_file.write_text("")
            return 0

        r = run_git(
            "log", "--reverse", f"{dep_base}..FETCH_HEAD",
            "--format=%H", check=False,
        )
        commits = [h.strip() for h in r.stdout.splitlines() if h.strip()]

        if not commits:
            console.print(
                f"[yellow]No commits found between {dep_base[:12]} "
                f"and FETCH_HEAD.[/yellow]"
            )

        bp_commits_file.write_text(
            "\n".join(commits) + "\n" if commits else ""
        )
        return len(commits)

    # ------------------------------------------------------------------
    # Normal MR: get commit list from the API
    # ------------------------------------------------------------------
    commits: list[str] = []

    if project:
        try:
            api_commits = gitlab_api.get_mr_commits(project, iid)
            commits = [c["id"] for c in reversed(api_commits)]
        except GitLabAPIError as exc:
            console.print(
                f"[bold red]API error fetching commits: {exc}[/bold red]"
            )

    if not commits:
        bp_commits_file.write_text("")
        return 0

    # Make sure the commits exist locally for git format-patch
    from .utils import git_show_exists
    if not git_show_exists(commits[0]):
        if not _fetch_mr_ref(iid, origin):
            console.print(
                "[bold red]git fetch of MR ref failed — "
                "commits not available locally.[/bold red]"
            )
            bp_commits_file.write_text("")
            return 0

    bp_commits_file.write_text("\n".join(commits) + "\n")
    return len(commits)


# -------------------------------------------------------------------
# Full patch extraction pipeline
# -------------------------------------------------------------------

def mr_extract_patches(
    mr_number: str,
    cfg: Config,
) -> bool:
    """Extract patches from an MR into indir.

    Full flow: get commits, format into patch files.
    Returns True on success.
    """
    if not _check_api():
        return False

    indir = cfg.indir
    outdir = cfg.outdir
    if not indir or not outdir:
        console.print("[bold red]Patch or Work directory not configured.[/bold red]")
        return False

    indir.mkdir(parents=True, exist_ok=True)
    outdir.mkdir(parents=True, exist_ok=True)

    origin = _get_origin()
    bp_commits_file = outdir / "bp-commits.log"

    r = run_git("remote", "get-url", origin, check=False)
    repo_url = r.stdout.strip() if r.returncode == 0 else "(unknown)"
    console.print(f"\n[bold]MR {mr_number}[/bold] from [bold]{repo_url}[/bold]")

    # Get MR comments via API
    from rich.progress import Progress, SpinnerColumn, TextColumn
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Getting comments for MR {task.description}...[/bold cyan]"),
        console=console, transient=True,
    ) as progress:
        progress.add_task(mr_number, total=None)
        mrcomments = mr_show(mr_number, comments_only=True, origin=origin)

    if not mrcomments or not mrcomments.strip():
        console.print(
            f"[bold red]MR {mr_number} not found or returned no data.[/bold red]"
        )
        console.print(
            f"[yellow]Repo: {repo_url}[/yellow]\n"
            "[yellow]Make sure this MR belongs to the current repo.[/yellow]"
        )
        return False

    mrcomments_file = outdir / "mrcomments.log"
    mrcomments_file.write_text(mrcomments)

    from .utils import confirm, display_in_pager

    already_reviewed = False
    lab_user = gitlab_api.get_user()
    if lab_user and "Approved By" in mrcomments:
        for line in mrcomments.splitlines():
            if "Approved By" in line and lab_user in line:
                already_reviewed = True
                console.print(
                    f"[yellow]You have already approved MR {mr_number}.[/yellow]"
                )
                break

    if cfg.show_comments:
        display_in_pager(mrcomments)

    if cfg.ask_continue or already_reviewed:
        if not confirm("Continue with review?"):
            return False

    existing = list(indir.glob("*.patch"))
    if existing:
        console.print(
            f"[yellow]There are already {len(existing)} patch files "
            f"in {indir}[/yellow]"
        )
        if cfg.ask_replace:
            if not confirm("Replace them?"):
                return False
        for f in indir.iterdir():
            if f.is_file():
                f.unlink()
        for f in outdir.glob("*.patch"):
            f.unlink()

    # Extract commits
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Fetching patches from MR {task.description}...[/bold cyan]"),
        console=console, transient=True,
    ) as progress:
        progress.add_task(mr_number, total=None)
        patch_count = mr_get_commits(
            mr_number, bp_commits_file,
            mrcomments=mrcomments, origin=origin,
        )

    if patch_count == 0:
        r = run_git("remote", "get-url", origin, check=False)
        repo_url = r.stdout.strip() if r.returncode == 0 else "(unknown)"
        console.print(f"[bold red]No patches found for MR {mr_number}[/bold red]")
        console.print(f"[bold red]Repo: {repo_url}[/bold red]")
        console.print(
            "[yellow]Make sure you are running from the correct "
            "git repo for this MR.[/yellow]"
        )
        return False

    console.print(f"Found [bold]{patch_count}[/bold] commits")

    from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn
    from .utils import run_git as _run_git
    commits = [
        line.strip() for line in bp_commits_file.read_text().splitlines()
        if line.strip()
    ]
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Extracting patches...", total=len(commits))
        for i, commit in enumerate(commits, 1):
            result = _run_git(
                "format-patch", "-1", "-k", "--no-renames",
                "--start-number", str(i),
                commit, "-o", str(indir),
                check=False,
            )
            if result.returncode != 0:
                pfx = f"{i:04d}"
                (indir / f"{pfx}-extract-failed.patch").write_text(
                    f"Failed to format commit: {commit}\n"
                )
            progress.update(task, advance=1)

    cfg.set("current_mr", mr_number)
    cfg.set("b_reviewed", False)
    cfg.set("b_acked", False)
    cfg.set("b_nacked", False)
    cfg.save()

    return True


# -------------------------------------------------------------------
# Approve / unapprove (API-based)
# -------------------------------------------------------------------

def mr_approve(mr_number: str, with_comment: bool = False) -> tuple[bool, str]:
    """Approve a merge request.

    Returns (success, error_message).
    """
    origin = _get_origin()
    project = _get_project_path(origin)
    if not project:
        return False, "Cannot determine GitLab project path"

    iid = int(mr_number)

    try:
        gitlab_api.approve_mr(project, iid)
    except GitLabAPIError as exc:
        if exc.status in (401, 409):
            # Distinguish "already approved" from a real auth problem
            try:
                approvals = gitlab_api.get_mr_approvals(project, iid)
                me = gitlab_api.get_user()
                approved_by = [
                    u.get("user", {}).get("username", "")
                    for u in approvals.get("approved_by", [])
                ]
                if me and me in approved_by:
                    return False, (
                        f"MR !{mr_number} is already approved by you ({me})."
                    )
                return False, (
                    f"Permission denied: your token may lack approval rights "
                    f"for MR !{mr_number}."
                )
            except GitLabAPIError:
                pass
        return False, str(exc)

    if with_comment:
        comment = _edit_text(f"Approval comment for MR !{mr_number}")
        if comment:
            try:
                gitlab_api.add_note(project, iid, comment)
            except GitLabAPIError as exc:
                return True, f"Approved, but comment failed: {exc}"

    return True, ""


def mr_unapprove(mr_number: str) -> bool:
    """Unapprove a merge request."""
    origin = _get_origin()
    project = _get_project_path(origin)
    if not project:
        return False
    try:
        gitlab_api.unapprove_mr(project, int(mr_number))
        return True
    except GitLabAPIError:
        return False


def mr_block(mr_number: str) -> bool:
    """Block a merge request by starting a discussion thread."""
    origin = _get_origin()
    project = _get_project_path(origin)
    if not project:
        console.print("[bold red]Cannot determine GitLab project path.[/bold red]")
        return False

    body = _edit_text(f"Discussion / block comment for MR !{mr_number}")
    if not body:
        console.print("[yellow]Empty comment — block cancelled.[/yellow]")
        return False

    try:
        gitlab_api.create_discussion(project, int(mr_number), body)
        return True
    except GitLabAPIError as exc:
        console.print(f"[bold red]Failed to create discussion: {exc}[/bold red]")
        return False


def mr_comment(mr_number: str) -> bool:
    """Add a comment to a merge request (opens editor)."""
    origin = _get_origin()
    project = _get_project_path(origin)
    if not project:
        console.print("[bold red]Cannot determine GitLab project path.[/bold red]")
        return False

    body = _edit_text(f"Comment on MR !{mr_number}")
    if not body:
        console.print("[yellow]Empty comment — cancelled.[/yellow]")
        return False

    try:
        gitlab_api.add_note(project, int(mr_number), body)
        return True
    except GitLabAPIError as exc:
        console.print(f"[bold red]Failed to post comment: {exc}[/bold red]")
        return False


# -------------------------------------------------------------------
# Display helpers
# -------------------------------------------------------------------

def display_mr_list(mrs: list[tuple[str, str]]):
    """Display MR list in a Rich table."""
    if not mrs:
        console.print("[yellow]No merge requests found.[/yellow]")
        return

    table = Table(
        title="Merge Requests",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("MR#", style="bold", width=8)
    table.add_column("Description")

    for mr_num, desc in mrs:
        table.add_row(mr_num, desc)

    console.print(table)


def select_mr_from_list(mrs: list[tuple[str, str]]) -> Optional[str]:
    """Display MR list and let user select one."""
    display_mr_list(mrs)
    if not mrs:
        return None

    mr_nums = {m[0] for m in mrs}
    while True:
        choice = Prompt.ask(
            "\nEnter MR number (or 'q' to quit)"
        )
        if choice.lower() == "q":
            return None
        if choice in mr_nums:
            return choice
        console.print(f"[bold red]{choice} is not in the list.[/bold red]")
