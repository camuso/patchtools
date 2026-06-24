"""Discover and cache kernel git repositories on the local filesystem."""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

CACHE_DIR = Path.home() / ".data" / "mr-review"
CACHE_FILE = CACHE_DIR / "repos.cache"

SKIP_DIRS = frozenset({
    "proc", "sys", "dev", "run", "snap", "boot", "tmp",
    "var", "lost+found", "mnt", "media", "sbin",
    "__pycache__", "node_modules", ".git",
})

console = Console()


def scan_kernel_repos() -> list[str]:
    """Walk from / and find git repos that contain a Kconfig (kernel trees).

    Skips virtual/system directories for speed.  Shows a spinner while
    scanning since this can take 10-30 seconds.
    """
    repos: list[str] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Scanning filesystem for kernel repos...[/bold cyan]"),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("", total=None)

        for dirpath, dirnames, filenames in os.walk("/", topdown=True, followlinks=False):
            # Prune dirs we never want to descend into
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS
                and not d.startswith(".")
            ]

            if ".git" in filenames or (
                os.path.isdir(os.path.join(dirpath, ".git"))
            ):
                # Found a git repo — check for Kconfig at root
                if os.path.isfile(os.path.join(dirpath, "Kconfig")):
                    repos.append(dirpath)
                    progress.update(task, description=f"Found {len(repos)}: {dirpath}")
                # Don't descend into the repo's subdirectories
                dirnames.clear()

    repos.sort()
    return repos


def load_cache() -> list[str]:
    """Read the cache file, returning only paths that still exist."""
    if not CACHE_FILE.exists():
        return []
    lines = CACHE_FILE.read_text().strip().splitlines()
    return [p for p in lines if p and os.path.isdir(p)]


def save_cache(repos: list[str]) -> None:
    """Write the repo list to the cache file (one path per line)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text("\n".join(repos) + "\n")


def get_repos(force_rescan: bool = False) -> list[str]:
    """Return cached kernel repo list, scanning if needed or forced."""
    if not force_rescan:
        cached = load_cache()
        if cached:
            return cached

    repos = scan_kernel_repos()
    if repos:
        save_cache(repos)
    return repos
