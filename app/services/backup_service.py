"""Automatic daily backups of the database.

One file per day (data/backups/daily/jovinna_YYYY-MM-DD.db), refreshed when the app starts, every
hour while it runs, and when it closes. The last BACKUP_KEEP_DAYS days are kept. If BACKUP_COPY_DIR
is set, each backup is also copied there (a cloud-synced folder or a flash drive).

Backups never stop the shop from selling: failures are written to backup.log instead of raised.
"""
import shutil
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from app import config

DAILY_DIR = config.DATA_DIR / "backups" / "daily"
LOG_FILE = config.DATA_DIR / "backups" / "backup.log"


def _log(message: str) -> None:
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")
    except OSError:
        pass


def copy_database(target: Path) -> None:
    """Consistent copy of the live database (safe while the app is running)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    with closing(sqlite3.connect(config.DB_PATH)) as src, closing(sqlite3.connect(tmp)) as dst:
        src.backup(dst)
    tmp.replace(target)  # only replace the old backup once the new one is complete


def daily_backup() -> Path | None:
    if not config.DB_PATH.exists():
        return None
    target = DAILY_DIR / f"jovinna_{date.today():%Y-%m-%d}.db"
    try:
        copy_database(target)
        _prune()
    except Exception as e:  # noqa: BLE001 — must never crash the app
        _log(f"FAILED daily backup: {e}")
        return None

    if config.BACKUP_COPY_DIR:
        extra = Path(config.BACKUP_COPY_DIR)
        try:
            if not extra.exists():
                raise FileNotFoundError(f"{extra} not found (flash drive unplugged?)")
            shutil.copy2(target, extra / target.name)
        except Exception as e:  # noqa: BLE001
            _log(f"FAILED copy to {extra}: {e}")
    return target


def _prune() -> None:
    backups = sorted(DAILY_DIR.glob("jovinna_*.db"))
    for old in backups[:-config.BACKUP_KEEP_DAYS]:
        old.unlink(missing_ok=True)


def latest_backup() -> Path | None:
    backups = sorted(DAILY_DIR.glob("jovinna_*.db"))
    return backups[-1] if backups else None
