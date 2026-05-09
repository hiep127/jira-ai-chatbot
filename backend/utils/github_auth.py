from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _gh_exe() -> str:
    """Return path to gh executable — bundled copy when frozen, PATH otherwise."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "tools" / "gh.exe"
        if bundled.exists():
            return str(bundled)
    return "gh"


def get_local_github_token() -> str | None:
    """Return the GitHub CLI token, or None on any failure."""
    try:
        result = subprocess.run(
            [_gh_exe(), "auth", "token"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        token = result.stdout.strip()
        return token if token else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def spawn_windows_auth_terminal() -> None:
    """Open a new cmd.exe window for interactive 'gh auth login'.

    CREATE_NEW_CONSOLE forces Windows to open a visible terminal window so the
    user can interact with gh's arrow-key prompts. Without it the subprocess
    inherits the parent's hidden console and the user sees nothing.
    """
    gh = _gh_exe()
    subprocess.Popen(
        ["cmd.exe", "/c", f'"{gh}" auth login & echo. & pause'],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
