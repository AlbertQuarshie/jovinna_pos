"""Dark theme with amber accents: colours, fonts, icons and the app-wide stylesheet."""
from functools import lru_cache

import qtawesome as qta
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton

from app import config

# ---- colours ----
BG = "#161615"          # app background
SIDEBAR = "#0F0F0E"
SURFACE = "#1F1F1D"     # panels, cards
SURFACE_2 = "#282826"   # inputs, tiles
SURFACE_3 = "#33332F"   # hover
BORDER = "#393935"
TEXT = "#F1EFE8"
MUTED = "#A3A19A"
FAINT = "#6E6D68"
ACCENT = "#EF9F27"
ACCENT_HOVER = "#F7B348"
ACCENT_SOFT = "#3A2A10"  # amber tint behind selected items
ON_ACCENT = "#2A1A02"
DANGER = "#E5534B"
DANGER_SOFT = "#3A1F1D"
SUCCESS = "#4CC38A"

# Placeholder tile colours for products without a photo (background, letters)
TILE_COLOURS = [("#3A2A10", "#FAC775"), ("#13304A", "#85B7EB"), ("#2E2A52", "#AFA9EC"),
                ("#123A2E", "#5DCAA5"), ("#47201A", "#F0997B"), ("#45192C", "#ED93B1")]

FONT_TEXT = "Space Grotesk"
FONT_MONO = "JetBrains Mono"


def load_fonts() -> None:
    """Register the bundled fonts; Qt falls back to the system font if a file is missing."""
    global FONT_TEXT, FONT_MONO
    fonts_dir = config.BASE_DIR / "assets" / "fonts"
    families = {}
    for file in fonts_dir.glob("*.ttf"):
        font_id = QFontDatabase.addApplicationFont(str(file))
        for family in QFontDatabase.applicationFontFamilies(font_id):
            families[family.lower()] = family
    FONT_TEXT = families.get("space grotesk", "Segoe UI")
    FONT_MONO = families.get("jetbrains mono", "Consolas")


def mono(size: int = 13, bold: bool = False) -> QFont:
    f = QFont(FONT_MONO, size)
    f.setPixelSize(size)
    f.setBold(bold)
    return f


def icon(name: str, color: str = MUTED, active_color: str | None = None) -> QIcon:
    """Phosphor icon, e.g. icon("shopping-cart"). active_color is used when a button is checked."""
    if active_color:
        return qta.icon(f"ph.{name}", color=color, color_active=active_color, color_on=active_color)
    return qta.icon(f"ph.{name}", color=color)


def button(text: str = "", icon_name: str | None = None, variant: str = "secondary",
           tooltip: str = "") -> QPushButton:
    """variant: primary (amber), secondary (outlined), ghost (no border), danger."""
    b = QPushButton(text)
    b.setProperty("variant", variant)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        colour = {"primary": ON_ACCENT, "danger": DANGER}.get(variant, TEXT if text else MUTED)
        b.setIcon(icon(icon_name, colour))
    if tooltip:
        b.setToolTip(tooltip)
    return b


def initials(name: str) -> str:
    words = [w for w in name.replace("-", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def tile_colours(key: str) -> tuple[str, str]:
    return TILE_COLOURS[sum(map(ord, key or "?")) % len(TILE_COLOURS)]


@lru_cache(maxsize=512)
def product_pixmap(image_path: str | None, name: str, category: str, w: int, h: int, radius: int = 8) -> QPixmap:
    """Product photo cropped to fill w×h with rounded corners, or a coloured initials tile."""
    from app.services.image_service import image_file

    ratio = QApplication.instance().devicePixelRatio() if QApplication.instance() else 1.0
    out = QPixmap(int(w * ratio), int(h * ratio))
    out.setDevicePixelRatio(ratio)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(clip)

    path = image_file(image_path)
    photo = QPixmap(str(path)) if path else QPixmap()
    if not photo.isNull():
        scaled = photo.scaled(int(w * ratio), int(h * ratio), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                              Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(ratio)
        sw, sh = scaled.width() / ratio, scaled.height() / ratio
        p.drawPixmap(QRectF((w - sw) / 2, (h - sh) / 2, sw, sh), scaled, QRectF(scaled.rect()))
    else:
        bg, fg = tile_colours(category or name)
        p.fillRect(QRectF(0, 0, w, h), QColor(bg))
        f = QFont(FONT_TEXT)
        f.setPixelSize(max(int(min(w, h) * 0.34), 10))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(fg))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, initials(name))
    p.end()
    return out


def clear_image_cache() -> None:
    product_pixmap.cache_clear()


def stylesheet() -> str:
    return f"""
* {{ font-family: "{FONT_TEXT}"; font-size: 14px; color: {TEXT}; }}
QMainWindow, QDialog, QMessageBox {{ background: {BG}; }}
QWidget#content {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px 8px; }}
QLabel {{ background: transparent; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="faint"] {{ color: {FAINT}; font-size: 12px; }}
QLabel[role="title"] {{ font-size: 22px; font-weight: bold; }}
QLabel[role="section"] {{ font-size: 15px; font-weight: bold; }}

/* ---- sidebar ---- */
QFrame#sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel#logo {{ font-size: 20px; font-weight: bold; letter-spacing: 2px; }}
QLabel#logoSub {{ color: {FAINT}; font-size: 11px; letter-spacing: 2px; }}
QPushButton#navBtn {{
    text-align: left; padding: 10px 14px; border: none; border-radius: 10px;
    color: {MUTED}; background: transparent; font-size: 14px;
}}
QPushButton#navBtn:hover {{ background: {SURFACE}; color: {TEXT}; }}
QPushButton#navBtn:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: bold; }}
QFrame#userCard {{ background: {SURFACE}; border-radius: 12px; }}
QLabel#avatar {{
    background: {ACCENT}; color: {ON_ACCENT}; border-radius: 18px; font-weight: bold;
    min-width: 36px; max-width: 36px; min-height: 36px; max-height: 36px;
}}

/* ---- panels & cards ---- */
QFrame#panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#statCard {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px; }}
QLabel#statTitle {{ color: {MUTED}; font-size: 12px; letter-spacing: 1px; }}
QLabel#statValue {{ font-family: "{FONT_MONO}"; font-size: 24px; font-weight: bold; }}
QLabel#statNote {{ color: {FAINT}; font-size: 12px; }}
QFrame#divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

/* ---- inputs ---- */
QLineEdit, QSpinBox, QComboBox, QDateEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
    padding: 7px 10px; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled {{ color: {FAINT}; }}
QLineEdit#scanInput {{ font-size: 16px; padding: 11px 12px; border-radius: 10px; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT}; outline: none;
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 18px; border: none; background: transparent; }}
QCheckBox {{ spacing: 8px; color: {MUTED}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER}; background: {SURFACE_2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

/* ---- buttons ---- */
QPushButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 14px;
}}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton[variant="primary"] {{ background: {ACCENT}; color: {ON_ACCENT}; border: none; font-weight: bold; }}
QPushButton[variant="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: none; color: {MUTED}; }}
QPushButton[variant="ghost"]:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton[variant="danger"] {{ background: transparent; border: 1px solid {DANGER_SOFT}; color: {DANGER}; }}
QPushButton[variant="danger"]:hover {{ background: {DANGER_SOFT}; }}
QPushButton[variant="chip"] {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 15px; padding: 5px 14px; color: {MUTED};
}}
QPushButton[variant="chip"]:hover {{ color: {TEXT}; }}
QPushButton[variant="chip"]:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: {ON_ACCENT}; }}
QPushButton[variant="segment"] {{ background: {SURFACE_2}; border: 1px solid {BORDER}; padding: 9px 6px; color: {MUTED}; }}
QPushButton[variant="segment"]:checked {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; color: {ACCENT}; font-weight: bold; }}
QPushButton#chargeBtn {{ font-size: 17px; padding: 15px; border-radius: 12px; }}
QPushButton#stepBtn {{ padding: 0; min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; border-radius: 13px; }}

/* ---- tables & lists ---- */
QTableWidget, QListWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px;
    gridline-color: transparent; alternate-background-color: #222220; outline: none;
}}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid #262624; }}
QTableWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {FAINT}; border: none; border-bottom: 1px solid {BORDER};
    padding: 9px 8px; font-size: 12px; font-weight: bold; text-transform: uppercase;
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}
QListWidget#productGrid {{ background: transparent; border: none; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---- tabs (inside reports) ---- */
QTabWidget::pane {{ border: none; top: 0; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 9px 16px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: bold; }}

/* ---- scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- calendar popup ---- */
QCalendarWidget QWidget {{ alternate-background-color: {SURFACE_2}; }}
QCalendarWidget QToolButton {{ background: transparent; color: {TEXT}; padding: 4px; }}
QCalendarWidget QAbstractItemView {{
    background: {SURFACE}; selection-background-color: {ACCENT}; selection-color: {ON_ACCENT};
}}
"""


def apply(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")  # consistent base so the stylesheet looks the same on every PC
    pal = QPalette()
    for role, colour in [
        (QPalette.ColorRole.Window, BG), (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, SURFACE_2), (QPalette.ColorRole.AlternateBase, SURFACE),
        (QPalette.ColorRole.Text, TEXT), (QPalette.ColorRole.Button, SURFACE_2),
        (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, ON_ACCENT), (QPalette.ColorRole.ToolTipBase, SURFACE_2),
        (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, FAINT),
        (QPalette.ColorRole.Link, ACCENT),
    ]:
        pal.setColor(role, QColor(colour))
    app.setPalette(pal)
    app.setFont(QFont(FONT_TEXT, 10))
    app.setStyleSheet(stylesheet())
