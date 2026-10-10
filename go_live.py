"""One-time reset before the shop starts using the system for real.

Moves ALL current data — products, photos, sales, users, receipts, labels and earlier backups — into
data/backups/test_data_<date>/ so nothing is lost, and leaves the app empty. On its next start the
app asks for a new owner (admin) account. Receipt numbers start again at #000001.

Close the POS app first, then run:  .venv\\Scripts\\python.exe go_live.py
"""
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime

from app import config

DATA = config.DATA_DIR
BACKUPS = DATA / "backups"
CONFIRM = "GO LIVE"


def summary() -> str:
    if not config.DB_PATH.exists():
        return "  (no database found)"
    with closing(sqlite3.connect(config.DB_PATH)) as db:
        def count(table):
            try:
                return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                return 0
        return (f"  {count('products')} products, {count('sales')} sales, "
                f"{count('users')} user accounts")


def main() -> int:
    print(__doc__)
    print("Current data:")
    print(summary())
    print()
    answer = input(f'Type {CONFIRM} (in capitals) to continue, or anything else to cancel: ').strip()
    if answer != CONFIRM:
        print("Cancelled. Nothing was changed.")
        return 1

    archive = BACKUPS / f"test_data_{datetime.now():%Y%m%d_%H%M%S}"
    archive.mkdir(parents=True)

    # 1. Consistent copy of the database (includes anything still in the WAL file)
    if config.DB_PATH.exists():
        target = archive / config.DB_PATH.name
        with closing(sqlite3.connect(config.DB_PATH)) as src, closing(sqlite3.connect(target)) as dst:
            src.backup(dst)

    # 2. Remove the live database. Fails if the app is still open — in that case stop before
    #    touching anything else.
    db_files = [config.DB_PATH, config.DB_PATH.with_name(config.DB_PATH.name + "-wal"),
                config.DB_PATH.with_name(config.DB_PATH.name + "-shm")]
    try:
        for f in db_files:
            if f.exists():
                f.rename(archive / (f.name + ".live"))
    except PermissionError:
        for f in archive.glob("*.live"):  # put back anything already moved
            f.rename(DATA / f.name.removesuffix(".live"))
        shutil.rmtree(archive)
        print("\nThe database is in use. Close the POS app completely, then run this again.")
        print("Nothing was changed.")
        return 1
    for f in archive.glob("*.live"):
        f.unlink()  # the clean copy from step 1 is the one we keep

    # 3. Move receipts, labels, photos and any other files
    for item in DATA.iterdir():
        if item.name != "backups":
            shutil.move(str(item), str(archive / item.name))
    # ...and earlier backups (they contain test data too), but not older test_data archives
    for item in BACKUPS.iterdir():
        if item != archive and not item.name.startswith("test_data_"):
            shutil.move(str(item), str(archive / item.name))

    print(f"\nDone. All test data was moved to:\n  {archive}")
    print("\nNext: start the app. It will ask you to create the owner (admin) account.")
    print("Then add your products with their real stock counts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
