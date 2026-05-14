from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_auth_cache: bool | None = None


def _gh_exe() -> str:
    """Return path to gh executable.

    Search order:
    1. Frozen (.exe): tools/gh.exe next to the executable (placed by build_release.py).
    2. Dev mode: tools/gh.exe at the project root (downloaded by build_release.py).
    3. Fallback: "gh" from the system PATH.
    """
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "tools" / "gh.exe"
    else:
        # backend/utils/github_auth.py → ../../.. == project root
        bundled = Path(__file__).parent.parent.parent / "tools" / "gh.exe"
    if bundled.exists():
        return str(bundled)
    return "gh"


def get_local_github_token() -> str | None:
    """Return the GitHub CLI token, or None on any failure."""
    try:
        result = subprocess.run(
            [_gh_exe(), "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        token = result.stdout.strip()
        return token if token else None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def check_auth(force: bool = False) -> bool:
    """Return cached auth status, or run a fresh subprocess check if forced or uncached."""
    global _auth_cache
    if not force and _auth_cache is not None:
        return _auth_cache
    _auth_cache = get_local_github_token() is not None
    return _auth_cache


def spawn_windows_auth_terminal() -> None:
    """Open a new cmd.exe window for interactive 'gh auth login'.

    CREATE_NEW_CONSOLE forces Windows to open a visible terminal window so the
    user can interact with gh's arrow-key prompts. Without it the subprocess
    inherits the parent's hidden console and the user sees nothing.
    """
    gh = _gh_exe()
    subprocess.Popen(
        f'cmd.exe /c ""{gh}" auth login & echo. & pause"',
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
