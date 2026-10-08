"""Till-roll style PDF receipts (80 mm wide, height grows with the number of items)."""
from decimal import Decimal
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import config
from app.db.database import SessionLocal
from app.db.models import Sale, SaleItem

RECEIPTS_DIR = config.DATA_DIR / "receipts"
FONTS_DIR = config.BASE_DIR / "assets" / "fonts"

WIDTH = 80 * mm
MARGIN = 4 * mm
LINE = 11  # points between lines

# Space Grotesk for words (shop name, product names, footer), JetBrains Mono for figures so amounts line up.
_FONT_FILES = {
    "SpaceGrotesk": "SpaceGrotesk-Regular.ttf",
    "SpaceGrotesk-Bold": "SpaceGrotesk-Bold.ttf",
    "JetBrainsMono": "JetBrainsMono-Regular.ttf",
    "JetBrainsMono-Bold": "JetBrainsMono-Bold.ttf",
}


def _register_fonts() -> tuple[str, str, str, str]:
    """Register the receipt fonts; fall back to ReportLab's built-ins if any TTF is missing."""
    try:
        for name, filename in _FONT_FILES.items():
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(FONTS_DIR / filename)))
    except (OSError, TTFError):
        return "Helvetica", "Helvetica-Bold", "Courier", "Courier-Bold"
    return "SpaceGrotesk", "SpaceGrotesk-Bold", "JetBrainsMono", "JetBrainsMono-Bold"


TEXT, TEXT_BOLD, MONO, MONO_BOLD = _register_fonts()


def _load_sale(sale_id: int) -> Sale:
    with SessionLocal() as session:
        sale = session.scalar(
            select(Sale).where(Sale.id == sale_id)
            .options(selectinload(Sale.items).selectinload(SaleItem.product), selectinload(Sale.user))
        )
    if sale is None:
        raise ValueError(f"Sale #{sale_id} not found.")
    return sale


def last_sale_id() -> int | None:
    with SessionLocal() as session:
        return session.scalar(select(Sale.id).order_by(Sale.id.desc()).limit(1))


def _money(value) -> str:
    return f"{Decimal(value):,.2f}"


def _centered(text: str, font: str, size: float, inner: float) -> list[tuple]:
    return [("center", part, font, size, 0) for part in simpleSplit(text, font, size, inner)]


def _build_lines(sale: Sale) -> list[tuple]:
    """Receipt as a list of (kind, ...) instructions, so height can be measured before drawing."""
    inner = WIDTH - 2 * MARGIN
    # "Jovinna General Agencies" -> large "JOVINNA" over a letter-spaced "GENERAL AGENCIES".
    first, _, rest = config.SHOP_NAME.partition(" ")
    lines: list[tuple] = [("center", first.upper(), TEXT_BOLD, 18, 1)]
    if rest:
        lines.append(("center", rest.upper(), TEXT, 8.5, 2.5))
    lines.append(("space",))
    for extra in (config.SHOP_TAGLINE, config.SHOP_ADDRESS, config.SHOP_PHONE and f"Tel: {config.SHOP_PHONE}"):
        if extra:
            lines += _centered(extra, TEXT, 8, inner)
    lines += [
        ("rule",),
        ("pair", f"Receipt #{sale.id:06d}", sale.created_at.strftime("%d/%m/%Y %H:%M"), MONO, 8),
    ]
    if sale.user:
        lines.append(("pair", "Served by", sale.user.full_name, MONO, 8))
    lines += [
        ("rule",),
    ]
    for item in sale.items:
        for part in simpleSplit(item.product.name, TEXT_BOLD, 9, inner):
            lines.append(("left", part, TEXT_BOLD, 9))
        lines.append(("pair", f"  {item.quantity} x {_money(item.unit_price)}", _money(item.line_total), MONO, 8.5))
    lines.append(("rule",))
    lines.append(("pair", "Subtotal", _money(sale.subtotal), MONO, 9))
    if sale.discount:
        lines.append(("pair", "Discount", f"-{_money(sale.discount)}", MONO, 9))
    lines += [
        ("pair", f"TOTAL ({config.CURRENCY})", _money(sale.total), MONO_BOLD, 12),
        ("pair", f"Paid ({sale.payment_method.title()})", _money(sale.amount_paid), MONO, 9),
        ("pair", "Change", _money(sale.change_given), MONO, 9),
        ("rule",),
        ("pair", "Items", str(sum(i.quantity for i in sale.items)), MONO, 8),
        ("space",),
    ]
    lines += _centered(config.RECEIPT_FOOTER, TEXT, 8.5, inner)
    return lines


def _advance(line: tuple) -> float:
    """Vertical space a line takes up."""
    kind = line[0]
    if kind == "rule":
        return LINE * 0.8
    if kind == "space":
        return LINE / 2
    size = line[4] if kind == "pair" else line[3]
    return max(LINE, size + 3)


def create_receipt_pdf(sale_id: int, path: Path | None = None) -> Path:
    sale = _load_sale(sale_id)
    if path is None:
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        path = RECEIPTS_DIR / f"receipt_{sale.id:06d}.pdf"

    lines = _build_lines(sale)
    height = 2 * MARGIN + sum(_advance(line) for line in lines)
    c = canvas.Canvas(str(path), pagesize=(WIDTH, height))
    c.setTitle(f"Receipt #{sale.id:06d}")

    y = height - MARGIN  # top of the current line's slot
    for line in lines:
        kind, *args = line
        step = _advance(line)
        baseline = y - step + 3  # leaves room for descenders
        if kind == "center":
            text, font, size, char_space = args
            c.setFont(font, size)
            c.drawCentredString(WIDTH / 2, baseline, text, charSpace=char_space)
        elif kind == "left":
            text, font, size = args
            c.setFont(font, size)
            c.drawString(MARGIN, baseline, text)
        elif kind == "pair":
            left, right, font, size = args
            c.setFont(font, size)
            c.drawString(MARGIN, baseline, left)
            c.drawRightString(WIDTH - MARGIN, baseline, right)
        elif kind == "rule":
            c.setDash(1, 2)
            c.line(MARGIN, y - step / 2, WIDTH - MARGIN, y - step / 2)
            c.setDash()
        y -= step
    c.save()
    return path
