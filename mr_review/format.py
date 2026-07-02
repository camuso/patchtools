"""Format upstream patches from extracted commit hashes.

Reads the commits file (us-commits.log) written by commits.py and uses
git format-patch in the upstream repo to create corresponding patch files
in the output directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from .config import Config
from .commits import extract_commits_from_patches
from .utils import git_format_patch, git_show_exists, patch_number_prefix

console = Console()

US_COMMITS_FILE = "us-commits.log"
BP_COMMITS_FILE = "bp-commits.log"


def _parse_commits_file(commits_file: Path) -> list[tuple[str, str, bool]]:
    """Parse commits file into list of (hash, index_frac, is_skipped)."""
    entries = []
    for line in commits_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue

        is_skipped = "# SKIPPED:" in line
        clean = line.split("#")[0].strip()
        parts = clean.split()
        if len(parts) < 2:
            continue
        commit_hash = parts[0]
        index_frac = parts[1]
        entries.append((commit_hash, index_frac, is_skipped))
    return entries


def format_upstream_patches(
    cfg: Config,
    force: bool = False,
) -> bool:
    """Full format pipeline: extract commits then format patches.

    Returns True on success.
    """
    indir = cfg.indir
    outdir = cfg.outdir
    remote_dir = cfg.remote_dir

    if not indir or not indir.is_dir():
        console.print("[bold red]Patch directory not set or does not exist.[/bold red]")
        return False
    if not remote_dir or not remote_dir.is_dir():
        console.print("[bold red]Upstream directory not set or does not exist.[/bold red]")
        return False
    if not outdir:
        console.print("[bold red]Work directory not set.[/bold red]")
        return False

    outdir.mkdir(parents=True, exist_ok=True)

    existing = list(outdir.glob("*.patch"))
    if existing and not force:
        console.print(
            f"\n[yellow]There are already {len(existing)} upstream patch files "
            f"in {outdir}[/yellow]"
        )
        from .utils import confirm
        if not confirm("Replace them?"):
            return False
        for f in existing:
            f.unlink()

    commits_file = outdir / US_COMMITS_FILE
    commits_file.touch()

    # Step 1: Extract commits from RHEL patches
    results = extract_commits_from_patches(
        patch_dir=indir,
        upstream_dir=remote_dir,
        commits_file=commits_file,
        fuzz=cfg.patchvalfuzz,
        mega_merge_threshold=cfg.mega_merge_threshold,
        mega_merge_strategy=cfg.mega_merge_default_strategy,
        verbose=cfg.verbose,
    )

    if not results:
        return False

    # Step 2: Format upstream patches from commits
    entries = _parse_commits_file(commits_file)
    if not entries:
        console.print("[bold red]No commits to format.[/bold red]")
        return False

    console.print(f"\n[bold]Formatting {len(entries)} upstream patches[/bold]")
    console.print(f"From: [bold]{remote_dir}[/bold]")
    console.print(f"Into: [bold]{outdir}[/bold]")
    console.rule()

    # Track which RHEL patch index we've already created a file for,
    # so mega-merge multi-commit entries share one output patch.
    seen_indices: dict[str, int] = {}
    formatted = 0
    not_found = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Formatting...", total=len(entries))

        for commit_hash, index_frac, is_skipped in entries:
            patch_num_str = index_frac.split("/")[0]
            try:
                patch_num = int(patch_num_str)
            except ValueError:
                patch_num = formatted + 1

            pfx = patch_number_prefix(patch_num)

            if is_skipped or int(commit_hash, 16) == 0:
                placeholder = outdir / f"{pfx}-nocommit.patch"
                if is_skipped:
                    placeholder.write_text(
                        f"No upstream commit detected for patch {patch_num}.\n"
                        f"Skipped: mega-merge\n"
                    )
                else:
                    placeholder.write_text(
                        f"No upstream commit detected for patch {patch_num}.\n"
                    )
                progress.update(task, advance=1)
                continue

            # For mega-merge multi-commit, skip if we already have
            # a patch for this index
            if index_frac in seen_indices:
                progress.update(task, advance=1)
                continue
            seen_indices[index_frac] = patch_num

            if not git_show_exists(commit_hash, cwd=remote_dir):
                placeholder = outdir / f"{pfx}-notfound.patch"
                placeholder.write_text(
                    f"Commit {commit_hash} was not found in any upstream repo.\n"
                )
                not_found += 1
                progress.update(task, advance=1)
                continue

            result = git_format_patch(
                commit_hash,
                destdir=outdir,
                start_number=patch_num,
                cwd=remote_dir,
            )

            if result:
                formatted += 1
                if cfg.verbose:
                    progress.console.print(f"  [bold]{result}[/bold]")
            else:
                placeholder = outdir / f"{pfx}-inv.patch"
                placeholder.write_text(f"invalid commit: {commit_hash}\n")

            progress.update(task, advance=1)

    console.print(
        f"\n[bold green]{formatted}[/bold green] patches formatted"
        + (f", [yellow]{not_found} not found[/yellow]" if not_found else "")
    )
    return True
