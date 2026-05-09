"""
Release build automation.

Steps:
  1. Run PyInstaller with the existing spec (preserves all custom hiddenimports).
  2. Copy tools/jira_server.env into dist/JiraAgent/tools/.
  3. Copy wiki/ into dist/JiraAgent/wiki/ if present.
  4. Report success.

Usage:
    python build_release.py

Note: verify the Flet version matches requirements.txt before building.
Run `python -c "import flet; print(flet.__version__)"` to confirm.
"""

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).parent

    print("[1/3] Running PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "Jira AI.spec", "--noconfirm", "--distpath", "dist"],
        cwd=root,
    )
    if result.returncode != 0:
        print("\nBUILD FAILED. See errors above.")
        sys.exit(result.returncode)

    dist = root / "dist" / "JiraAgent"

    print("[2/3] Copying .env template...")
    env_src = root / "tools" / "jira_server.env"
    if env_src.exists():
        env_dst = dist / "tools"
        env_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_src, env_dst / "jira_server.env")
        print("  Copied tools/jira_server.env")
    else:
        print("  tools/jira_server.env not found — skipped.")

    print("[3/3] Copying wiki/...")
    wiki_src = root / "wiki"
    if wiki_src.exists():
        shutil.copytree(wiki_src, dist / "wiki", dirs_exist_ok=True)
        print("  Copied wiki/")
    else:
        print("  wiki/ not found — skipped.")

    print(f"\nBUILD SUCCEEDED. Output is in: dist/JiraAgent/")


if __name__ == "__main__":
    main()
