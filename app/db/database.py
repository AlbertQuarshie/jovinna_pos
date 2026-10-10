import sqlite3
from contextlib import closing
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import config
from app.db.models import Base

config.DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{config.DB_PATH}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _sqlite_settings(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")    # survives power cuts mid-sale much better
    cur.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, and faster
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


# ---- schema updates ----
# Each function upgrades the database by one version and must be safe to run on a database that
# already has the change. Add new ones to the END of the list — never reorder or remove.

def _v1_product_images(conn):
    columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(products)")}
    if "image_path" not in columns:
        conn.exec_driver_sql("ALTER TABLE products ADD COLUMN image_path VARCHAR(255)")


MIGRATIONS = [_v1_product_images]
SCHEMA_VERSION = len(MIGRATIONS)


def init_db() -> None:
    with engine.connect() as conn:
        had_tables = bool(conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='products'").first())
        version = conn.exec_driver_sql("PRAGMA user_version").scalar()

    if had_tables and version < SCHEMA_VERSION:
        _backup_before_upgrade(version)
    Base.metadata.create_all(engine)  # creates any missing tables (all of them on a new install)

    if version < SCHEMA_VERSION:
        with engine.begin() as conn:
            for migrate in MIGRATIONS[version:]:
                migrate(conn)
            conn.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")
    elif version > SCHEMA_VERSION:
        raise RuntimeError(
            f"This database was made by a newer version of the app (v{version}, this app knows v{SCHEMA_VERSION}). "
            "Install the latest version of the app.")


def _backup_before_upgrade(version: int) -> None:
    """Keep a copy of the database exactly as it was before changing its structure."""
    folder = config.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"jovinna_before_upgrade_v{version}_{datetime.now():%Y%m%d_%H%M%S}.db"
    with closing(sqlite3.connect(config.DB_PATH)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
