import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_base_path() -> Path:
    path = Path.home() / ".jira_agent_app"
    path.mkdir(exist_ok=True)
    return path


def _get_legacy_base_path() -> Path | None:
    candidates = [Path(sys.executable).parent, Path(__file__).resolve().parent.parent]
    for p in candidates:
        if (p / "settings.json").exists():
            return p
    return None


def migrate_legacy_settings() -> None:
    new_path = get_base_path() / "settings.json"
    if new_path.exists():
        return
    try:
        legacy = _get_legacy_base_path()
        if legacy is None:
            return
        shutil.copy2(legacy / "settings.json", new_path)
        logger.info("[paths] Migrated settings.json from %s to %s", legacy, new_path.parent)
    except Exception as exc:
        logger.warning("[paths] Migration failed (non-fatal): %s", exc)
