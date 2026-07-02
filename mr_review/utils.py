"""Git helpers, file operations, and patch parsing utilities."""

from __future__ import annotations

import atexit
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import termios
import tty
from pathlib import Path
from typing import Optional


HASH_RE = re.compile(r"\b[0-9a-f]{40}\b")
SHORT_HASH_RE = re.compile(r"\b[0-9a-f]{7,12}\b")

# Save the terminal state at import time so we can always restore it.
_saved_term_attrs = None
try:
    if sys.stdin.isatty():
        _saved_term_attrs = termios.tcgetattr(sys.stdin.fileno())
except Exception:
    pass


def _restore_terminal():
    """Restore terminal to the state captured at startup."""
    if _saved_term_attrs is not None:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _saved_term_attrs)
        except Exception:
            pass
    # Re-show cursor in case Rich or something hid it
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _signal_handler(signum, frame):
    """Handle termination signals by restoring the terminal first."""
    _restore_terminal()
    sys.exit(128 + signum)


atexit.register(_restore_terminal)
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def run_git(
    *args: str,
    cwd: Optional[str | Path] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run a git command and return the CompletedProcess."""
    cmd = ["git"] + list(args)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=check,
    )


def git_log_oneline(commit: str, cwd: Optional[str | Path] = None) -> Optional[str]:
    """Return the one-line log for a commit, or None if invalid."""
    try:
        r = run_git("log", "--oneline", "-n1", commit, cwd=cwd)
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def git_log_summary(commit: str, cwd: Optional[str | Path] = None) -> Optional[str]:
    """Return just the summary (no hash prefix) from git log --oneline."""
    line = git_log_oneline(commit, cwd=cwd)
    if line is None:
        return None
    parts = line.split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def git_show_exists(commit: str, cwd: Optional[str | Path] = None) -> bool:
    """Check whether a commit exists in the repo."""
    try:
        run_git("cat-file", "-t", commit, cwd=cwd)
        return True
    except subprocess.CalledProcessError:
        return False


def git_format_patch(
    commit: str,
    destdir: str | Path,
    start_number: int = 1,
    cwd: Optional[str | Path] = None,
) -> Optional[str]:
    """Format a single commit as a patch file, return the output path."""
    try:
        r = run_git(
            "format-patch", "-1", "-k", "--no-renames",
            "--start-number", str(start_number),
            commit, "-o", str(destdir),
            cwd=cwd,
        )
        return r.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def git_get_current_branch(cwd: Optional[str | Path] = None) -> str:
    r = run_git("branch", "--show-current", cwd=cwd, check=False)
    return r.stdout.strip()


def git_get_last_tag(cwd: Optional[str | Path] = None) -> str:
    r = run_git("describe", "--tags", "--abbrev=0", cwd=cwd, check=False)
    return r.stdout.strip()


def git_get_head_oneline(cwd: Optional[str | Path] = None) -> str:
    r = run_git("log", "--oneline", "-n1", cwd=cwd, check=False)
    return r.stdout.strip()


def git_is_repo(path: Optional[str | Path] = None) -> bool:
    """Check if path is inside a git repository."""
    if path is None:
        path = os.getcwd()
    return (Path(path) / ".git").is_dir()


def git_commit_files(commit: str, cwd: Optional[str | Path] = None) -> list[str]:
    """Return list of files touched by a commit."""
    try:
        r = run_git(
            "diff-tree", "--no-commit-id", "-r", "--name-only", commit,
            cwd=cwd,
        )
        return [f for f in r.stdout.strip().splitlines() if f]
    except subprocess.CalledProcessError:
        return []


def git_find_fixes(
    commit: str,
    remote_branch: str,
    cwd: Optional[str | Path] = None,
) -> list[str]:
    """Find commits on remote_branch that fix the given commit."""
    try:
        info = run_git(
            "log", "--pretty=%h|%ad", "-1", commit, cwd=cwd,
        )
        parts = info.stdout.strip().split("|", 1)
        if len(parts) < 2:
            return []
        short_hash, commit_date = parts

        r = run_git(
            "--no-pager", "log", "--oneline",
            "--pretty=%h (\"%s\")",
            f"--since={commit_date}",
            f"--grep=Fixes: {short_hash}",
            remote_branch,
            cwd=cwd,
            check=False,
        )
        return [line for line in r.stdout.strip().splitlines() if line]
    except subprocess.CalledProcessError:
        return []


def git_commit_in_branch(
    commit: str,
    since_date: str,
    cwd: Optional[str | Path] = None,
) -> bool:
    """Check if a commit exists in the current branch (searching since date)."""
    try:
        r = run_git(
            "log", f"--since={since_date}",
            "--format=%H", "--grep", f"commit {commit}",
            cwd=cwd, check=False,
        )
        return bool(r.stdout.strip())
    except subprocess.CalledProcessError:
        return False


def git_rev_list_contains(
    commit: str,
    ref: str,
    cwd: Optional[str | Path] = None,
) -> bool:
    """Check if commit is an ancestor of ref."""
    r = run_git("merge-base", "--is-ancestor", commit, ref, cwd=cwd, check=False)
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Patch file parsing
# ---------------------------------------------------------------------------

def extract_subject(patch_path: str | Path) -> str:
    """Extract Subject line from a patch file, including continuation lines."""
    patch_path = Path(patch_path)
    subject_parts: list[str] = []
    in_subject = False

    for line in patch_path.read_text(errors="replace").splitlines():
        if not in_subject:
            if line.startswith("Subject: "):
                subject_parts.append(line[len("Subject: "):])
                in_subject = True
        else:
            if line and line[0] in (" ", "\t"):
                subject_parts.append(line.strip())
            else:
                break

    return " ".join(subject_parts)


def extract_subject_bare(subject: str) -> str:
    """Strip [PATCH ...] prefix and return the bare subject."""
    m = re.match(r"\[.*?\]\s*(.*)", subject)
    return m.group(1) if m else subject


def extract_commit_log(patch_path: str | Path) -> str:
    """Extract the commit log portion (before first 'diff --git' or '---')."""
    lines: list[str] = []
    for line in Path(patch_path).read_text(errors="replace").splitlines():
        if line.startswith("diff --git ") or line == "---":
            break
        lines.append(line)
    return "\n".join(lines)


def extract_diff_files(patch_path: str | Path) -> list[str]:
    """Extract list of files from 'diff --git a/X b/X' lines."""
    files = set()
    for line in Path(patch_path).read_text(errors="replace").splitlines():
        m = re.match(r"^diff --git a/(.*?) b/(.*)", line)
        if m:
            files.add(m.group(1))
    return sorted(files)


def extract_change_lines(patch_path: str | Path) -> list[str]:
    """Extract only +/- lines (actual code changes) from a patch."""
    lines = []
    in_diff = False
    for line in Path(patch_path).read_text(errors="replace").splitlines():
        if line.startswith("diff --git "):
            in_diff = True
            continue
        if not in_diff:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            lines.append(line)
        elif line.startswith("-") and not line.startswith("---"):
            lines.append(line)
    return lines


def is_prologue(patch_path: str | Path) -> bool:
    """Check if a patch is a 0/N prologue."""
    subject = extract_subject(patch_path)
    m = re.search(r"\b0+/\d+", subject)
    return m is not None


def get_patch_files(directory: str | Path) -> list[Path]:
    """Return sorted list of .patch files in directory, excluding prologues."""
    d = Path(directory)
    if not d.is_dir():
        return []
    patches = sorted(d.glob("*.patch"), key=lambda p: p.name)
    return [p for p in patches if not is_prologue(p)]


def patch_number_prefix(index: int) -> str:
    """Return zero-padded 4-digit prefix for patch numbering."""
    return f"{index:04d}"


def subjects_match(
    rhel_subject: str,
    upstream_summary: str,
    fuzz: int = 1,
) -> bool:
    """Compare RHEL patch subject with upstream commit summary.

    Fuzz levels:
      0 - exact match
      1 - case insensitive
      2 - case insensitive, ignore commas
      3 - case insensitive, ignore all punctuation
    """
    if fuzz >= 1:
        rhel_subject = rhel_subject.lower()
        upstream_summary = upstream_summary.lower()

    if fuzz >= 3:
        rhel_subject = re.sub(r"[^\w\s]", "", rhel_subject)
        upstream_summary = re.sub(r"[^\w\s]", "", upstream_summary)
    elif fuzz >= 2:
        rhel_subject = rhel_subject.replace(",", "")
        upstream_summary = upstream_summary.replace(",", "")

    us_tokens = upstream_summary.split()
    rh_tokens = rhel_subject.split()

    if not us_tokens:
        return False

    # Find the start of upstream tokens within RHEL tokens
    for start in range(len(rh_tokens)):
        if rh_tokens[start] == us_tokens[0]:
            remaining_rh = rh_tokens[start:]
            if len(remaining_rh) >= len(us_tokens):
                if remaining_rh[: len(us_tokens)] == us_tokens:
                    return True

    return False


def readchar() -> str:
    """Read a single character from stdin without requiring Enter.

    Uses cbreak mode so Ctrl-C still works for signals.
    """
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def prompt_key(message: str, valid: Optional[set[str]] = None) -> str:
    """Display a prompt and read a single keypress (no Enter needed).

    If valid is provided, only accepts characters in that set (loops
    silently on invalid input).  Returns the character pressed.
    """
    from rich.console import Console
    con = Console()

    con.print(message, end="  ")
    while True:
        ch = readchar()
        if valid is None or ch in valid:
            con.print(ch)
            return ch


def confirm(message: str, default: bool = False) -> bool:
    """Ask a yes/no question, single keypress, no Enter required."""
    hint = "[Y/n]" if default else "[y/N]"
    from rich.console import Console
    con = Console()

    con.print(f"{message} {hint}", end=" ")
    while True:
        ch = readchar().lower()
        if ch in ("y", "n"):
            con.print(ch)
            return ch == "y"
        if ch in ("\r", "\n", " "):
            con.print("y" if default else "n")
            return default


_URL_RE = re.compile(r"https?://\S+")
_LORE_RE = re.compile(r"https?://lore\.kernel\.org/\S+")
_GIT_COMMIT_URL_RE = re.compile(
    r"https?://[^/]+/.+?/commit/?\?.*?id=([0-9a-fA-F]{7,40})"
)


def extract_upstream_status(patch_path: str | Path) -> Optional[str]:
    """Extract a URL from the 'Upstream status:' line in a patch header.

    Handles variants like:
      Upstream status: Posted https://lore.kernel.org/...
      Upstream status: https://lore.kernel.org/...
      Upstream Status: https://git.kernel.org/.../commit/?id=abc123
    """
    for line in Path(patch_path).read_text(errors="replace").splitlines():
        if line.startswith("diff --git "):
            break
        if re.match(r"^\s*[Uu]pstream\s+[Ss]tatus\s*:", line):
            m = _URL_RE.search(line)
            if m:
                return m.group().rstrip("/")
    return None


def is_lore_url(url: str) -> bool:
    """Return True if the URL points to lore.kernel.org."""
    return bool(_LORE_RE.match(url))


def fetch_lore_patch(url: str, dest: Path) -> bool:
    """Download a raw patch from a lore.kernel.org URL and save to dest.

    Appends /raw to the URL to get the raw email/patch content.
    Returns True on success.
    """
    raw_url = url.rstrip("/") + "/raw"
    try:
        result = subprocess.run(
            ["curl", "-sL", "--fail",
             "-A", "mr-review/2.0",
             "-o", str(dest), raw_url],
            timeout=30,
            capture_output=True,
        )
        if result.returncode != 0:
            return False
        return dest.exists() and dest.stat().st_size > 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def fetch_lore_series(url: str, outdir: Path) -> list[Path]:
    """Download a complete patch series from lore and split into files.

    Fetches the thread mbox via /t.mbox.gz, then extracts individual
    patches (messages containing 'diff --git') into outdir as
    lore-NN.patch files.

    Returns a list of saved patch file paths, sorted by subject.
    """
    import email
    import email.policy
    import gzip
    import mailbox

    lore_dir = outdir / ".lore_cache"
    lore_dir.mkdir(exist_ok=True)

    mbox_gz = lore_dir / "thread.mbox.gz"
    mbox_path = lore_dir / "thread.mbox"
    mbox_url = url.rstrip("/") + "/t.mbox.gz"

    try:
        result = subprocess.run(
            ["curl", "-sL", "--fail",
             "-A", "mr-review/2.0",
             "-o", str(mbox_gz), mbox_url],
            timeout=60,
            capture_output=True,
        )
        if result.returncode != 0:
            return []

        with gzip.open(mbox_gz, "rb") as gz:
            mbox_path.write_bytes(gz.read())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    finally:
        if mbox_gz.exists():
            mbox_gz.unlink()

    patches: list[tuple[str, str]] = []
    try:
        mbox = mailbox.mbox(str(mbox_path))
        for msg in mbox:
            body = msg.get_payload(decode=True)
            if body is None:
                if msg.is_multipart():
                    parts = []
                    for part in msg.walk():
                        pl = part.get_payload(decode=True)
                        if pl:
                            parts.append(pl.decode("utf-8", errors="replace"))
                    body_text = "\n".join(parts)
                else:
                    continue
            else:
                body_text = body.decode("utf-8", errors="replace")

            if "diff --git " not in body_text:
                continue

            subject = msg.get("Subject", "")
            subject = re.sub(r"\s+", " ", subject).strip()
            patches.append((subject, msg.as_string()))
        mbox.close()
    except Exception:
        return []
    finally:
        if mbox_path.exists():
            mbox_path.unlink()

    if not patches:
        return []

    saved: list[Path] = []
    for i, (subj, raw) in enumerate(patches, 1):
        dest = lore_dir / f"lore-{i:04d}.patch"
        dest.write_text(raw)
        saved.append(dest)

    return saved


def match_lore_patch_by_subject(
    rhel_subject: str,
    lore_patches: list[Path],
    fuzz: int = 3,
) -> Optional[Path]:
    """Find the lore patch whose subject best matches the RHEL subject.

    Uses the same fuzzy matching as commit comparison.
    """
    bare = extract_subject_bare(rhel_subject)

    for lp in lore_patches:
        lore_subj = extract_subject(lp)
        lore_bare = extract_subject_bare(lore_subj)
        if subjects_match(bare, lore_bare, fuzz=fuzz):
            return lp

    return None


def extract_commit_from_url(url: str) -> Optional[str]:
    """Try to extract a commit hash from a git web URL.

    Handles URLs like:
      https://git.kernel.org/.../commit/?id=abc123def456
    """
    m = _GIT_COMMIT_URL_RE.search(url)
    return m.group(1) if m else None


def extract_repo_from_url(url: str) -> Optional[str]:
    """Try to extract a git:// or https:// clone URL from a web URL.

    Handles cgit-style URLs like:
      https://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git/commit/?id=...
    Returns:
      https://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git
    """
    m = re.match(r"(https?://[^/]+/.+?\.git)(?:/|$)", url)
    return m.group(1) if m else None


def fetch_commit_from_alt_repo(
    commit: str,
    repo_url: str,
    cwd: Path,
) -> bool:
    """Add repo_url as a temporary remote and fetch the commit.

    Returns True if the commit is reachable after fetch.
    """
    remote_name = "_mr_review_alt"
    try:
        subprocess.run(
            ["git", "remote", "remove", remote_name],
            cwd=cwd, capture_output=True,
        )
        result = subprocess.run(
            ["git", "remote", "add", remote_name, repo_url],
            cwd=cwd, capture_output=True,
        )
        if result.returncode != 0:
            return False
        result = subprocess.run(
            ["git", "fetch", "--depth=1", remote_name, commit],
            cwd=cwd, capture_output=True, timeout=60,
        )
        return result.returncode == 0 and git_show_exists(commit, cwd=cwd)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    finally:
        subprocess.run(
            ["git", "remote", "remove", remote_name],
            cwd=cwd, capture_output=True,
        )


def display_in_pager(text: str):
    """Display text in the system pager (less/more) for searchable viewing.

    Falls back to plain print if no pager is available.
    """
    pager = os.environ.get("PAGER", "less")
    pager_cmd = shutil.which(pager) or shutil.which("less") or shutil.which("more")

    if not pager_cmd:
        from rich.console import Console
        Console().print(text)
        return

    env = os.environ.copy()
    if "less" in pager_cmd:
        env.setdefault("LESS", "-R")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False,
        ) as tmp:
            tmp.write(text)
            tmp_path = tmp.name
        subprocess.run([pager_cmd, tmp_path], env=env)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
