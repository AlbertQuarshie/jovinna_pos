import sqlite3
from contextlib import closing
from datetime import datetime

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app import config
from app.db.models import Base, Category

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
# already has the change (a new install gets the latest tables from create_all). Functions get a
# plain sqlite3 connection inside a transaction with foreign-key checks paused, so they can rebuild
# tables. Add new ones to the END of the list — never reorder or remove.

def _columns(db, table: str) -> set[str]:
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})")}


def _v1_product_images(db):
    if "image_path" not in _columns(db, "products"):
        db.execute("ALTER TABLE products ADD COLUMN image_path VARCHAR(255)")


def _v2_subcategories(db):
    """Categories get a parent (main category). Names become unique per parent instead of
    shop-wide, which SQLite can only do by rebuilding the table (ids are kept, so products keep
    their categories)."""
    if "parent_id" not in _columns(db, "categories"):
        db.execute("""
            CREATE TABLE categories_new (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                parent_id INTEGER REFERENCES categories (id),
                UNIQUE (parent_id, name)
            )""")
        db.execute("INSERT INTO categories_new (id, name) SELECT id, name FROM categories")
        db.execute("DROP TABLE categories")
        db.execute("ALTER TABLE categories_new RENAME TO categories")
    # The first version's "Phone Accessories" becomes the main "Accessories" category
    has_accessories = db.execute(
        "SELECT 1 FROM categories WHERE name = 'Accessories' AND parent_id IS NULL").fetchone()
    if not has_accessories:
        db.execute("UPDATE categories SET name = 'Accessories' "
                   "WHERE name = 'Phone Accessories' AND parent_id IS NULL")


def _v3_only_two_main_categories(db):
    """Only the shop's main categories (Accessories, Stationery) stay at the top. Any other
    top-level category (e.g. "Speakers") becomes a subcategory of Accessories; if Accessories
    already has a subcategory with that name, the products are merged into it."""
    def main_id(name):
        row = db.execute("SELECT id FROM categories WHERE name = ? AND parent_id IS NULL", (name,)).fetchone()
        if row:
            return row[0]
        return db.execute("INSERT INTO categories (name) VALUES (?)", (name,)).lastrowid
    mains = [main_id(name) for name in config.MAIN_CATEGORIES]
    default_parent = mains[0]
    others = db.execute("SELECT id, name FROM categories WHERE parent_id IS NULL AND id NOT IN (%s)"
                        % ",".join("?" * len(mains)), mains).fetchall()
    for cat_id, name in others:
        same = db.execute("SELECT id FROM categories WHERE parent_id = ? AND lower(name) = lower(?)",
                          (default_parent, name)).fetchone()
        if same:
            db.execute("UPDATE products SET category_id = ? WHERE category_id = ?", (same[0], cat_id))
            db.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (default_parent, cat_id))
            db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
        else:
            # its own subcategories (if any) move up to Accessories too
            db.execute("UPDATE categories SET parent_id = ? WHERE parent_id = ?", (default_parent, cat_id))
            db.execute("UPDATE categories SET parent_id = ? WHERE id = ?", (default_parent, cat_id))


MIGRATIONS = [_v1_product_images, _v2_subcategories, _v3_only_two_main_categories]
SCHEMA_VERSION = len(MIGRATIONS)


def init_db() -> None:
    with engine.connect() as conn:
        had_tables = bool(conn.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='products'").first())
        version = conn.exec_driver_sql("PRAGMA user_version").scalar()
    engine.dispose()  # release the file before upgrading it through its own connection

    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"This database was made by a newer version of the app (v{version}, this app knows v{SCHEMA_VERSION}). "
            "Install the latest version of the app.")
    if had_tables and version < SCHEMA_VERSION:
        _backup_before_upgrade(version)
    Base.metadata.create_all(engine)  # creates any missing tables (all of them on a new install)
    engine.dispose()
    if version < SCHEMA_VERSION:
        _run_migrations(version)
    _ensure_main_categories()


def _run_migrations(version: int) -> None:
    """All pending updates in one transaction: either every change is applied, or none."""
    with closing(sqlite3.connect(config.DB_PATH, isolation_level=None)) as db:
        db.execute("PRAGMA foreign_keys=OFF")  # only possible outside a transaction
        db.execute("BEGIN IMMEDIATE")
        try:
            for migrate in MIGRATIONS[version:]:
                migrate(db)
            broken = db.execute("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(f"Database update would break links between records: {broken[:5]}")
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.execute("PRAGMA foreign_keys=ON")


def _ensure_main_categories() -> None:
    with SessionLocal() as session, session.begin():
        existing = set(session.scalars(select(Category.name).where(Category.parent_id.is_(None))))
        for name in config.MAIN_CATEGORIES:
            if name not in existing:
                session.add(Category(name=name))


def _backup_before_upgrade(version: int) -> None:
    """Keep a copy of the database exactly as it was before changing its structure."""
    folder = config.DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"jovinna_before_upgrade_v{version}_{datetime.now():%Y%m%d_%H%M%S}.db"
    with closing(sqlite3.connect(config.DB_PATH)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
