"""
Release build automation.

Steps:
  1. Run PyInstaller with the existing spec (preserves all custom hiddenimports).
  2. Copy tools/jira_server.env into dist/JiraAgent/tools/.
  3. Download gh.exe (GitHub CLI) into dist/JiraAgent/tools/ if not already present.
  4. Copy wiki/ into dist/JiraAgent/wiki/ if present.
  5. Report success.

Usage:
    python build_release.py

Note: verify the Flet version matches requirements.txt before building.
Run `python -c "import flet; print(flet.__version__)"` to confirm.
"""

import io
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


def _check_prerequisites(root: Path) -> None:
    import importlib.metadata
    try:
        installed = importlib.metadata.version("flet")
        required = (root / "requirements.txt").read_text().splitlines()
        pinned = next((l.split("==")[1] for l in required if l.startswith("flet==")), None)
        if pinned and installed != pinned:
            print(f"WARNING: flet {installed} installed but requirements.txt pins flet=={pinned}.")
            print("         Run: pip install -r requirements.txt")
            print()
    except Exception:
        pass


def _bundle_gh(tools_dir: Path) -> None:
    """Download the latest gh.exe from GitHub releases into tools_dir."""
    gh_dst = tools_dir / "gh.exe"
    if gh_dst.exists():
        print("  gh.exe already present — skipped download.")
        return

    print("  Fetching latest GitHub CLI release info...")
    req = urllib.request.Request(
        "https://api.github.com/repos/cli/cli/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "build_release.py"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    asset = next(
        a for a in data["assets"]
        if "windows_amd64.zip" in a["name"] and "msi" not in a["name"]
    )

    print(f"  Downloading {asset['name']} ({asset['size'] // (1024*1024)} MB)...")
    with urllib.request.urlopen(asset["browser_download_url"], timeout=120) as resp:
        zip_data = resp.read()

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        gh_entry = next(n for n in zf.namelist() if n.endswith("bin/gh.exe"))
        tools_dir.mkdir(parents=True, exist_ok=True)
        with zf.open(gh_entry) as src, open(gh_dst, "wb") as dst:
            dst.write(src.read())

    print(f"  gh.exe bundled → {gh_dst}")


def main() -> None:
    root = Path(__file__).parent

    _check_prerequisites(root)

    print("[1/4] Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "Jira AI.spec", "--noconfirm", "--distpath", "dist"],
        cwd=root,
    )
    if result.returncode != 0:
        print("\nBUILD FAILED. See errors above.")
        sys.exit(result.returncode)

    dist = root / "dist" / "JiraAgent"
    tools_dir = dist / "tools"

    print("[2/4] Copying .env template...")
    env_src = root / "tools" / "jira_server.env"
    if env_src.exists():
        tools_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_src, tools_dir / "jira_server.env")
        print("  Copied tools/jira_server.env")
    else:
        print("  tools/jira_server.env not found — skipped.")

    print("[3/4] Bundling GitHub CLI (gh.exe)...")
    try:
        _bundle_gh(tools_dir)
    except Exception as exc:
        print(f"  WARNING: could not download gh.exe: {exc}")
        print("  Customers will need GitHub CLI installed manually.")

    print("[4/4] Copying wiki/...")
    wiki_src = root / "wiki"
    if wiki_src.exists():
        shutil.copytree(wiki_src, dist / "wiki", dirs_exist_ok=True)
        print("  Copied wiki/")
    else:
        print("  wiki/ not found — skipped.")

    print(f"\nBUILD SUCCEEDED. Output is in: dist/JiraAgent/")


if __name__ == "__main__":
    main()
