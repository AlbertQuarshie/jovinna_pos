"""Shop-wide settings. Change these to match the business."""
import os
import sys
from pathlib import Path

APP_NAME = "Jovinna POS"
APP_ID = "JovinnaPOS"  # folder and file names, no spaces
APP_VERSION = "1.1.0"
PUBLISHER = "Aeternum Devs"

SHOP_NAME = "Jovinna General Agencies"
SHOP_TAGLINE = "Stationery & Phone Accessories"
SHOP_PHONE = "+254 725 000 081"
SHOP_ADDRESS = "Buruburu Complex Ground Floor, Opposite Buruburu Police Station, Nairobi, Kenya"

CURRENCY = "KES"

# The shop's main product groups. Always present; subcategories (Chargers, Pens…) are added under
# them when adding products.
MAIN_CATEGORIES = ["Accessories", "Stationery"]

RECEIPT_FOOTER = "Welcome Back Anytime"

FROZEN = getattr(sys, "frozen", False)  # True when running as the installed JovinnaPOS.exe

# Bundled read-only files (fonts, icon): next to the code, or inside the exe's bundle folder
BASE_DIR = Path(sys._MEIPASS) if FROZEN else Path(__file__).resolve().parent.parent

# Shop data (database, photos, receipts, backups). The installed app can't write to Program Files,
# so it uses C:\Users\<user>\AppData\Local\JovinnaPOS — updates and reinstalls never touch it.
if os.environ.get("JOVINNA_DATA_DIR"):
    DATA_DIR = Path(os.environ["JOVINNA_DATA_DIR"])
elif FROZEN:
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_ID
else:
    DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jovinna.db"

# Automatic backups: a copy of the database for each day, kept for this many days
BACKUP_KEEP_DAYS = 30
BACKUP_EVERY_MINUTES = 60
# Optional second copy somewhere safer, e.g. a Google Drive or OneDrive folder or a flash drive:
#   BACKUP_COPY_DIR = r"C:\Users\Owner\Google Drive\Jovinna backups"
BACKUP_COPY_DIR = None
