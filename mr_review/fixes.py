"""Seek missing fixes in upstream remote branches.

For each upstream commit in the series, search for 'Fixes: <short-hash>'
commits in the remote branch and determine whether each fix is:
  - Already in the current MR series
  - Already merged into the downstream branch
  - Intentionally omitted (marked in commit log or MR comments)
  - Truly missing (WARNING)

Mirrors the bash check_fixes/find_fixes/parse_missingfix logic.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn

from .config import Config
from .utils import (
    extract_commit_log,
    run_git,
)

console = Console()

SHORT_HASH_RE = re.compile(r"\b[0-9a-f]{7,12}\b")


def _is_valid_hash(h: str) -> bool:
    """Check if a string looks like a valid commit hash."""
    if not h or len(h) != 40:
        return False
    try:
        return int(h, 16) != 0
    except ValueError:
        return False


def _find_patch_by_number(patch_dir: Path, num: int) -> Optional[Path]:
    """Find a patch file by its leading number."""
    prefix = f"{num:04d}"
    for f in sorted(patch_dir.glob("*.patch")):
        if f.name.startswith(prefix):
            return f
    return None


def _check_omitted(
    fix_hash: str,
    mr_commitlog: str,
    mrcomments: str,
) -> bool:
    """Check if a fix was intentionally omitted."""
    pattern = re.compile(r"omitted.fix", re.IGNORECASE)
    for text in (mr_commitlog, mrcomments):
        if pattern.search(text) and fix_hash in text:
            return True
    return False


def _find_fixes(
    commit_hash: str,
    remote_dir: Path,
    remote_branch: str,
) -> tuple[str, list[str]]:
    """Find commits on remote_branch that fix the given commit.

    Mirrors bash find_fixes(): gets short hash and date with one git
    call, then searches for Fixes: tags since that date.

    Returns (commit_date, list_of_fix_lines).
    """
    r = run_git(
        "log", "--pretty=%h|%ad", "-1", commit_hash,
        cwd=remote_dir, check=False,
    )
    line = r.stdout.strip()
    if not line or "|" not in line:
        return "", []

    short_hash, commit_date = line.split("|", 1)

    r = run_git(
        "--no-pager", "log", "--oneline",
        "--pretty=%h (\"%s\")",
        f"--since={commit_date}",
        f"--grep=Fixes: {short_hash}",
        remote_branch,
        cwd=remote_dir, check=False,
    )
    fix_lines = [ln for ln in r.stdout.strip().splitlines() if ln]
    return commit_date, fix_lines


def _parse_missingfix(
    commit_date: str,
    fix_line: str,
    index_frac: str,
    commits_file_text: str,
    mr_commitlog: str,
    mrcomments: str,
    missing_file: Path,
) -> int:
    """Determine if a fix is truly missing or accounted for.

    Mirrors bash parse_missingfix().

    Returns:
        0 - fix is accounted for
        1 - intentionally omitted or in series/downstream
        2 - truly missing
    """
    fix_hash_match = SHORT_HASH_RE.search(fix_line)
    if not fix_hash_match:
        return 0
    fix_id = fix_hash_match.group()

    # 1. Intentionally omitted?
    if _check_omitted(fix_id, mr_commitlog, mrcomments):
        with missing_file.open("a") as f:
            f.write(
                f"Intentionally Omitted Fix: "
                f"{fix_line} for {index_frac}\n"
            )
        return 1

    # 2. Fix is in the upstream commits list for this MR series?
    #    (grep fix_id against the commits file, same as old code)
    for cline in commits_file_text.splitlines():
        if fix_id in cline:
            found_frac = cline.split()[1] if len(cline.split()) > 1 else ""
            with missing_file.open("a") as f:
                f.write(
                    f"{found_frac} contains Fix: "
                    f"{fix_line} for {index_frac}\n"
                )
            return 1

    # 3. Already merged downstream? Search the current (RHEL) branch
    #    for "commit <fix_id>" since the commit date.
    #    Runs in cwd (the RHEL repo), NOT the upstream repo.
    r = run_git(
        "log", f"--since={commit_date}",
        f"--grep=commit {fix_id}",
        "--format=%h", "-1",
        cwd=None, check=False,
    )
    if r.stdout.strip():
        with missing_file.open("a") as f:
            f.write(
                f"Downstream has Fix: "
                f"{fix_line} for {index_frac}\n"
            )
        return 1

    # 4. Truly missing
    with missing_file.open("a") as f:
        f.write(
            f"WARNING: found Missing Fix: "
            f"{fix_line} for {index_frac}\n"
        )
    console.print(
        f"  [bold red]MISSING:[/bold red] "
        f"{fix_line} for {index_frac}"
    )
    return 2


def seek_missing_fixes(cfg: Config) -> Path:
    """Search upstream for missing fixes.

    Returns the path to the missing_fixes output file.
    """
    outdir = cfg.outdir
    indir = cfg.indir
    remote_dir = cfg.remote_dir

    if not outdir or not indir or not remote_dir:
        console.print("[bold red]Directories not fully configured.[/bold red]")
        return Path("/dev/null")

    remote_branch = f"{cfg.remote_repo}/{cfg.remote_branch}"
    commits_file = outdir / "us-commits.log"
    missing_file = outdir / "missing_fixes"
    mrcomments_file = outdir / "mrcomments.log"

    if not commits_file.exists():
        console.print(
            "[bold red]Upstream commits file not found. Run 'format' first.[/bold red]"
        )
        return missing_file

    mrcomments = ""
    if mrcomments_file.exists():
        mrcomments = mrcomments_file.read_text(errors="replace")

    commits_file_text = commits_file.read_text()

    # Read the commits file: each line is "<hash> <index>/<total>"
    commit_entries: list[tuple[str, str]] = []
    for line in commits_file_text.splitlines():
        clean = line.split("#")[0].strip()
        if not clean:
            continue
        parts = clean.split()
        if len(parts) >= 2:
            commit_entries.append((parts[0], parts[1]))

    valid_entries = [
        (h, frac) for h, frac in commit_entries if _is_valid_hash(h)
    ]

    if not valid_entries:
        console.print("[yellow]No valid commits to check.[/yellow]")
        missing_file.write_text("")
        return missing_file

    console.print(
        f"\n[bold]Looking for missing fixes in "
        f"{remote_dir} : {remote_branch}[/bold]\n"
    )

    missing_file.write_text("")
    warning_count = 0

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Checking fixes...", total=len(valid_entries))

        for commit_hash, index_frac in valid_entries:
            patch_num_str = index_frac.split("/")[0]
            try:
                patch_num = int(patch_num_str)
            except ValueError:
                progress.update(task, advance=1)
                continue

            # find_fixes: two git calls (get date, then grep), same as bash
            commit_date, fix_lines = _find_fixes(
                commit_hash, remote_dir, remote_branch,
            )

            if not fix_lines:
                progress.update(task, advance=1)
                continue

            # Get the commit log for omitted-fix checking
            patch_file = _find_patch_by_number(indir, patch_num)
            mr_commitlog = ""
            if patch_file:
                mr_commitlog = extract_commit_log(patch_file)

            # parse_missingfix for each fix found
            for fix_line in fix_lines:
                result = _parse_missingfix(
                    commit_date,
                    fix_line,
                    index_frac,
                    commits_file_text,
                    mr_commitlog,
                    mrcomments,
                    missing_file,
                )
                if result == 2:
                    warning_count += 1

            progress.update(task, advance=1)

    if warning_count:
        console.print(
            f"\n[bold red]WARNING: {warning_count} missing fix(es) "
            f"found![/bold red]"
        )
        console.print(f"Details in: {missing_file}")
    else:
        console.print("\n[bold green]No missing fixes found.[/bold green]")

    return missing_file
