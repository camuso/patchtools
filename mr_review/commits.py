"""Smart commit extraction from RHEL patches with mega-merge detection.

This is the core improvement over the original patchreview.  When a patch
contains more than `mega_merge_threshold` upstream commit hashes (e.g. a
DRM bulk merge), the user is offered multiple strategies instead of being
shown an unusable list of hundreds of commits.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn
from rich.table import Table
from rich.prompt import Prompt, IntPrompt

from .utils import (
    HASH_RE,
    extract_commit_log,
    extract_diff_files,
    extract_subject,
    extract_subject_bare,
    git_commit_files,
    git_log_summary,
    git_show_exists,
    subjects_match,
)

console = Console()

MEGA_MERGE_THRESHOLD_DEFAULT = 10


@dataclass
class CommitResult:
    """Result of commit extraction for a single patch file."""
    patch_index: int
    patch_path: Path
    commit: Optional[str] = None
    skipped: bool = False
    skip_reason: str = ""
    selected_commits: list[str] = field(default_factory=list)


@dataclass
class MegaMergeGroup:
    """A group of commits touching the same subsystem directory."""
    subsystem: str
    commits: list[str] = field(default_factory=list)


def _extract_raw_hashes(commit_log: str) -> list[str]:
    """Extract unique 40-char hex hashes from commit log text.

    Skips hashes that appear on lines mentioning 'revert' (case insensitive).
    Preserves order of first appearance.
    """
    seen = set()
    result = []
    for line in commit_log.splitlines():
        if re.search(r"\brevert\b", line, re.IGNORECASE):
            continue
        for m in HASH_RE.finditer(line):
            h = m.group()
            # Filter out all-zero hashes
            if int(h, 16) == 0:
                continue
            if h not in seen:
                seen.add(h)
                result.append(h)
    return result


def _validate_and_select_single(
    hashes: list[str],
    subject: str,
    upstream_dir: Path,
    fuzz: int,
) -> Optional[str]:
    """For a small set of hashes, try subject matching then fall back to prompt."""
    bare_subject = extract_subject_bare(subject)
    valid_commits: list[str] = []

    if len(hashes) == 1:
        h = hashes[0]
        if git_show_exists(h, cwd=upstream_dir):
            return h
        return None

    # Try subject-line matching first
    for h in hashes:
        if not git_show_exists(h, cwd=upstream_dir):
            continue
        summary = git_log_summary(h, cwd=upstream_dir)
        if summary is None:
            continue
        if subjects_match(bare_subject, summary, fuzz=fuzz):
            return h
        valid_commits.append(h)

    if not valid_commits:
        return None
    if len(valid_commits) == 1:
        return valid_commits[0]

    # Multiple valid commits but no subject match: prompt user
    console.print(
        f"\n[bold]Multiple upstream commits found, "
        f"none matching subject line.[/bold]"
    )
    console.print(f"  Subject: [white]{bare_subject}[/white]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="bold", width=4)
    table.add_column("Commit", width=14)
    table.add_column("Summary")

    for i, h in enumerate(valid_commits, 1):
        summary = git_log_summary(h, cwd=upstream_dir) or "(unknown)"
        table.add_row(str(i), h[:12], summary)

    console.print(table)
    choice = IntPrompt.ask(
        "Select commit number",
        choices=[str(i) for i in range(1, len(valid_commits) + 1)],
    )
    return valid_commits[choice - 1]


# ---------------------------------------------------------------------------
# Mega-merge strategies
# ---------------------------------------------------------------------------

def _group_by_subsystem(
    hashes: list[str],
    upstream_dir: Path,
    depth: int = 3,
) -> list[MegaMergeGroup]:
    """Group commits by the top-level directory they touch."""
    groups: dict[str, list[str]] = defaultdict(list)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Grouping by subsystem...", total=len(hashes),
        )
        for h in hashes:
            if not git_show_exists(h, cwd=upstream_dir):
                progress.update(task, advance=1)
                continue
            files = git_commit_files(h, cwd=upstream_dir)
            subsystems = set()
            for f in files:
                parts = f.split("/")
                sub = "/".join(parts[:min(depth, len(parts))])
                subsystems.add(sub)
            if not subsystems:
                subsystems = {"(unknown)"}
            for sub in subsystems:
                groups[sub].append(h)
            progress.update(task, advance=1)

    result = []
    for sub in sorted(groups, key=lambda s: -len(groups[s])):
        result.append(MegaMergeGroup(subsystem=sub, commits=groups[sub]))
    return result


def _strategy_group(
    hashes: list[str],
    upstream_dir: Path,
) -> list[str]:
    """Mega-merge strategy: group by subsystem, let user select groups."""
    console.print("\n[bold cyan]Grouping commits by subsystem...[/bold cyan]")

    groups = _group_by_subsystem(hashes, upstream_dir)
    if not groups:
        console.print("[bold red]No valid upstream commits found.[/bold red]")
        return []

    table = Table(
        title=f"Mega-merge: {len(hashes)} upstream commits",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Subsystem")
    table.add_column("Commits", justify="right")

    for i, g in enumerate(groups, 1):
        table.add_row(str(i), g.subsystem, str(len(g.commits)))

    console.print(table)
    console.print(
        "\nEnter subsystem numbers (comma-separated), "
        "'a' for all, or 's' to skip:"
    )
    choice = Prompt.ask("Selection")

    if choice.strip().lower() == "s":
        return []
    if choice.strip().lower() == "a":
        selected = []
        for g in groups:
            selected.extend(g.commits)
        return list(dict.fromkeys(selected))

    selected = []
    try:
        indices = [int(x.strip()) for x in choice.split(",")]
        for idx in indices:
            if 1 <= idx <= len(groups):
                selected.extend(groups[idx - 1].commits)
    except ValueError:
        console.print("[bold red]Invalid selection, skipping.[/bold red]")
        return []

    return list(dict.fromkeys(selected))


def _strategy_filter_files(
    hashes: list[str],
    rhel_patch_path: Path,
    upstream_dir: Path,
) -> list[str]:
    """Mega-merge strategy: filter to commits touching same files as RHEL patch."""
    rhel_files = set(extract_diff_files(rhel_patch_path))
    if not rhel_files:
        console.print("[yellow]Could not determine files from RHEL patch.[/yellow]")
        return []

    console.print(
        f"\n[bold cyan]Filtering {len(hashes)} commits to those "
        f"touching {len(rhel_files)} files from the RHEL patch...[/bold cyan]"
    )

    matching = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Filtering...", total=len(hashes))
        for h in hashes:
            if not git_show_exists(h, cwd=upstream_dir):
                progress.update(task, advance=1)
                continue
            commit_files = set(git_commit_files(h, cwd=upstream_dir))
            if commit_files & rhel_files:
                matching.append(h)
            progress.update(task, advance=1)

    console.print(
        f"  Found [bold]{len(matching)}[/bold] commits touching the same files."
    )
    return matching


def _strategy_manual(
    hashes: list[str],
    upstream_dir: Path,
) -> list[str]:
    """Mega-merge strategy: paginated searchable list."""
    valid: list[tuple[str, str]] = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Validating commits...", total=len(hashes))
        for h in hashes:
            if not git_show_exists(h, cwd=upstream_dir):
                progress.update(task, advance=1)
                continue
            summary = git_log_summary(h, cwd=upstream_dir) or "(unknown)"
            valid.append((h, summary))
            progress.update(task, advance=1)

    if not valid:
        console.print("[bold red]No valid upstream commits found.[/bold red]")
        return []

    page_size = 20
    total_pages = (len(valid) + page_size - 1) // page_size

    console.print(f"\n[bold]{len(valid)} valid upstream commits[/bold]")
    console.print(
        "Navigate: [bold]n[/bold]ext page, [bold]p[/bold]rev page, "
        "[bold]/<pattern>[/bold] to search, "
        "[bold]<numbers>[/bold] comma-separated to select, "
        "[bold]a[/bold]ll, [bold]s[/bold]kip"
    )

    page = 0
    while True:
        start = page * page_size
        end = min(start + page_size, len(valid))

        table = Table(
            title=f"Page {page + 1}/{total_pages}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", style="bold", width=6)
        table.add_column("Commit", width=14)
        table.add_column("Summary")

        for i in range(start, end):
            h, summary = valid[i]
            table.add_row(str(i + 1), h[:12], summary)

        console.print(table)

        from .utils import readchar
        console.print("Choice", end="  ")
        ch = readchar()

        if ch.lower() == "n":
            console.print(ch)
            page = min(page + 1, total_pages - 1)
        elif ch.lower() == "p":
            console.print(ch)
            page = max(page - 1, 0)
        elif ch.lower() == "s":
            console.print(ch)
            return []
        elif ch.lower() == "a":
            console.print(ch)
            return [h for h, _ in valid]
        elif ch == "/":
            # Switch to line input for search pattern
            pattern = Prompt.ask("/").lower()
            matches = [
                (i, h, s) for i, (h, s) in enumerate(valid)
                if pattern in s.lower() or pattern in h
            ]
            if matches:
                for i, h, s in matches:
                    console.print(f"  [bold]{i + 1}[/bold]. {h[:12]} {s}")
            else:
                console.print("[yellow]No matches.[/yellow]")
        elif ch.isdigit():
            # Switch to line input for comma-separated numbers
            rest = Prompt.ask(ch, default="")
            choice = ch + rest
            try:
                indices = [int(x.strip()) for x in choice.split(",")]
                selected = []
                for idx in indices:
                    if 1 <= idx <= len(valid):
                        selected.append(valid[idx - 1][0])
                if selected:
                    return selected
                console.print("[bold red]No valid indices in selection.[/bold red]")
            except ValueError:
                console.print("[bold red]Invalid input.[/bold red]")
        else:
            console.print(ch)


def _handle_mega_merge(
    hashes: list[str],
    patch_path: Path,
    upstream_dir: Path,
    default_strategy: str,
) -> tuple[list[str], bool]:
    """Handle a patch with many upstream commits.

    Returns (selected_commits, was_skipped).
    """
    console.print(
        f"\n[bold yellow]Mega-merge detected:[/bold yellow] "
        f"[bold]{len(hashes)}[/bold] upstream commits in patch"
    )
    console.print(f"  [white]{patch_path.name}[/white]")

    if default_strategy == "skip":
        return [], True
    if default_strategy == "group":
        selected = _strategy_group(hashes, upstream_dir)
        return selected, not bool(selected)
    if default_strategy == "filter":
        selected = _strategy_filter_files(hashes, patch_path, upstream_dir)
        return selected, not bool(selected)

    # default_strategy == "prompt" or anything else
    console.print("\nChoose a strategy:")
    console.print("  [bold]1[/bold] - Group by subsystem (see which areas are touched)")
    console.print("  [bold]2[/bold] - Filter by files (only commits touching same files)")
    console.print("  [bold]3[/bold] - Skip (mark as bulk import)")
    console.print("  [bold]4[/bold] - Manual selection (paginated list)")

    from .utils import prompt_key
    choice = prompt_key("Strategy", valid={"1", "2", "3", "4"})

    if choice == "1":
        selected = _strategy_group(hashes, upstream_dir)
    elif choice == "2":
        selected = _strategy_filter_files(hashes, patch_path, upstream_dir)
    elif choice == "3":
        return [], True
    else:
        selected = _strategy_manual(hashes, upstream_dir)

    return selected, not bool(selected)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_commits_from_patches(
    patch_dir: Path,
    upstream_dir: Path,
    commits_file: Path,
    fuzz: int = 1,
    mega_merge_threshold: int = MEGA_MERGE_THRESHOLD_DEFAULT,
    mega_merge_strategy: str = "prompt",
    verbose: bool = True,
) -> list[CommitResult]:
    """Extract upstream commit hashes from all patches in patch_dir.

    Writes results to commits_file in the format expected by the rest of
    the toolchain: '<hash> <index>/<total>' per line.

    Returns a list of CommitResult for each patch processed.
    """
    from .utils import get_patch_files

    patches = get_patch_files(patch_dir)
    if not patches:
        console.print(f"[bold red]No patch files in {patch_dir}[/bold red]")
        return []

    total = len(patches)
    results: list[CommitResult] = []

    console.print(f"\n[bold]{total} patches[/bold] in {patch_dir}")
    console.print(f"Upstream repo: [bold]{upstream_dir}[/bold]")
    console.rule()

    with commits_file.open("w") as cf:
        for idx, patch_path in enumerate(patches, 1):
            result = CommitResult(patch_index=idx, patch_path=patch_path)

            if verbose:
                console.print(f"[white]{patch_path.name}[/white]")

            commit_log = extract_commit_log(patch_path)
            subject = extract_subject(patch_path)
            hashes = _extract_raw_hashes(commit_log)

            if not hashes:
                cf.write(f"{'0' * 40} {idx}/{total}\n")
                result.commit = None
                results.append(result)
                continue

            if len(hashes) > mega_merge_threshold:
                selected, skipped = _handle_mega_merge(
                    hashes, patch_path, upstream_dir, mega_merge_strategy,
                )
                if skipped:
                    cf.write(
                        f"{'0' * 40} {idx}/{total}"
                        f" # SKIPPED: mega-merge ({len(hashes)} commits)\n"
                    )
                    result.skipped = True
                    result.skip_reason = (
                        f"mega-merge with {len(hashes)} commits"
                    )
                    results.append(result)
                    continue

                # For mega-merges with selected commits, write each one.
                # The format phase will combine them for comparison.
                result.selected_commits = selected
                for sh in selected:
                    cf.write(f"{sh} {idx}/{total}\n")
                result.commit = selected[0] if selected else None
                results.append(result)
                continue

            # Normal case: small number of hashes
            commit = _validate_and_select_single(
                hashes, subject, upstream_dir, fuzz,
            )

            if commit:
                cf.write(f"{commit} {idx}/{total}\n")
                result.commit = commit
            else:
                cf.write(f"{'0' * 40} {idx}/{total}\n")

            results.append(result)

    console.print(f"\n[bold]Commits written to[/bold] {commits_file}")
    skipped_count = sum(1 for r in results if r.skipped)
    if skipped_count:
        console.print(
            f"[yellow]{skipped_count} patch(es) skipped as mega-merges[/yellow]"
        )

    return results
