import sqlite3
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import config
from app.db.models import Base, Category, Product

config.DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(f"sqlite:///{config.DB_PATH}")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _seed_sample_data()


# Columns added after the first release. create_all() only creates missing tables, so older
# databases get these via ALTER TABLE. (To be replaced by Alembic migrations.)
_NEW_COLUMNS = {
    "products": {"image_path": "VARCHAR(255)"},
}


def _add_missing_columns() -> None:
    with engine.connect() as conn:
        missing = []
        for table, columns in _NEW_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            missing += [(table, col, sql_type) for col, sql_type in columns.items() if col not in existing]
    if not missing:
        return

    # Keep a copy of the database as it was before changing its structure
    backup_dir = config.DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"jovinna_before_upgrade_{datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(config.DB_PATH) as src, sqlite3.connect(backup) as dst:
        src.backup(dst)

    with engine.begin() as conn:
        for table, col, sql_type in missing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}")


def _seed_sample_data() -> None:
    """Adds a few demo products on first run so the POS can be tried straight away."""
    with SessionLocal() as session:
        if session.scalar(select(Product.id).limit(1)):
            return

        stationery = Category(name="Stationery")
        accessories = Category(name="Phone Accessories")
        session.add_all([stationery, accessories])

        samples = [
            ("1001", "A4 Exercise Book 96pg", stationery, "35", "50", 100),
            ("1002", "Blue Ballpoint Pen", stationery, "12", "20", 200),
            ("1003", "HB Pencil", stationery, "8", "15", 150),
            ("1004", "Mathematical Set", stationery, "120", "180", 30),
            ("2001", "USB-C Charging Cable 1m", accessories, "150", "300", 40),
            ("2002", "Tempered Glass Screen Protector", accessories, "60", "200", 60),
            ("2003", "Wired Earphones", accessories, "180", "350", 25),
            ("2004", "Phone Case (Silicone)", accessories, "120", "250", 35),
        ]
        for barcode, name, cat, cost, price, qty in samples:
            session.add(Product(
                barcode=barcode, name=name, category=cat,
                cost_price=Decimal(cost), selling_price=Decimal(price), stock_qty=qty,
            ))
        session.commit()
