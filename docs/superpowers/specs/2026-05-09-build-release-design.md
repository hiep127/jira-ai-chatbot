# Build Release Design

**Date:** 2026-05-09  
**Topic:** Packaging the app as a distributable `--onedir` build with asset copying  
**Status:** Approved

---

## Problem

The existing PyInstaller spec (`Jira AI.spec`) produces a single-file exe (`--onefile`). The goal is to switch to `--onedir` so users can see and modify the `wiki/` folder and `.env` configuration next to the executable, and to automate the full release build including asset copying via a single Python script.

---

## Architecture

Three coordinated changes:

1. **`Jira AI.spec`** — converted from onefile to onedir mode
2. **`build_release.py`** — new root-level automation script
3. **`config/paths.py`** — new `get_base_path()` utility for frozen-exe path resolution
4. **`build_installer.iss`** — updated `SourceDir` to match new output folder name

---

## Section 1: Spec Update (`Jira AI.spec`)

Replace the monolithic `EXE` block with a lean `EXE` + `COLLECT` pattern.

**Before (onefile):**
```python
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='Jira AI', console=False, ...)
```

**After (onedir):**
```python
exe = EXE(
    pyz, a.scripts, [], [],
    exclude_binaries=True,
    name='Jira AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JiraAgent',
)
```

Output: `dist/JiraAgent/Jira AI.exe` with all DLLs and data files alongside it.

All existing customizations are preserved: `collect_all` for the five LangChain packages and all `hiddenimports` for uvicorn/fastapi/keyring remain unchanged.

`console=False` (windowed mode) is kept — the backend runs as an in-process thread, not a subprocess, so no console streaming is needed.

---

## Section 2: `build_release.py`

New file at the project root. Steps:

1. Run PyInstaller using the existing spec:
   ```
   python -m PyInstaller "Jira AI.spec" --noconfirm --distpath dist
   ```
2. Copy `tools/jira_server.env` → `dist/JiraAgent/tools/jira_server.env` (preserves relative path structure).
3. Copy `wiki/` → `dist/JiraAgent/wiki/` if the source folder exists; print a skip notice otherwise (no crash).
4. Print a success message pointing to `dist/JiraAgent/`.
5. Exit with a non-zero code if PyInstaller fails (CI-friendly).

Implementation uses only stdlib: `subprocess`, `shutil`, `pathlib.Path`, `sys`.

---

## Section 3: `config/paths.py` — `get_base_path()`

```python
import sys
from pathlib import Path

def get_base_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent   # dist/JiraAgent/
    return Path(__file__).resolve().parent.parent  # project root
```

No callers yet — the MCP tools don't run when frozen (`sys.frozen` guard in `backend/main.py`). This establishes the pattern for future code that needs to locate `wiki/` or other assets at runtime.

---

## Section 4: `build_installer.iss` Update

Change `SourceDir` from `dist\Jira AI` to `dist\JiraAgent` so InnoSetup picks up the new onedir output folder.

---

## Constraints

- `--onefile` is explicitly not used. Users must be able to see/edit `wiki/` next to the exe.
- `--windowed` (`console=False`) is used. The backend is in-process; no console streaming required.
- No new packages introduced. All stdlib.
- The `wiki/` copy step is non-fatal if the folder is absent.
