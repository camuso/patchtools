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
from .utils import (
    extract_commit_from_url,
    extract_repo_from_url,
    extract_subject,
    extract_upstream_status,
    fetch_commit_from_alt_repo,
    fetch_lore_patch,
    fetch_lore_series,
    get_patch_files,
    git_format_patch,
    git_show_exists,
    is_lore_url,
    match_lore_patch_by_subject,
    patch_number_prefix,
)

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

    # Build a map from 1-based patch index to RHEL patch path
    # so we can check Upstream status: when a commit is missing.
    rhel_patches = get_patch_files(indir)
    rhel_by_num: dict[int, Path] = {}
    for i, rp in enumerate(rhel_patches, 1):
        rhel_by_num[i] = rp

    console.print(f"\n[bold]Formatting {len(entries)} upstream patches[/bold]")
    console.print(f"From: [bold]{remote_dir}[/bold]")
    console.print(f"Into: [bold]{outdir}[/bold]")
    console.rule()

    # Track which RHEL patch index we've already created a file for,
    # so mega-merge multi-commit entries share one output patch.
    seen_indices: dict[str, int] = {}
    formatted = 0
    not_found = 0
    from_lore = 0
    from_alt = 0

    # Cache lore series: URL -> list of downloaded patch files
    lore_cache: dict[str, list[Path]] = {}

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
            rhel_patch = rhel_by_num.get(patch_num)

            if is_skipped:
                placeholder = outdir / f"{pfx}-nocommit.patch"
                placeholder.write_text(
                    f"No upstream commit detected for patch {patch_num}.\n"
                    f"Skipped: mega-merge\n"
                )
                progress.update(task, advance=1)
                continue

            # Null commit hash -- no upstream commit found in the patch
            if int(commit_hash, 16) == 0:
                if _try_upstream_status_fallback(
                    rhel_patch, patch_num, pfx, outdir, remote_dir,
                    progress, cfg, lore_cache=lore_cache,
                ):
                    formatted += 1
                    from_lore += 1
                else:
                    placeholder = outdir / f"{pfx}-nocommit.patch"
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
                # Commit not in configured upstream; try Upstream status: URL
                if _try_upstream_status_fallback(
                    rhel_patch, patch_num, pfx, outdir, remote_dir,
                    progress, cfg, commit_hash=commit_hash,
                    lore_cache=lore_cache,
                ):
                    formatted += 1
                    from_alt += 1
                else:
                    placeholder = outdir / f"{pfx}-notfound.patch"
                    placeholder.write_text(
                        f"Commit {commit_hash} not found in upstream repo.\n"
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

    summary = f"\n[bold green]{formatted}[/bold green] patches formatted"
    if from_lore:
        summary += f", [bold cyan]{from_lore} from lore[/bold cyan]"
    if from_alt:
        summary += f", [bold cyan]{from_alt} from alt repo[/bold cyan]"
    if not_found:
        summary += f", [bold red]{not_found} not found[/bold red]"
    console.print(summary)
    return True


def _try_upstream_status_fallback(
    rhel_patch: Optional[Path],
    patch_num: int,
    pfx: str,
    outdir: Path,
    remote_dir: Path,
    progress,
    cfg,
    commit_hash: Optional[str] = None,
    lore_cache: Optional[dict[str, list[Path]]] = None,
) -> bool:
    """Try to obtain an upstream patch via Upstream status: URL.

    Handles two cases:
      1. lore.kernel.org URL -- fetch thread, match by subject
      2. git repo URL with commit hash -- fetch from alt repo and format

    Returns True if a patch was successfully created.
    """
    if lore_cache is None:
        lore_cache = {}

    if not rhel_patch or not rhel_patch.exists():
        return False

    url = extract_upstream_status(rhel_patch)
    if not url:
        return False

    # Case 1: lore.kernel.org -- fetch series and match by subject
    if is_lore_url(url):
        # Fetch the series once, cache for subsequent patches
        if url not in lore_cache:
            progress.console.print(
                f"  [bold cyan]Fetching series from lore:[/bold cyan] {url}"
            )
            series = fetch_lore_series(url, outdir)
            if not series:
                # Fall back to single-patch download
                progress.console.print(
                    f"  [bold cyan]Series fetch failed, trying single patch[/bold cyan]"
                )
                dest = outdir / f"{pfx}-lore.patch"
                if fetch_lore_patch(url, dest):
                    lore_cache[url] = []
                    progress.console.print(
                        f"  [bold green]{dest.name}[/bold green]"
                    )
                    return True
                progress.console.print(
                    f"  [bold red]Failed to download from lore[/bold red]"
                )
                lore_cache[url] = []
                return False
            progress.console.print(
                f"  [bold green]Got {len(series)} patches from series[/bold green]"
            )
            lore_cache[url] = series

        cached = lore_cache[url]
        if not cached:
            return False

        rhel_subject = extract_subject(rhel_patch)
        matched = match_lore_patch_by_subject(rhel_subject, cached)
        if matched:
            dest = outdir / f"{pfx}-lore.patch"
            import shutil
            shutil.copy2(matched, dest)
            progress.console.print(
                f"  [bold green]{dest.name}[/bold green] (matched by subject)"
            )
            return True

        progress.console.print(
            f"  [bold red]No subject match in lore series for patch {patch_num}[/bold red]"
        )
        return False

    # Case 2: git web URL -- extract commit and repo, fetch, format
    alt_commit = commit_hash or extract_commit_from_url(url)
    alt_repo = extract_repo_from_url(url)

    if alt_commit and alt_repo:
        progress.console.print(
            f"  [bold cyan]Fetching {alt_commit[:12]} from {alt_repo}[/bold cyan]"
        )
        if fetch_commit_from_alt_repo(alt_commit, alt_repo, cwd=remote_dir):
            result = git_format_patch(
                alt_commit,
                destdir=outdir,
                start_number=patch_num,
                cwd=remote_dir,
            )
            if result:
                progress.console.print(
                    f"  [bold green]{result}[/bold green]"
                )
                return True
        progress.console.print(
            f"  [bold red]Failed to fetch from alt repo[/bold red]"
        )

    return False
