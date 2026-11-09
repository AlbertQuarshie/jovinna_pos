"""Preferences the owner can change in Settings (theme, shop details, backups).

Saved in DATA_DIR/settings.json and applied over the defaults in app.config when the app starts,
so updating or reinstalling the app keeps them. Not for secrets — those use secure_store.
"""
import json

from app import config

PATH = config.DATA_DIR / "settings.json"

# setting name -> name of the app.config value it overrides
CONFIG_KEYS = {
    "shop_name": "SHOP_NAME", "shop_tagline": "SHOP_TAGLINE", "shop_phone": "SHOP_PHONE",
    "shop_address": "SHOP_ADDRESS", "receipt_footer": "RECEIPT_FOOTER",
    "backup_copy_dir": "BACKUP_COPY_DIR", "backup_keep_days": "BACKUP_KEEP_DAYS",
}
_DEFAULTS = {key: getattr(config, name) for key, name in CONFIG_KEYS.items()}
_DEFAULTS["theme"] = "dark"


def load() -> dict:
    try:
        saved = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    return {**_DEFAULTS, **{k: v for k, v in saved.items() if k in _DEFAULTS}}


def save(**changes) -> dict:
    values = {**load(), **{k: v for k, v in changes.items() if k in _DEFAULTS}}
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, indent=2), encoding="utf-8")
    tmp.replace(PATH)
    apply(values)
    return values


def apply(values: dict | None = None) -> None:
    """Copy the saved values onto app.config, which the receipts, backups and screens read."""
    values = values or load()
    for key, name in CONFIG_KEYS.items():
        value = values[key]
        if key == "backup_copy_dir":
            value = value or None
        elif key == "backup_keep_days":
            value = max(1, int(value or _DEFAULTS[key]))
        setattr(config, name, value)
