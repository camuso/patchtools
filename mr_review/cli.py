"""Click-based CLI for mr-review.

Invocation:
  mr-review              Interactive mode (no args)
  mr-review <command>    CLI subcommands
"""

from __future__ import annotations

import sys

import click
from rich.console import Console

from . import __version__
from .config import Config
from .utils import git_is_repo, git_get_current_branch, git_get_last_tag

console = Console()


def _require_repo():
    """Exit if not in a git repo."""
    if not git_is_repo():
        console.print(
            "[bold red]Not in a git repository. "
            "Please run from a kernel git tree.[/bold red]"
        )
        sys.exit(1)


def _load_config() -> Config:
    """Load config, ensuring .data directory exists."""
    return Config()


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="mr-review")
@click.pass_context
def main(ctx):
    """mr-review - Smart kernel patch review tool with mega-merge support.

    Run without arguments for interactive mode.
    """
    if ctx.invoked_subcommand is None:
        _require_repo()
        cfg = _load_config()
        from .tui import main_menu
        main_menu(cfg)


# ---------------------------------------------------------------------------
# mr — MR operations
# ---------------------------------------------------------------------------

@main.group()
def mr():
    """Merge Request operations."""
    pass


@mr.command("review")
@click.argument("mr_number")
def mr_review(mr_number):
    """Review a specific MR (extract, format, seek, compare, ack)."""
    _require_repo()
    cfg = _load_config()

    from .mr import mr_extract_patches
    from .format import format_upstream_patches
    from .fixes import seek_missing_fixes
    from .compare import run_compare
    from .tui import acknack_menu

    if mr_extract_patches(mr_number, cfg):
        format_upstream_patches(cfg)
        if cfg.seek_fixes:
            seek_missing_fixes(cfg)
        run_compare(cfg)
        acknack_menu(cfg)


@mr.command("list")
@click.option(
    "--state", default="opened",
    type=click.Choice(["opened", "merged", "closed", "all"]),
    help="MR state to filter by.",
)
@click.option("--author", default=None, help="Filter by author.")
@click.option("--target", default=None, help="Filter by target branch.")
def mr_list_cmd(state, author, target):
    """List merge requests."""
    _require_repo()

    from .mr import mr_list, display_mr_list

    spec_parts = [f"--state {state}", "--all"]
    if author:
        spec_parts.append(f"--author {author}")
    if target:
        spec_parts.append(f"-t {target}")

    specifier = " ".join(spec_parts)
    mrs = mr_list(specifier=specifier)
    display_mr_list(mrs)


@mr.command("comments")
@click.argument("mr_number")
def mr_comments_cmd(mr_number):
    """View comments for a specific MR."""
    _require_repo()

    from .mr import mr_show
    from .utils import display_in_pager
    text = mr_show(mr_number, full=True)
    display_in_pager(text)


@mr.command("approve")
@click.argument("mr_number")
@click.option("--comment", is_flag=True, help="Approve with comment.")
def mr_approve_cmd(mr_number, comment):
    """Approve a merge request."""
    _require_repo()

    from .utils import confirm
    from .mr import mr_approve

    if confirm(f"Approve MR {mr_number}?"):
        if mr_approve(mr_number, with_comment=comment):
            cfg = _load_config()
            cfg.set("b_acked", True)
            cfg.set("b_nacked", False)
            cfg.set("b_reviewed", True)
            cfg.save()
            console.print(f"[green]MR {mr_number} approved.[/green]")
        else:
            console.print("[bold red]Approve failed.[/bold red]")


@mr.command("block")
@click.argument("mr_number")
def mr_block_cmd(mr_number):
    """Block a merge request and start discussion."""
    _require_repo()

    from .utils import confirm
    from .mr import mr_block

    if confirm(f"Block MR {mr_number}?"):
        if mr_block(mr_number):
            cfg = _load_config()
            cfg.set("b_nacked", True)
            cfg.set("b_acked", False)
            cfg.set("b_reviewed", True)
            cfg.save()
            console.print(f"[bold red]MR {mr_number} blocked.[/bold red]")


# ---------------------------------------------------------------------------
# Standalone operation commands
# ---------------------------------------------------------------------------

@main.command()
def format():
    """Format upstream patches from commit hashes in RHEL patches."""
    _require_repo()
    cfg = _load_config()

    from .format import format_upstream_patches
    format_upstream_patches(cfg)


@main.command()
def seek():
    """Seek missing fixes in the upstream remote branch."""
    _require_repo()
    cfg = _load_config()

    from .fixes import seek_missing_fixes
    seek_missing_fixes(cfg)


@main.command()
def compare():
    """Compare RHEL patches with upstream and present diffs."""
    _require_repo()
    cfg = _load_config()

    from .compare import run_compare
    run_compare(cfg)


@main.command()
def status():
    """Show current configuration and environment status."""
    _require_repo()
    cfg = _load_config()

    from .utils import get_patch_files

    console.print(f"\n[bold cyan]mr-review v{__version__} status[/bold cyan]\n")
    console.print(f"  Editor        : [bold]{cfg.editor}[/bold]")
    console.print(f"  Branch        : [bold]{git_get_current_branch()}[/bold]")
    console.print(f"  Last tag      : [bold]{git_get_last_tag()}[/bold]")
    console.print(f"  Patch dir     : [bold]{cfg.indir or '(not set)'}[/bold]")

    if cfg.indir:
        pc = len(get_patch_files(cfg.indir))
        console.print(f"                  ({pc} patches)")

    console.print(f"  Work dir      : [bold]{cfg.outdir or '(not set)'}[/bold]")
    console.print(f"  Upstream dir  : [bold]{cfg.remote_dir or '(not set)'}[/bold]")
    console.print(f"  Remote        : [bold]{cfg.remote_repo}/{cfg.remote_branch}[/bold]")
    console.print(f"  Verbose       : [bold]{'ON' if cfg.verbose else 'OFF'}[/bold]")
    console.print(f"  Seek fixes    : [bold]{'ON' if cfg.seek_fixes else 'OFF'}[/bold]")
    console.print(f"  Fuzz level    : [bold]{cfg.patchvalfuzz}[/bold]")
    console.print(f"  Mega-merge th : [bold]{cfg.mega_merge_threshold}[/bold]")
    console.print(f"  Mega strategy : [bold]{cfg.mega_merge_default_strategy}[/bold]")

    if cfg.current_mr:
        console.print(f"  Current MR    : [bold]{cfg.current_mr}[/bold]")
        if cfg.get_bool("b_acked"):
            console.print(f"                  [green]Approved[/green]")
        elif cfg.get_bool("b_nacked"):
            console.print(f"                  [bold red]Blocked[/bold red]")

    console.print()


@main.command("set-config")
@click.argument("key")
@click.argument("value")
def set_config(key, value):
    """Set a configuration value (key value)."""
    cfg = _load_config()
    cfg.set(key, value)
    cfg.save()
    console.print(f"[green]Set {key} = {value}[/green]")


if __name__ == "__main__":
    main()
