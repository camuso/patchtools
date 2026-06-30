"""Rich-based terminal UI for interactive mr-review sessions.

Provides the main menu, config menu, MR ack/nack menu, and helpers
for prompts, directory selection, and editor selection.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from . import __version__
from .config import Config
from .utils import (
    git_get_current_branch,
    git_get_head_oneline,
    git_get_last_tag,
    git_is_repo,
    get_patch_files,
)

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def prompt_directory(label: str, current: Optional[Path] = None) -> Optional[Path]:
    """Prompt user for a directory path."""
    if current:
        console.print(f"  Current {label}: [bold]{current}[/bold]")
        console.print("  Press Enter to keep, or type a new path (q to cancel):")

    val = Prompt.ask(f"  {label}", default=str(current) if current else "")
    if val.lower() == "q":
        return current

    p = Path(val).expanduser().resolve()
    if not p.exists():
        from .utils import confirm
        if confirm(f"  {p} does not exist. Create it?"):
            p.mkdir(parents=True, exist_ok=True)
        else:
            return current
    return p


def prompt_editor() -> str:
    """Prompt user to select a diff editor."""
    from .utils import prompt_key
    console.print("\n  Select a diff editor:")
    console.print("  [bold]1[/bold] - vimdiff")
    console.print("  [bold]2[/bold] - meld")
    console.print("  [bold]3[/bold] - tkdiff")
    console.print("  [bold]4[/bold] - emacs")

    choice = prompt_key("  Choice", valid={"1", "2", "3", "4"})
    editors = {"1": "vimdiff", "2": "meld", "3": "tkdiff", "4": "emacs"}
    return editors[choice]


def prompt_remote_dir_and_branch(
    cfg: Config,
) -> tuple[Optional[Path], str, str]:
    """Prompt user for upstream directory, remote repo, and branch."""
    remote_dir = prompt_directory("Upstream directory", cfg.remote_dir)
    if not remote_dir or not remote_dir.is_dir():
        return None, "", ""

    # List remotes in that directory
    from .utils import run_git
    r = run_git("remote", cwd=remote_dir, check=False)
    remotes = [x.strip() for x in r.stdout.strip().splitlines() if x.strip()]

    if not remotes:
        console.print("[bold red]No remotes found in upstream directory.[/bold red]")
        return remote_dir, "", ""

    if len(remotes) == 1:
        repo = remotes[0]
    else:
        console.print("\n  Available remotes:")
        for i, rem in enumerate(remotes, 1):
            console.print(f"  [bold]{i}[/bold] - {rem}")
        idx = IntPrompt.ask(
            "  Select remote",
            choices=[str(i) for i in range(1, len(remotes) + 1)],
        )
        repo = remotes[idx - 1]

    # List branches for selected remote
    r = run_git("branch", "-r", cwd=remote_dir, check=False)
    branches = []
    for line in r.stdout.strip().splitlines():
        line = line.strip()
        if "->" in line:
            continue
        if line.startswith(f"{repo}/"):
            branches.append(line.split("/", 1)[1])

    if not branches:
        console.print(f"[bold red]No branches for remote {repo}.[/bold red]")
        return remote_dir, repo, ""

    if len(branches) == 1:
        branch = branches[0]
    else:
        console.print(f"\n  Branches in {repo}:")
        for i, br in enumerate(branches, 1):
            console.print(f"  [bold]{i}[/bold] - {br}")
        idx = IntPrompt.ask(
            "  Select branch",
            choices=[str(i) for i in range(1, len(branches) + 1)],
        )
        branch = branches[idx - 1]

    return remote_dir, repo, branch


# ---------------------------------------------------------------------------
# Repo selection
# ---------------------------------------------------------------------------

def select_repo(cfg: Config) -> bool:
    """Present discovered kernel repos and let user switch.

    Returns True if the working directory was changed, False otherwise.
    """
    from .repos import get_repos
    from .utils import prompt_key

    repos = get_repos()
    if not repos:
        console.print("[yellow]  No kernel repos found. Triggering rescan...[/yellow]")
        repos = get_repos(force_rescan=True)
        if not repos:
            console.print("[bold red]  No kernel repos discovered on this system.[/bold red]")
            return False

    cwd = os.getcwd()

    while True:
        console.print(f"\n  [bold cyan]Kernel Repositories[/bold cyan]")
        for i, repo in enumerate(repos, 1):
            marker = "  <-- current" if os.path.realpath(repo) == os.path.realpath(cwd) else ""
            console.print(f"  [bold bright_magenta]{i:3d}[/bold bright_magenta]  [bold bright_magenta]{repo}[/bold bright_magenta][bold green]{marker}[/bold green]")

        console.print(f"\n  [bold]R[/bold]  Rescan filesystem")
        console.print(f"  [bold]q[/bold]  Cancel")

        if len(repos) < 10:
            choice = prompt_key("\n  Enter number, R, or q")
        else:
            choice = Prompt.ask("\n  Enter number, R, or q").strip()

        if choice.lower() == "q":
            return False
        if choice.upper() == "R":
            from .repos import get_repos
            console.print()
            repos = get_repos(force_rescan=True)
            cwd = os.getcwd()
            if not repos:
                console.print("[bold red]  No kernel repos discovered.[/bold red]")
                return False
            continue

        if not choice.isdigit():
            continue
        idx = int(choice)
        if idx < 1 or idx > len(repos):
            console.print(f"[yellow]  Please enter 1-{len(repos)}[/yellow]")
            continue

        target = repos[idx - 1]
        if not os.path.isdir(target):
            console.print(f"[bold red]  {target} no longer exists.[/bold red]")
            continue
        if not os.path.isdir(os.path.join(target, ".git")):
            console.print(f"[bold red]  {target} is not a git repo.[/bold red]")
            continue

        os.chdir(target)
        cfg.reload(target)
        if not cfg.outdir:
            outdir = Path(target) / ".data" / "patches" / "work"
            outdir.mkdir(parents=True, exist_ok=True)
            cfg.set("outdir", outdir)
        if not cfg.indir:
            indir = Path(target) / ".patches"
            if indir.is_dir():
                cfg.set("indir", indir)
        cfg.save()
        console.print(f"[bold green]  Switched to {target}[/bold green]")
        return True


# ---------------------------------------------------------------------------
# Config menu
# ---------------------------------------------------------------------------

def config_menu(cfg: Config):
    """Interactive configuration menu."""
    while True:
        remote_str = f"{cfg.remote_dir} : {cfg.remote_repo}/{cfg.remote_branch}"

        console.print(Panel(
            "[bold]Configuration[/bold]",
            style="cyan",
        ))
        console.print(f"  [bold]d[/bold]  Patch directory      : [bold]{cfg.indir or '(not set)'}[/bold]")
        console.print(f"  [bold]w[/bold]  Work directory       : [bold]{cfg.outdir or '(not set)'}[/bold]")
        console.print(f"  [bold]u[/bold]  Upstream dir/branch  : [bold]{remote_str}[/bold]")
        console.print(f"  [bold]e[/bold]  Diff editor          : [bold]{cfg.editor}[/bold]")
        console.print(f"  [bold]f[/bold]  Patch validation fuzz: [bold]{cfg.patchvalfuzz}[/bold]")
        console.print(f"  [bold]v[/bold]  Verbose mode         : [bold]{'ON' if cfg.verbose else 'OFF'}[/bold]")
        console.print(f"  [bold]s[/bold]  Auto seek fixes      : [bold]{'ON' if cfg.seek_fixes else 'OFF'}[/bold]")
        console.print(f"  [bold]t[/bold]  Mega-merge threshold : [bold]{cfg.mega_merge_threshold}[/bold]")
        console.print(f"  [bold]m[/bold]  Mega-merge strategy  : [bold]{cfg.mega_merge_default_strategy}[/bold]")
        console.print(f"  [bold]q[/bold]  Return to main menu")

        from .utils import prompt_key
        choice = prompt_key("\n  Enter one of the above")

        if choice == "q":
            cfg.save()
            return
        elif choice == "d":
            p = prompt_directory("Patch directory", cfg.indir)
            if p:
                cfg.set("indir", p)
        elif choice == "w":
            p = prompt_directory("Work directory", cfg.outdir)
            if p:
                cfg.set("outdir", p)
        elif choice == "u":
            rd, repo, branch = prompt_remote_dir_and_branch(cfg)
            if rd:
                cfg.set("remote_dir", rd)
                cfg.set("remote_repo", repo)
                cfg.set("remote_branch", branch)
        elif choice == "e":
            cfg.set("editor", prompt_editor())
        elif choice == "f":
            fuzz = prompt_key(
                "  Fuzz level (0=exact, 1=icase, 2=no commas, 3=no punct)",
                valid={"0", "1", "2", "3"},
            )
            cfg.set("patchvalfuzz", int(fuzz))
        elif choice == "v":
            cfg.set("b_verbose", not cfg.verbose)
        elif choice == "s":
            cfg.set("b_seekfixes", not cfg.seek_fixes)
        elif choice == "t":
            val = IntPrompt.ask(
                "  Mega-merge threshold (commit count)",
                default=cfg.mega_merge_threshold,
            )
            cfg.set("mega_merge_threshold", val)
        elif choice == "m":
            strat = Prompt.ask(
                "  Strategy",
                choices=["prompt", "group", "filter", "skip"],
                default=cfg.mega_merge_default_strategy,
            )
            cfg.set("mega_merge_default_strategy", strat)

        cfg.save()


# ---------------------------------------------------------------------------
# MR ack/nack menu
# ---------------------------------------------------------------------------

def acknack_menu(cfg: Config, conflict_count: int = 0) -> Optional[str]:
    """Interactive MR approval/rejection menu.

    Returns an action string or None to quit:
      'new_mr', 'list_mr', 'review', or None
    """
    from .mr import (
        mr_approve, mr_unapprove, mr_block, mr_comment,
        mr_show, display_mr_list, mr_list, select_mr_from_list,
    )

    mr_num = cfg.current_mr
    if not mr_num:
        console.print("[yellow]No MR currently selected.[/yellow]")
        return None

    while True:
        console.print(Panel(
            f"[bold]Merge Request Review: MR {mr_num}[/bold]",
            style="cyan",
        ))

        reviewed = cfg.get_bool("b_reviewed")
        acked = cfg.get_bool("b_acked")
        nacked = cfg.get_bool("b_nacked")

        if reviewed:
            if acked:
                console.print(f"  Status: [bold green]Approved[/bold green]")
            elif nacked:
                console.print(f"  Status: [bold red]Blocked[/bold red]")

        console.print(f"  [bold]a[/bold]  Approve")
        console.print(f"  [bold]A[/bold]  Approve with comment")
        console.print(f"  [bold]b[/bold]  Block and start discussion")
        console.print(f"  [bold]u[/bold]  Unapprove")
        console.print(f"  [bold]c[/bold]  Comment only")
        console.print(f"  [bold]v[/bold]  View comments for {mr_num}")
        console.print(f"  [bold]H[/bold]  Review history")
        console.print(f"  [bold]W[/bold]  Select a working repo")
        console.print(f"  [bold]M[/bold]  Review another MR")
        console.print(f"  [bold]m[/bold]  Display list of MRs")
        console.print(f"  [bold]P[/bold]  Review diffs for {mr_num}")
        console.print(f"  [bold]q[/bold]  Return to main menu")

        from .utils import prompt_key, confirm as confirm_key
        choice = prompt_key("\n  Enter one of the above")

        from .history import update_history
        patch_count = len(get_patch_files(cfg.indir)) if cfg.indir else 0

        if choice == "q":
            return None
        elif choice in ("a", "A"):
            # Check cached MR comments for prior approval
            mrcomments_file = cfg.outdir / "mrcomments.log" if cfg.outdir else None
            if mrcomments_file and mrcomments_file.exists():
                from .mr import _get_lab_user
                lab_user = _get_lab_user()
                comments_text = mrcomments_file.read_text(errors="replace")
                if lab_user and "Approved By" in comments_text:
                    for cline in comments_text.splitlines():
                        if "Approved By" in cline and lab_user in cline:
                            console.print(
                                f"[yellow]  MR {mr_num} is already approved "
                                f"by you.[/yellow]"
                            )
                            break

            with_comment = (choice == "A")
            if confirm_key(f"  Approve MR {mr_num}?"):
                if mr_approve(mr_num, with_comment=with_comment):
                    action = "Approved with comment" if with_comment else "Approved"
                    cfg.set("b_acked", True)
                    cfg.set("b_nacked", False)
                    cfg.set("b_reviewed", True)
                    cfg.save()
                    update_history(mr_num, action, patch_count, conflict_count)
                    console.print(f"[green]MR {mr_num} approved.[/green]")
                else:
                    console.print("[bold red]Approve failed.[/bold red]")
        elif choice == "b":
            if confirm_key(f"  Block MR {mr_num}?"):
                if mr_block(mr_num):
                    cfg.set("b_nacked", True)
                    cfg.set("b_acked", False)
                    cfg.set("b_reviewed", True)
                    cfg.save()
                    update_history(mr_num, "Blocked/Discussion", patch_count, conflict_count)
                    console.print(f"[bold red]MR {mr_num} blocked.[/bold red]")
        elif choice == "u":
            if confirm_key(f"  Unapprove MR {mr_num}?"):
                if mr_unapprove(mr_num):
                    cfg.set("b_acked", False)
                    cfg.set("b_reviewed", True)
                    cfg.save()
                    update_history(mr_num, "Unapproved", patch_count, conflict_count)
                    console.print(f"[yellow]MR {mr_num} unapproved.[/yellow]")
        elif choice == "c":
            mr_comment(mr_num)
            update_history(mr_num, "Comment-only", patch_count, conflict_count)
        elif choice == "v":
            from .utils import display_in_pager
            text = mr_show(mr_num, full=True)
            display_in_pager(text)
        elif choice == "H":
            _history_menu(cfg)
        elif choice == "W":
            select_repo(cfg)
        elif choice == "M":
            return "new_mr"
        elif choice == "m":
            return "list_mr"
        elif choice == "P":
            return "review"


# ---------------------------------------------------------------------------
# History menu
# ---------------------------------------------------------------------------

def _history_menu(cfg: Config):
    """Interactive review history menu."""
    from .history import (
        view_all_history, view_history_for_mr, clear_history, HISTORY_FILE,
    )
    from .utils import prompt_key, confirm as confirm_key, display_in_pager

    while True:
        console.print(f"\n  [bold cyan]Review History[/bold cyan]")
        console.print(f"  File: [bold]{HISTORY_FILE}[/bold]")
        console.print(f"  [bold]v[/bold]  View all review history")
        console.print(f"  [bold]m[/bold]  View history for current MR: [bold]{cfg.current_mr or '(none)'}[/bold]")
        console.print(f"  [bold]s[/bold]  Specify a different MR history to view")
        console.print(f"  [bold]C[/bold]  Clear MR review history")
        console.print(f"  [bold]q[/bold]  Return")

        choice = prompt_key("\n  Enter one of the above")

        if choice == "q":
            return
        elif choice == "v":
            text = view_all_history()
            if text.strip():
                display_in_pager(text)
            else:
                console.print("[yellow]  No review history yet.[/yellow]")
        elif choice == "m":
            if cfg.current_mr:
                text = view_history_for_mr(cfg.current_mr)
                if text:
                    console.print(f"\n{text}")
                else:
                    console.print(
                        f"[yellow]  MR {cfg.current_mr} is not in your "
                        f"review history.[/yellow]"
                    )
            else:
                console.print("[yellow]  No MR currently selected.[/yellow]")
        elif choice == "s":
            mr_id = Prompt.ask("  Enter the MR number")
            if mr_id.strip():
                text = view_history_for_mr(mr_id.strip())
                if text:
                    console.print(f"\n{text}")
                else:
                    console.print(
                        f"[yellow]  MR {mr_id} is not in your "
                        f"review history.[/yellow]"
                    )
        elif choice == "C":
            if confirm_key("  Are you sure you want to clear all Review History?"):
                clear_history()
                console.print("[green]  History cleared.[/green]")


# ---------------------------------------------------------------------------
# Main interactive menu
# ---------------------------------------------------------------------------

def main_menu(cfg: Config):
    """Main interactive menu loop."""
    from .format import format_upstream_patches
    from .fixes import seek_missing_fixes
    from .compare import run_compare
    from .mr import (
        mr_extract_patches, mr_list, select_mr_from_list,
        display_mr_list,
    )

    def _run_mr_pipeline(cfg: Config, mr_num: str) -> tuple[bool, int]:
        """Run the full review pipeline for a single MR (extract, format,
        seek fixes, compare).  Returns (success, conflict_count)."""
        if not cfg.editor or cfg.editor not in ("vimdiff", "meld", "tkdiff", "emacs"):
            cfg.set("editor", prompt_editor())
            cfg.save()
        if not mr_extract_patches(mr_num, cfg):
            return False, 0
        format_upstream_patches(cfg)
        if cfg.seek_fixes:
            seek_missing_fixes(cfg)
        _ok, n_conflicts = run_compare(cfg)
        return True, n_conflicts

    if not git_is_repo():
        console.print(
            "[bold red]Not in a git repository. "
            "Please run from a kernel git tree.[/bold red]"
        )
        return

    # Ensure essential directories exist
    if not cfg.indir:
        console.print("[yellow]Patch directory not set.[/yellow]")
        p = prompt_directory("Patch directory")
        if p:
            cfg.set("indir", p)
            cfg.save()

    if not cfg.outdir:
        console.print("[yellow]Work directory not set.[/yellow]")
        p = prompt_directory("Work directory")
        if p:
            cfg.set("outdir", p)
            cfg.save()

    if not cfg.editor or cfg.editor not in ("vimdiff", "meld", "tkdiff", "emacs"):
        cfg.set("editor", prompt_editor())
        cfg.save()

    # Trampoline: acknack_menu can set next_action to feed back into
    # the main loop, just like patchreview's case_qanret / menu_parser.
    next_action = None
    last_conflict_count = 0

    while True:
        # If acknack set a follow-up action, execute it directly
        # instead of showing the main menu.
        if next_action:
            choice = next_action
            next_action = None
        else:
            last_tag = git_get_last_tag()
            head = git_get_head_oneline()
            branch = git_get_current_branch()
            patch_count = len(get_patch_files(cfg.indir)) if cfg.indir else 0
            remote_str = (
                f"{cfg.remote_dir} : {cfg.remote_repo}/{cfg.remote_branch}"
                if cfg.remote_dir else "(not set)"
            )

            mr_status = ""
            if cfg.current_mr:
                mr_status = f" MR [bold]{cfg.current_mr}[/bold]"
                if cfg.get_bool("b_acked"):
                    mr_status += " [green]Approved[/green]"
                elif cfg.get_bool("b_nacked"):
                    mr_status += " [bold red]Blocked[/bold red]"

            console.print(Panel(
                f"[bold]mr-review v{__version__}[/bold]{mr_status}",
                style="cyan",
            ))
            console.print(f"  [bold]c[/bold]  Config menu")
            console.print(f"      Most recent tag      : [bold]{last_tag}[/bold]")
            console.print(f"      Current head         : [bold]{head}[/bold]")
            console.print(f"      Branch               : [bold]{branch}[/bold]")
            console.print(f"  [bold]d[/bold]  Patch directory        : [bold]{cfg.indir}[/bold] ({patch_count} patches)")
            console.print(f"  [bold]w[/bold]  Work directory         : [bold]{cfg.outdir}[/bold]")
            console.print(f"  [bold]u[/bold]  Upstream dir/branch    : [bold]{remote_str}[/bold]")

            console.print(f"\n  [bold cyan]Main Controls[/bold cyan]")
            console.print(f"  [bold]W[/bold]  Select a working repo")
            console.print(f"  [bold]M[/bold]  Enter a specific MR for review")
            console.print(f"  [bold]m[/bold]  Show list of MRs and select one")
            console.print(f"  [bold]v[/bold]  View comments for current MR")
            console.print(f"  [bold]a[/bold]  Ack/Nack/Comment on MR")

            console.print(f"\n  [bold cyan]Operations[/bold cyan]")
            console.print(f"  [bold]F[/bold]  Format upstream patches")
            console.print(f"  [bold]S[/bold]  Seek missing fixes")
            console.print(f"  [bold]P[/bold]  Compare patches")
            console.print(f"  [bold]H[/bold]  Review history")
            console.print(f"  [bold]h[/bold]  Help")
            console.print(f"  [bold]q[/bold]  Quit")

            from .utils import prompt_key
            choice = prompt_key("\n  Enter one of the above")

        if choice == "q":
            cfg.save()
            return
        elif choice == "c":
            config_menu(cfg)
        elif choice == "d":
            p = prompt_directory("Patch directory", cfg.indir)
            if p:
                cfg.set("indir", p)
                cfg.save()
        elif choice == "w":
            p = prompt_directory("Work directory", cfg.outdir)
            if p:
                cfg.set("outdir", p)
                cfg.save()
        elif choice == "u":
            rd, repo, branch = prompt_remote_dir_and_branch(cfg)
            if rd:
                cfg.set("remote_dir", rd)
                cfg.set("remote_repo", repo)
                cfg.set("remote_branch", branch)
                cfg.save()
        elif choice == "W":
            select_repo(cfg)
        elif choice == "M":
            mr_num = Prompt.ask("  Enter MR number (q to cancel)")
            if mr_num.lower() == "q" or not mr_num.isdigit():
                continue
            ok, last_conflict_count = _run_mr_pipeline(cfg, mr_num)
            if ok:
                result = acknack_menu(cfg, last_conflict_count)
                if result in ("new_mr", "list_mr", "review"):
                    next_action = {"new_mr": "M", "list_mr": "m", "review": "P"}[result]
        elif choice == "m":
            mrs = mr_list()
            mr_num = select_mr_from_list(mrs)
            if mr_num:
                ok, last_conflict_count = _run_mr_pipeline(cfg, mr_num)
                if ok:
                    result = acknack_menu(cfg, last_conflict_count)
                    if result in ("new_mr", "list_mr", "review"):
                        next_action = {"new_mr": "M", "list_mr": "m", "review": "P"}[result]
        elif choice == "v":
            from .utils import display_in_pager
            if cfg.current_mr:
                from .mr import mr_show
                text = mr_show(cfg.current_mr, full=True)
                display_in_pager(text)
            else:
                mr_num = Prompt.ask("  Enter MR number")
                if mr_num.isdigit():
                    from .mr import mr_show
                    text = mr_show(mr_num, full=True)
                    display_in_pager(text)
        elif choice == "a":
            if cfg.current_mr:
                result = acknack_menu(cfg, last_conflict_count)
                if result in ("new_mr", "list_mr", "review"):
                    next_action = {"new_mr": "M", "list_mr": "m", "review": "P"}[result]
            else:
                console.print("[yellow]No MR selected. Use M first.[/yellow]")
        elif choice == "H":
            _history_menu(cfg)
        elif choice == "F":
            format_upstream_patches(cfg)
        elif choice == "S":
            seek_missing_fixes(cfg)
        elif choice == "P":
            _ok, last_conflict_count = run_compare(cfg)
        elif choice == "h":
            _show_help()


def _show_help():
    """Display help text in pager with colors, wait for keypress to return."""
    from io import StringIO
    from .utils import display_in_pager, readchar

    help_markup = """\
[bold cyan]mr-review - Kernel Patch Review Tool[/bold cyan]

This tool compares downstream (RHEL) patches with their upstream
counterparts, helping reviewers identify differences.

[bold]Workflow:[/bold]
  1. Enter an MR number ([bold]M[/bold]) or select from list ([bold]m[/bold])
  2. Patches are extracted from the MR
  3. Upstream commits are identified and formatted
  4. Missing fixes are sought upstream
  5. Patches are compared batch-style, conflicts highlighted
  6. Interactive diff viewer for reviewing conflicts
  7. Approve/Block the MR

[bold]Mega-merge handling:[/bold]
  When a patch contains many upstream commits (e.g. DRM merges),
  you are offered strategies:
    - Group by subsystem (see which areas are touched)
    - Filter by files (only commits touching same files)
    - Skip (mark as bulk import)
    - Manual selection (paginated, searchable list)

[bold cyan]Main menu keys:[/bold cyan]
  [bold]c[/bold]   Config menu
  [bold]d[/bold]   Set patch directory
  [bold]w[/bold]   Set work directory
  [bold]u[/bold]   Set upstream dir/branch
  [bold]W[/bold]   Select a working repo (kernel tree)
  [bold]M[/bold]   Enter a specific MR for review
  [bold]m[/bold]   Show list of MRs and select one
  [bold]v[/bold]   View comments for current MR
  [bold]a[/bold]   Ack/Nack/Comment on MR
  [bold]F[/bold]   Format upstream patches
  [bold]S[/bold]   Seek missing fixes
  [bold]P[/bold]   Compare patches
  [bold]H[/bold]   Review history
  [bold]h[/bold]   This help
  [bold]q[/bold]   Quit

[bold cyan]Review menu keys:[/bold cyan]
  [bold]a[/bold]   Approve
  [bold]A[/bold]   Approve with comment
  [bold]b[/bold]   Block and start discussion
  [bold]u[/bold]   Unapprove
  [bold]c[/bold]   Comment only
  [bold]v[/bold]   View MR comments
  [bold]W[/bold]   Select a working repo
  [bold]M[/bold]   Review another MR
  [bold]m[/bold]   Display list of MRs
  [bold]P[/bold]   Review diffs
  [bold]H[/bold]   Review history
  [bold]q[/bold]   Return to main menu

[bold cyan]Diff viewer keys:[/bold cyan]
  [bold]r[/bold]   Replay the last diff
  [bold]b[/bold]   Go back one diff
  [bold]n[/bold]   Jump to a specific patch number
  [bold]p[/bold]   Substitute a different upstream commit
  [bold]c[/bold]   Show conflicting patches
  [bold]m[/bold]   Toggle conflict-only mode
  [bold]f[/bold]   View missing fixes (if any)
  [bold]e[/bold]   Show environment info
  [bold]C[/bold]   Re-run batch comparison
  [bold]q[/bold]   Quit diff viewer
  [bold]any[/bold] Display diff for current patch

[bold cyan]Command line usage:[/bold cyan]
  [bold]mr-review[/bold]                       Interactive mode
  [bold]mr-review mr review <number>[/bold]    Review specific MR
  [bold]mr-review mr list[/bold]               List MRs
  [bold]mr-review format[/bold]                Format upstream patches
  [bold]mr-review seek[/bold]                  Seek missing fixes
  [bold]mr-review compare[/bold]               Compare patches
  [bold]mr-review status[/bold]                Show current status
"""
    buf = StringIO()
    ansi_console = Console(file=buf, force_terminal=True)
    ansi_console.print(help_markup)
    display_in_pager(buf.getvalue())
    console.print("\n  [bold cyan]Press any key to continue...[/bold cyan]", end=" ")
    readchar()
    console.print()
