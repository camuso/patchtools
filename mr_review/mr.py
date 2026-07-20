"""GitLab Merge Request integration via the lab CLI.

Wraps 'lab mr' subcommands for listing, showing, extracting patches,
and approving/blocking merge requests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .config import Config
from .utils import run_git, git_get_current_branch

console = Console()


def _get_origin() -> str:
    """Extract the first remote name from .git/config."""
    config_path = Path(".git/config")
    if not config_path.exists():
        return "origin"
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if line.startswith("[remote"):
            # [remote "origin"]  ->  origin
            name = line.split('"')[1] if '"' in line else "origin"
            return name
    return "origin"


def _check_lab():
    """Verify lab CLI is available."""
    if not shutil.which("lab"):
        console.print(
            "[bold red]lab CLI is required but not installed.[/bold red]\n"
            "Install with: [bold]sudo dnf install lab[/bold]\n"
            "Repo: sudo dnf copr enable bmeneguele/rhkernel-devtools"
        )
        return False
    return True


def _check_lab_config():
    """Verify lab.toml config exists."""
    config_file = Path.home() / ".config" / "lab" / "lab.toml"
    if not config_file.exists():
        console.print(
            f"[bold red]lab configuration not found at {config_file}[/bold red]\n\n"
            "Create it with:\n"
            "[bold]mkdir -p ~/.config/lab[/bold]\n"
            "Then add to [bold]~/.config/lab/lab.toml[/bold]:\n\n"
            "  [core]\n"
            '    host = "https://gitlab.com"\n'
            '    token = "<your-gitlab-token>"\n'
            '    user = "<your-gitlab-username>"'
        )
        return False
    return True


def _get_lab_user() -> Optional[str]:
    """Extract username from lab.toml."""
    config_file = Path.home() / ".config" / "lab" / "lab.toml"
    if not config_file.exists():
        return None
    for line in config_file.read_text().splitlines():
        if "user" in line and "=" in line:
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return val
    return None


def _run_lab(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a lab command."""
    cmd = ["lab"] + list(args)
    return subprocess.run(
        cmd, capture_output=True, text=True, check=check,
    )


def mr_list(
    specifier: Optional[str] = None,
    origin: Optional[str] = None,
) -> list[tuple[str, str]]:
    """Get list of merge requests.

    Returns list of (mr_number, description) tuples.
    """
    if not _check_lab() or not _check_lab_config():
        return []

    if origin is None:
        origin = _get_origin()

    if specifier is None:
        specifier = "--state opened --all"

    cmd_parts = ["mr", "list", origin] + specifier.split()
    r = _run_lab(*cmd_parts, check=False)

    results = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        line = line.lstrip("!")
        parts = line.split(None, 1)
        if parts:
            mr_num = parts[0]
            desc = parts[1] if len(parts) > 1 else ""
            results.append((mr_num, desc))

    # Sort by MR number
    results.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0)
    return results


def mr_show(
    mr_number: str,
    full: bool = False,
    comments_only: bool = False,
    origin: Optional[str] = None,
) -> str:
    """Show MR details.  Returns the output text."""
    if origin is None:
        origin = _get_origin()

    args = ["mr", "show", origin, mr_number]
    if full:
        args.append("--full")
    elif comments_only:
        args.append("--comments")

    r = _run_lab(*args, check=False)
    return r.stdout


def mr_get_commits(
    mr_number: str,
    bp_commits_file: Path,
    mrcomments: Optional[str] = None,
    origin: Optional[str] = None,
) -> int:
    """Extract commit hashes from MR into bp_commits_file.

    Handles dependency-based checkout when needed.
    Returns number of commits found.
    """
    if origin is None:
        origin = _get_origin()

    # Always try lab first -- it knows exactly which commits belong
    # to the MR, regardless of dependencies or rebases.
    r = _run_lab(
        "mr", "show", origin, mr_number, "-p", "--reverse",
        check=False,
    )
    if r.returncode != 0:
        console.print(f"[bold red]lab mr show -p failed (rc={r.returncode})[/bold red]")
        if r.stderr.strip():
            console.print(f"[bold red]  {r.stderr.strip()}[/bold red]")
    commits = []
    for line in r.stdout.splitlines():
        if line.startswith("commit "):
            commits.append(line.split()[1])

    if commits:
        bp_commits_file.write_text("\n".join(commits) + "\n")
        return len(commits)

    # Fallback for dependency-based MRs where lab returns no commits:
    # check out the MR branch and use git log from the dependency base.
    import re
    base_commit = None
    if mrcomments:
        for m in re.finditer(r"Dependencies::([^,\s]*)", mrcomments):
            dep_val = m.group(1).strip()
            if dep_val.lower() not in ("ok", "none", ""):
                base_commit = dep_val
                break

    if base_commit:
        console.print(
            f"[bold cyan]lab returned no commits; "
            f"trying dependency base {base_commit}[/bold cyan]"
        )
        orig_branch = git_get_current_branch()
        _run_lab("mr", "checkout", mr_number, check=False)
        new_branch = git_get_current_branch()

        r = run_git(
            "log", "--reverse", f"{base_commit}..HEAD",
            "--format=commit %H",
            check=False,
        )
        for line in r.stdout.splitlines():
            if line.startswith("commit "):
                commits.append(line.split()[1])

        run_git("checkout", orig_branch, check=False)
        run_git("branch", "-D", new_branch, check=False)

    bp_commits_file.write_text("\n".join(commits) + "\n" if commits else "")
    return len(commits)


def mr_extract_patches(
    mr_number: str,
    cfg: Config,
) -> bool:
    """Extract patches from an MR into indir.

    Full flow: get commits, format into patch files.
    Returns True on success.
    """
    if not _check_lab() or not _check_lab_config():
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

    # Show which project we're querying
    r = run_git("remote", "get-url", origin, check=False)
    repo_url = r.stdout.strip() if r.returncode == 0 else "(unknown)"
    console.print(f"\n[bold]MR {mr_number}[/bold] from [bold]{repo_url}[/bold]")

    # Get MR comments first
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

    # Check if user has already reviewed/approved this MR
    already_reviewed = False
    lab_user = _get_lab_user()
    if lab_user and "Approved By" in mrcomments:
        for line in mrcomments.splitlines():
            if "Approved By" in line and lab_user in line:
                already_reviewed = True
                console.print(
                    f"[yellow]You have already approved MR {mr_number}.[/yellow]"
                )
                break

    # Show comments in pager (configurable)
    if cfg.show_comments:
        display_in_pager(mrcomments)

    # Ask before continuing (configurable, but always ask if already reviewed)
    if cfg.ask_continue or already_reviewed:
        if not confirm("Continue with review?"):
            return False

    # Check existing patches
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
        # Show which repo lab queried so user can spot wrong-directory errors
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

    # Format the RHEL patches from commits
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


def mr_approve(mr_number: str, with_comment: bool = False) -> bool:
    """Approve a merge request."""
    origin = _get_origin()
    args = ["mr", "approve", origin]
    if with_comment:
        args.extend(["--with-comment", "--force-linebreak"])
    args.append(mr_number)

    r = _run_lab(*args, check=False)
    return r.returncode == 0


def mr_unapprove(mr_number: str) -> bool:
    """Unapprove a merge request."""
    origin = _get_origin()
    r = _run_lab("mr", "unapprove", origin, mr_number, check=False)
    return r.returncode == 0


def mr_block(mr_number: str) -> bool:
    """Block/start discussion on a merge request."""
    origin = _get_origin()
    r = _run_lab("mr", "discussion", origin, mr_number, check=False)
    return r.returncode == 0


def mr_comment(mr_number: str) -> bool:
    """Add a comment to a merge request (interactive)."""
    origin = _get_origin()
    r = subprocess.run(
        ["lab", "mr", "note", origin, mr_number, "--force-linebreak"],
        check=False,
    )
    return r.returncode == 0


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
