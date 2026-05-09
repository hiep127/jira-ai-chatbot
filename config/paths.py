import sys
from pathlib import Path


def get_base_path() -> Path:
    """Return the app's runtime root regardless of execution context.

    - Frozen exe (PyInstaller --onedir): returns the folder containing the exe,
      i.e. dist/JiraAgent/, where wiki/ and tools/ live alongside it.
    - Script: returns the project root (two levels above this file).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
