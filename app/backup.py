"""Automatic backups of the local SQLite database (backups/ folder).

A backup is a complete, consistent copy made with SQLite's own backup API, so it is safe even while participants
are being recorded. Made: when the site starts, every 15 minutes while it runs (only if data changed), after each
participant finishes, before deletes and imports, and at freeze. The newest KEEP backups are kept.
"""
import sqlite3
from contextlib import closing
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config

KEEP = 40
INTERVAL_S = 15 * 60
_lock = threading.Lock()
_last_size = {"v": None}


def db_path():
    url = config.DATABASE_URL
    if not url.startswith("sqlite:///"):
        return None                     # cloud database: backups are the provider's job
    return Path(url[len("sqlite:///"):])


# backups/ sits next to the database file (the project folder for the real study)
BACKUP_DIR = (db_path().parent if db_path() else config.ROOT) / "backups"


def _copy_to(dest: Path):
    src = db_path()
    with closing(sqlite3.connect(src)) as s, closing(sqlite3.connect(dest)) as d:
        s.backup(d)


def make_backup(reason="auto"):
    src = db_path()
    if src is None or not src.exists():
        return None
    with _lock:
        BACKUP_DIR.mkdir(exist_ok=True)
        dest = BACKUP_DIR / f"hti_study_{datetime.now():%Y%m%d_%H%M%S}_{reason}.db"
        _copy_to(dest)
        old = sorted(BACKUP_DIR.glob("hti_study_*.db"))
        for f in old[:-KEEP]:
            f.unlink(missing_ok=True)
    return dest


def fresh_copy(dest: Path):
    """A consistent single-file copy for downloading."""
    with _lock:
        _copy_to(dest)


def checkpoint():
    """Write everything into hti_study.db itself, so the file alone is complete after the site stops."""
    src = db_path()
    if src is None or not src.exists():
        return
    with closing(sqlite3.connect(src)) as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _changed():
    src = db_path()
    wal = Path(str(src) + "-wal")
    size = (src.stat().st_size if src.exists() else 0, wal.stat().st_size if wal.exists() else 0,
            src.stat().st_mtime if src.exists() else 0, wal.stat().st_mtime if wal.exists() else 0)
    if size != _last_size["v"]:
        _last_size["v"] = size
        return True
    return False


def start_periodic():
    if db_path() is None:
        return

    def loop():
        while True:
            time.sleep(INTERVAL_S)
            try:
                if _changed():
                    make_backup("auto")
            except Exception:  # noqa: BLE001 - a failed backup must never stop the study
                pass

    _changed()
    threading.Thread(target=loop, daemon=True, name="db-backup").start()


def list_backups():
    if not BACKUP_DIR.exists():
        return []
    return [{"name": f.name, "size_kb": round(f.stat().st_size / 1024), "time": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")}
            for f in sorted(BACKUP_DIR.glob("hti_study_*.db"), reverse=True)]


def safe_name(name):
    return BACKUP_DIR / Path(name).name if name.startswith("hti_study_") and name.endswith(".db") else None

