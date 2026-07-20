"""Backward-compatible config manager for .data/patchreview.conf.

Reads and writes the same 'key = value' format used by the bash
config-manager.source, so the old and new tools can share config.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Optional

TEMPLATE_KEYS: list[tuple[str, str]] = [
    ("menumode", "0"),
    ("patchvalfuzz", "3"),
    ("applyfailmode", "0"),
    ("applymode", "0"),
    ("cmpmode", "1"),
    ("editor", ""),
    ("indir", ""),
    ("outdir", ""),
    ("background", ""),
    ("remote_dir", ""),
    ("remote_repo", ""),
    ("remote_branch", ""),
    ("mergelist_filter", ""),
    ("opmode", "0"),
    ("current_mr", ""),
    ("b_rename_infiles", "false"),
    ("b_fmt_upstream", "true"),
    ("b_verbose", "true"),
    ("b_mrcomments", "true"),
    ("b_seekfixes", "true"),
    ("b_reviewed", "false"),
    ("b_acked", "false"),
    ("b_nacked", "false"),
    ("b_unapp", "false"),
    # New keys for mr-review
    ("mega_merge_threshold", "10"),
    ("mega_merge_default_strategy", "prompt"),
    ("b_ask_continue", "false"),
    ("b_ask_replace", "false"),
    ("b_ask_commit", "false"),
    ("b_show_comments", "true"),
]

BOOL_KEYS = {
    "b_rename_infiles", "b_fmt_upstream", "b_verbose", "b_mrcomments",
    "b_seekfixes", "b_reviewed", "b_acked", "b_nacked", "b_unapp",
    "b_ask_continue", "b_ask_replace", "b_ask_commit", "b_show_comments",
}

INT_KEYS = {
    "menumode", "patchvalfuzz", "applyfailmode", "applymode", "cmpmode",
    "background", "opmode", "mega_merge_threshold",
}


class Config:
    """Read/write .data/patchreview.conf in the working repo directory."""

    def __init__(self, repo_dir: Optional[str] = None):
        if repo_dir is None:
            repo_dir = os.getcwd()
        self.repo_dir = Path(repo_dir)
        self.data_dir = self.repo_dir / ".data"
        self.config_path = self.data_dir / "patchreview.conf"
        self._items: OrderedDict[str, str] = OrderedDict()
        self._load()

    def _load(self):
        """Load config from file, filling missing keys from template."""
        template = OrderedDict(TEMPLATE_KEYS)

        if self.config_path.exists():
            for line in self.config_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                self._items[key.strip()] = val.strip()

        for key, default in template.items():
            if key not in self._items:
                self._items[key] = default

    def save(self):
        """Write config back to file in the original format."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        max_key_len = max(len(k) for k in self._items) if self._items else 0
        lines = []
        for key, val in self._items.items():
            padding = " " * (max_key_len - len(key))
            lines.append(f"{key}{padding} = {val}")
        self.config_path.write_text("\n".join(lines) + "\n")

    def get(self, key: str, default: str = "") -> str:
        """Get a raw string value."""
        return self._items.get(key, default)

    def get_bool(self, key: str) -> bool:
        val = self.get(key, "false")
        return val.lower() in ("true", "1", "yes")

    def get_int(self, key: str, default: int = 0) -> int:
        val = self.get(key, str(default))
        try:
            return int(val)
        except ValueError:
            return default

    def get_path(self, key: str) -> Optional[Path]:
        val = self.get(key)
        if not val:
            return None
        return Path(val)

    def set(self, key: str, value: Any):
        """Set a config value (converts bools and ints to strings)."""
        if isinstance(value, bool):
            self._items[key] = "true" if value else "false"
        elif isinstance(value, Path):
            self._items[key] = str(value)
        else:
            self._items[key] = str(value)

    def __getitem__(self, key: str) -> str:
        return self.get(key)

    def __setitem__(self, key: str, value: Any):
        self.set(key, value)

    @property
    def editor(self) -> str:
        return self.get("editor", "vimdiff")

    @property
    def indir(self) -> Optional[Path]:
        return self.get_path("indir")

    @property
    def outdir(self) -> Optional[Path]:
        return self.get_path("outdir")

    @property
    def remote_dir(self) -> Optional[Path]:
        return self.get_path("remote_dir")

    @property
    def remote_repo(self) -> str:
        return self.get("remote_repo")

    @property
    def remote_branch(self) -> str:
        return self.get("remote_branch")

    @property
    def verbose(self) -> bool:
        return self.get_bool("b_verbose")

    @property
    def seek_fixes(self) -> bool:
        return self.get_bool("b_seekfixes")

    @property
    def mega_merge_threshold(self) -> int:
        return self.get_int("mega_merge_threshold", 10)

    @property
    def mega_merge_default_strategy(self) -> str:
        return self.get("mega_merge_default_strategy", "prompt")

    @property
    def patchvalfuzz(self) -> int:
        return self.get_int("patchvalfuzz", 1)

    def reload(self, repo_dir: str) -> None:
        """Re-initialize config from a different repo directory."""
        self.repo_dir = Path(repo_dir)
        self.data_dir = self.repo_dir / ".data"
        self.config_path = self.data_dir / "patchreview.conf"
        self._items = OrderedDict()
        self._load()

    @property
    def ask_continue(self) -> bool:
        return self.get_bool("b_ask_continue")

    @property
    def ask_replace(self) -> bool:
        return self.get_bool("b_ask_replace")

    @property
    def ask_commit(self) -> bool:
        return self.get_bool("b_ask_commit")

    @property
    def show_comments(self) -> bool:
        return self.get_bool("b_show_comments")

    @property
    def current_mr(self) -> str:
        return self.get("current_mr")
