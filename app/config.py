"""Shop-wide settings. Change these to match the business."""
from pathlib import Path

SHOP_NAME = "Jovinna General Agencies"
SHOP_TAGLINE = "Stationery & Phone Accessories"
SHOP_PHONE = "+254 725 000 081"
SHOP_ADDRESS = "Buruburu Complex Ground Floor, Opposite Buruburu Police Station, Nairobi, Kenya"

CURRENCY = "KES"

RECEIPT_FOOTER = "Welcome Back Anytime"

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "jovinna.db"
