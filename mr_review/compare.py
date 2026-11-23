"""Batch patch comparison and interactive diff viewer.

Replaces patbatcmp (batch line-by-line comparison) and patcmp
(interactive diff navigation).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich.table import Table

from .config import Config
from .utils import (
    extract_change_lines,
    extract_diff_files,
    extract_hunk_lines,
    get_patch_files,
    is_placeholder_patch,
    is_real_patch,
)

console = Console()


@dataclass
class ConflictInfo:
    """Information about a single patch conflict."""
    patch_index: int          # 1-based index
    rhel_path: Path
    upstream_path: Path
    possible_fp: bool = False  # possible false positive


def _compare_patch_pair(
    rhel_path: Path,
    upstream_path: Path,
    strict: bool = False,
) -> bool:
    """Compare two patch files.

    Returns True if they match (no conflict), False if they differ.

    Default includes hunk context as well as +/- lines, while still
    ignoring commit logs, ---/+++ paths, index, and @@ markers.
    Context differences matter for review (tree divergence around an
    otherwise identical change).

    When strict=True, only +/- lines are compared (patbatcmp -s).

    If either side lacks 'diff --git' (nocommit/notfound placeholder),
    that is a conflict.
    """
    if not is_real_patch(rhel_path) or not is_real_patch(upstream_path):
        return False

    if strict:
        return extract_change_lines(rhel_path) == extract_change_lines(upstream_path)

    return extract_hunk_lines(rhel_path) == extract_hunk_lines(upstream_path)


def _check_possible_fp(rhel_path: Path, upstream_path: Path) -> bool:
    """Check if a conflict might be a false positive.

    A conflict is possibly false if the downstream patch has no
    Conflicts: stanza, both patches modify the same files, and the
    actual +/- change lines (sorted) are identical — i.e. only hunk
    context differs due to tree divergence.
    """
    # If submitter documented conflicts, trust it as real
    rhel_text = rhel_path.read_text(errors="replace")
    if "Conflicts:" in rhel_text.split("diff --git")[0]:
        return False

    rhel_files = extract_diff_files(rhel_path)
    us_files = extract_diff_files(upstream_path)
    if rhel_files != us_files:
        return False

    rhel_changes = sorted(extract_change_lines(rhel_path))
    us_changes = sorted(extract_change_lines(upstream_path))
    return rhel_changes == us_changes


def batch_compare(
    rhel_dir: Path,
    upstream_dir: Path,
    output_file: Optional[Path] = None,
    strict: bool = False,
) -> list[ConflictInfo]:
    """Batch compare all patch pairs between two directories.

    Returns list of ConflictInfo for patches that differ.
    Default compares hunk context and +/- lines (commit logs,
    ---/+++, index, @@ ignored). Missing upstream or a Conflicts:
    stanza also forces a conflict for interactive review.
    """
    rhel_patches = get_patch_files(rhel_dir)
    us_patches = get_patch_files(upstream_dir)

    if not rhel_patches:
        console.print(f"[bold red]No patch files in {rhel_dir}[/bold red]")
        return []
    if not us_patches:
        console.print(f"[bold red]No patch files in {upstream_dir}[/bold red]")
        return []

    if len(rhel_patches) != len(us_patches):
        console.print(
            f"[yellow]Warning: RHEL has {len(rhel_patches)} patches, "
            f"upstream has {len(us_patches)}.[/yellow]"
        )

    pair_count = min(len(rhel_patches), len(us_patches))
    conflicts: list[ConflictInfo] = []

    console.print(f"\n[bold]Comparing {pair_count} patch pairs...[/bold]")

    for i in range(pair_count):
        rp = rhel_patches[i]
        up = us_patches[i]

        code_match = _compare_patch_pair(rp, up, strict=strict)
        rhel_header = rp.read_text(errors="replace").split("diff --git")[0]
        has_conflicts_stanza = "Conflicts:" in rhel_header

        # Conflict if hunk/context differs, upstream missing, or Conflicts:
        if not code_match or has_conflicts_stanza:
            if is_placeholder_patch(up) or not is_real_patch(up):
                fp = False
            else:
                fp = _check_possible_fp(rp, up)
            conflicts.append(ConflictInfo(
                patch_index=i + 1,
                rhel_path=rp,
                upstream_path=up,
                possible_fp=fp,
            ))

    # Write output file if requested
    if output_file:
        with output_file.open("w") as f:
            f.write(f"verbosity:1\n")
            for c in conflicts:
                f.write(
                    f"PATCH:{c.patch_index}:"
                    f"{c.rhel_path.name} != {c.upstream_path.name}\n"
                )

    return conflicts


def display_conflicts(conflicts: list[ConflictInfo], total_patches: int):
    """Display conflict summary using Rich table."""
    if not conflicts:
        console.print(
            "\n[bold green] ********************************************* [/bold green]"
        )
        console.print(
            "[bold green] *                                           * [/bold green]"
        )
        console.print(
            "[bold green] *    There are no conflicting patches       * [/bold green]"
        )
        console.print(
            "[bold green] *                                           * [/bold green]"
        )
        console.print(
            "[bold green] ********************************************* [/bold green]"
        )
        return

    fp_count = sum(1 for c in conflicts if c.possible_fp)

    table = Table(
        title="Patches conflicting with upstream commits",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="bold", width=4)
    table.add_column("Patch", width=6, justify="right")
    table.add_column("RHEL file")
    table.add_column("Upstream")
    table.add_column("FP?", width=4)

    missing_us = 0
    for i, c in enumerate(conflicts, 1):
        fp_mark = "[bold cyan]?[/bold cyan]" if c.possible_fp else ""
        if is_placeholder_patch(c.upstream_path) or not is_real_patch(c.upstream_path):
            us_label = f"[bold red]{c.upstream_path.name}[/bold red]"
            missing_us += 1
        else:
            us_label = c.upstream_path.name
        table.add_row(
            str(i),
            str(c.patch_index),
            c.rhel_path.name,
            us_label,
            fp_mark,
        )

    console.print(table)
    console.print(
        f"\nTotal conflicts with upstream: [bold]{len(conflicts)}[/bold]"
    )
    if missing_us:
        console.print(
            f"[bold red]Missing upstream patches: {missing_us}[/bold red] "
            f"(no commit / commit not in your upstream tree)"
        )
    if fp_count:
        console.print(
            f"Possible false positives [?]: [bold cyan]{fp_count}[/bold cyan] "
            f"(verify manually)"
        )


def _launch_diff(editor: str, file_a: Path, file_b: Path):
    """Launch a diff editor on two files."""
    if not editor:
        console.print("[bold red]No diff editor configured. Use config menu (c) to set one.[/bold red]")
        return
    if editor == "vimdiff":
        subprocess.run(["vimdiff", "-c", "redraw!", str(file_a), str(file_b)])
    elif editor == "emacs":
        subprocess.run([
            "emacs", "--eval",
            f'(ediff-files "{file_a}" "{file_b}")',
            "-geometry", "160x40",
        ])
    elif editor in ("tkdiff", "meld"):
        subprocess.run([editor, str(file_a), str(file_b)])
    else:
        subprocess.run([editor, str(file_a), str(file_b)])


def _substitute_upstream(cfg: Config, patch_idx: int, us_patches: list[Path]):
    """Replace the upstream patch for patch_idx with a different commit.

    Prompts for a new commit hash, formats it from the upstream repo,
    and overwrites the existing upstream patch file.
    """
    from .utils import (
        git_show_exists, git_format_patch, git_log_oneline,
        patch_number_prefix,
    )

    outdir = cfg.outdir
    remote_dir = cfg.remote_dir

    if not remote_dir or not remote_dir.is_dir():
        console.print("[bold red]Upstream directory not configured.[/bold red]")
        return

    current_file = us_patches[patch_idx] if patch_idx < len(us_patches) else None
    if current_file:
        console.print(f"  Current upstream: [bold]{current_file.name}[/bold]")

    commit = Prompt.ask("  Enter upstream commit hash (q to cancel)")
    if not commit or commit.lower() == "q":
        return

    if not git_show_exists(commit, cwd=remote_dir):
        console.print(f"[bold red]Commit {commit} not found in {remote_dir}[/bold red]")
        return

    summary = git_log_oneline(commit, cwd=remote_dir)
    console.print(f"  [bold]{summary}[/bold]")

    from .utils import confirm
    if not confirm("  Replace upstream patch with this commit?"):
        return

    # Remove the old upstream patch file
    if current_file and current_file.exists():
        current_file.unlink()

    patch_num = patch_idx + 1
    result = git_format_patch(
        commit,
        destdir=outdir,
        start_number=patch_num,
        cwd=remote_dir,
    )

    if result:
        new_path = Path(result)
        us_patches[patch_idx] = new_path
        console.print(
            f"[bold green]  Replaced with: {new_path.name}[/bold green]"
        )
    else:
        console.print("[bold red]  Failed to format patch.[/bold red]")


def interactive_compare(
    cfg: Config,
    conflicts: Optional[list[ConflictInfo]] = None,
) -> bool:
    """Interactive comparison session.

    If conflicts list is provided, navigate through conflicts.
    Otherwise, navigate through all patches.

    Returns True if user completed review.
    """
    indir = cfg.indir
    outdir = cfg.outdir
    editor = cfg.editor

    if not indir or not outdir:
        console.print("[bold red]Directories not configured.[/bold red]")
        return False

    rhel_patches = get_patch_files(indir)
    us_patches = get_patch_files(outdir)

    if not rhel_patches or not us_patches:
        console.print("[bold red]No patches to compare.[/bold red]")
        return False

    total = min(len(rhel_patches), len(us_patches))
    missing_file = outdir / "missing_fixes"
    has_missing_fixes = (
        missing_file.exists()
        and missing_file.stat().st_size > 0
        and "WARNING" in missing_file.read_text(errors="replace")
    )

    # If we have conflicts, start in conflict-only mode
    conflict_mode = bool(conflicts)
    conflict_indices = [c.patch_index - 1 for c in conflicts] if conflicts else []

    if conflict_mode:
        nav_list = conflict_indices
    else:
        nav_list = list(range(total))

    if not nav_list:
        console.print("[green]Nothing to review.[/green]")
        return True

    pos = 0  # position in nav_list
    last_rhel = None  # last pair shown in diff editor
    last_us = None
    last_idx = None   # patch index of last viewed diff
    # When reviewing all patches (D / no conflict list), open the
    # first pair immediately — waiting for an extra key is confusing.
    auto_launch = conflicts is None

    while True:
        idx = nav_list[pos]
        if idx >= len(rhel_patches) or idx >= len(us_patches):
            console.print(f"[bold red]Patch index {idx + 1} out of range.[/bold red]")
            break

        rhel_file = rhel_patches[idx]
        us_file = us_patches[idx]

        # Find conflict info if available
        conflict_info = None
        if conflicts:
            for c in conflicts:
                if c.patch_index - 1 == idx:
                    conflict_info = c
                    break

        ctx = f"cwd: {os.getcwd()}"
        if cfg.current_mr:
            ctx += f"  MR: {cfg.current_mr}"
        from rich.panel import Panel
        console.print(Panel(
            f"[bold]{editor}[/bold] will diff local patches with upstream commits",
            subtitle=ctx,
            style="cyan",
        ))
        console.print(
            f"[bold]Patch {idx + 1}[/bold] of {total}"
        )
        console.print(f"[bold]RHEL    : {rhel_file}[/bold]")
        console.print(f"[bold]Upstream: {us_file}[/bold]")

        if is_placeholder_patch(us_file) or not is_real_patch(us_file):
            console.print(
                "[bold red]Missing upstream patch — open the pair to "
                "review the RHEL patch.[/bold red]"
            )
            for line in us_file.read_text(errors="replace").strip().splitlines():
                console.print(f"  [bold yellow]{line}[/bold yellow]")

        if conflict_info:
            ci = conflict_indices.index(idx) if idx in conflict_indices else 0
            console.print(
                f"[bold red]Conflict {ci + 1}[/bold red] of "
                f"[bold red]{len(conflict_indices)}[/bold red]"
            )
            rhel_header = rhel_file.read_text(errors="replace").split("diff --git")[0]
            if "Conflicts:" in rhel_header:
                console.print(
                    "[bold yellow]  RHEL commit log contains Conflicts: "
                    "stanza[/bold yellow]"
                )
            if conflict_info.possible_fp:
                console.print("[bold cyan]  [?] Possible false positive[/bold cyan]")

        console.print("[bold]" + "-" * 68 + "[/bold]")

        # Menu
        console.print("  [bold]r[/bold] - replay the last diff")
        console.print("  [bold]b[/bold] - go back one diff")
        console.print("  [bold]n[/bold] - go to specific patch number")
        console.print("  [bold]p[/bold] - substitute a different upstream commit")
        console.print(
            f"  [bold]c[/bold] - show conflicting patches"
        )
        console.print(
            f"  [bold]m[/bold] - toggle conflict-only mode: "
            f"[bold]{'ON' if conflict_mode else 'OFF'}[/bold]"
        )
        if has_missing_fixes:
            console.print("  [bold]f[/bold] - view missing fixes")
        console.print("  [bold]e[/bold] - show environment")
        console.print(
            "  [bold]C[/bold] - run batch comparison to find conflicts"
        )
        console.print("  [bold]q[/bold] - quit")
        console.print(
            f"  [bold]Any other key[/bold] displays diff for "
            f"patch {idx + 1} of {total}"
        )

        from .utils import prompt_key
        if auto_launch:
            auto_launch = False
            choice = ""  # fall through to launch diff
            console.print()
        else:
            choice = prompt_key("\n  Your choice")

        if choice == "q":
            break
        elif choice == "r":
            if last_rhel and last_us:
                _launch_diff(editor, last_rhel, last_us)
            else:
                console.print("[yellow]No diff has been viewed yet.[/yellow]")
            continue
        elif choice == "b":
            # pos was already advanced after the last diff, so we need
            # to go back 2: one to undo the advance, one to truly back up.
            pos = max(pos - 2, 0)
            back_idx = nav_list[pos]
            bf_rhel = rhel_patches[back_idx]
            bf_us = us_patches[back_idx]
            _launch_diff(editor, bf_rhel, bf_us)
            last_rhel = bf_rhel
            last_us = bf_us
            last_idx = back_idx
            # Advance so the next default action shows the patch after this one
            if pos < len(nav_list) - 1:
                pos += 1
            continue
        elif choice == "p":
            sub_idx = last_idx if last_idx is not None else idx
            _substitute_upstream(cfg, sub_idx, us_patches)
            # Immediately show the diff with the new upstream patch
            pf_rhel = rhel_patches[sub_idx]
            pf_us = us_patches[sub_idx]
            _launch_diff(editor, pf_rhel, pf_us)
            last_rhel = pf_rhel
            last_us = pf_us
            last_idx = sub_idx
            continue
        elif choice == "n":
            try:
                pnum = IntPrompt.ask(
                    "Patch number",
                    default=idx + 1,
                )
                target = pnum - 1
                if 0 <= target < total:
                    if conflict_mode and target in conflict_indices:
                        pos = conflict_indices.index(target)
                    elif not conflict_mode:
                        pos = target
                    else:
                        console.print(
                            "[yellow]Not a conflict. "
                            "Toggle 'm' to see all.[/yellow]"
                        )
                else:
                    console.print("[bold red]Out of range.[/bold red]")
            except (ValueError, KeyboardInterrupt):
                pass
            continue
        elif choice == "c":
            if conflicts:
                display_conflicts(conflicts, total)
            else:
                console.print("[green]No conflicts detected.[/green]")
            continue
        elif choice == "m":
            conflict_mode = not conflict_mode
            if conflict_mode and conflict_indices:
                nav_list = conflict_indices
                pos = 0
            else:
                nav_list = list(range(total))
                pos = idx
                conflict_mode = False
            continue
        elif choice == "f" and has_missing_fixes:
            from .utils import display_in_pager
            display_in_pager(missing_file.read_text(errors="replace"))
            continue
        elif choice == "e":
            from .utils import git_get_last_tag, git_get_current_branch
            console.print(f"  Last Tag    : [bold]{git_get_last_tag()}[/bold]")
            console.print(f"  Branch      : [bold]{git_get_current_branch()}[/bold]")
            console.print(f"  RHEL dir    : [bold]{indir}[/bold]")
            console.print(f"  Upstream dir: [bold]{outdir}[/bold]")
            if has_missing_fixes:
                console.print("  [bold red]There are missing fixes.[/bold red]")
            continue
        elif choice == "C":
            conflicts = batch_compare(
                indir, outdir,
                output_file=outdir / "mm.log",
            )
            conflict_indices = [
                c.patch_index - 1 for c in conflicts
            ]
            display_conflicts(conflicts, total)
            if conflict_indices:
                conflict_mode = True
                nav_list = conflict_indices
                pos = 0
            continue
        else:
            # Launch diff editor and remember what was shown
            _launch_diff(editor, rhel_file, us_file)
            last_rhel = rhel_file
            last_us = us_file
            last_idx = idx

            # Advance to next or signal completion
            if pos < len(nav_list) - 1:
                pos += 1
            else:
                label = "conflicts" if conflict_mode else "patches"
                msg = f"All {label} have been reviewed."
                pad = len(msg) + 6
                console.print()
                console.print(f"[bold green] {'*' * pad} [/bold green]")
                console.print(f"[bold green] *  {msg}  * [/bold green]")
                console.print(f"[bold green] {'*' * pad} [/bold green]")

    return True


def run_compare(cfg: Config) -> tuple[bool, int]:
    """Full comparison pipeline: batch compare then interactive review.

    Returns (success, conflict_count).
    """
    indir = cfg.indir
    outdir = cfg.outdir

    if not indir or not outdir:
        console.print("[bold red]Directories not configured.[/bold red]")
        return False, 0

    # Run batch comparison
    mm_file = outdir / "mm.log"
    conflicts = batch_compare(indir, outdir, output_file=mm_file)
    display_conflicts(conflicts, len(get_patch_files(indir)))

    if not conflicts:
        return True, 0

    # Enter interactive mode only when there are conflicts to review
    # (includes missing-upstream placeholders, matching bash patbatcmp).
    ok = interactive_compare(cfg, conflicts=conflicts)
    return ok, len(conflicts)
