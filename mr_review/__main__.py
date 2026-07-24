"""Entry point for python3 -m mr_review."""

import importlib
import subprocess
import sys

REQUIRED_MODULES = {
    "click": "click",
    "rich": "rich",
}


def _ensure_dependencies():
    """Check for required Python modules and install any that are missing."""
    missing = []
    for import_name, pip_name in REQUIRED_MODULES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)

    if not missing:
        return

    names = ", ".join(missing)
    print(f"mr-review: installing missing Python module(s): {names}")
    cmd = [sys.executable, "-m", "pip", "install", "--user"] + missing
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError:
        print(
            f"mr-review: failed to install {names}.\n"
            f"  Try manually:  pip3 install --user {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError:
        print(
            f"mr-review: pip not found. Install pip first:\n"
            f"  sudo dnf install python3-pip\n"
            f"  Then:  pip3 install --user {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)


_ensure_dependencies()

from .cli import main

if __name__ == "__main__":
    main()
