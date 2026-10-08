"""Barcode label PDFs: A4 sticker sheets or single labels for a thermal label printer."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app import config
from app.services.product_service import ean13_check_digit

LABELS_DIR = config.DATA_DIR / "labels"


@dataclass(frozen=True)
class LabelLayout:
    name: str
    page_size: tuple[float, float]
    cols: int
    rows: int
    label_w: float
    label_h: float
    margin_left: float = 0
    margin_top: float = 0
    gap_x: float = 0
    gap_y: float = 0

    @property
    def per_page(self) -> int:
        return self.cols * self.rows


LAYOUTS = {
    # Common A4 sticker sheet: 3 x 8 labels, 70 x 37 mm, no gaps
    "a4_24": LabelLayout("A4 sheet — 24 labels (70×37 mm)", A4, 3, 8, 70 * mm, 37 * mm,
                         margin_top=(297 - 8 * 37) / 2 * mm),
    # A4 sheet: 4 x 10 labels, 48.5 x 25.4 mm
    "a4_40": LabelLayout("A4 sheet — 40 labels (48.5×25.4 mm)", A4, 4, 10, 48.5 * mm, 25.4 * mm,
                         margin_left=8 * mm, margin_top=21.5 * mm),
    # Thermal label printer roll: one label per page
    "roll_50x25": LabelLayout("Label printer roll (50×25 mm)", (50 * mm, 25 * mm), 1, 1, 50 * mm, 25 * mm),
}


@dataclass
class LabelItem:
    barcode: str
    name: str
    price: Decimal
    copies: int


def _is_valid_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13_check_digit(code[:12]) == code[-1]


def _draw_barcode(c: canvas.Canvas, code: str, x: float, y: float, max_w: float, max_h: float):
    """Draw a barcode centred inside the box (x, y, max_w, max_h), scaled to fit."""
    if _is_valid_ean13(code):
        d = createBarcodeDrawing("EAN13", value=code[:12], barHeight=max_h * 0.75, humanReadable=True)
    else:
        d = createBarcodeDrawing("Code128", value=code, barHeight=max_h * 0.75, barWidth=0.9,
                                 humanReadable=True, quiet=False)
    # Real extents, including the human-readable digits that sit outside the nominal size
    x0, y0, x1, y1 = d.getBounds()
    w, h = x1 - x0, y1 - y0
    scale = min(max_w / w, max_h / h, 1.6)
    c.saveState()
    c.translate(x + (max_w - w * scale) / 2, y + (max_h - h * scale) / 2)
    c.scale(scale, scale)
    renderPDF.draw(d, c, -x0, -y0)
    c.restoreState()


def _fit_text(text: str, font: str, size: float, max_w: float) -> str:
    if stringWidth(text, font, size) <= max_w:
        return text
    while text and stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def _draw_label(c: canvas.Canvas, x: float, y: float, w: float, h: float, item: LabelItem):
    pad = 2 * mm
    inner_w = w - 2 * pad
    small = h < 30 * mm
    name_size, price_size, shop_size = (7, 9, 5) if small else (8, 11, 6)

    top = y + h - pad
    c.setFont("Helvetica", shop_size)
    c.drawCentredString(x + w / 2, top - shop_size, _fit_text(config.SHOP_NAME, "Helvetica", shop_size, inner_w))
    top -= shop_size + 1.5
    c.setFont("Helvetica-Bold", name_size)
    c.drawCentredString(x + w / 2, top - name_size, _fit_text(item.name, "Helvetica-Bold", name_size, inner_w))
    top -= name_size + 1.5

    bottom = y + pad
    price = f"{config.CURRENCY} {item.price:,.2f}"
    c.setFont("Helvetica-Bold", price_size)
    c.drawCentredString(x + w / 2, bottom, price)
    bottom += price_size + 1.5

    _draw_barcode(c, item.barcode, x + pad, bottom, inner_w, top - bottom - 1)


def create_labels_pdf(items: list[LabelItem], layout_key: str = "a4_24", skip: int = 0,
                      path: Path | None = None) -> Path:
    """Write labels to a PDF and return its path.

    `skip` leaves the first N spaces empty, so a partly used sticker sheet can be reused.
    """
    layout = LAYOUTS[layout_key]
    if path is None:
        LABELS_DIR.mkdir(parents=True, exist_ok=True)
        path = LABELS_DIR / f"labels_{datetime.now():%Y%m%d_%H%M%S}.pdf"

    queue = [item for item in items for _ in range(item.copies)]
    if not queue:
        raise ValueError("No labels to print.")

    c = canvas.Canvas(str(path), pagesize=layout.page_size)
    c.setTitle(f"{config.SHOP_NAME} barcode labels")
    page_h = layout.page_size[1]
    slot = skip % layout.per_page if layout.per_page > 1 else 0
    for i, item in enumerate(queue):
        if slot == layout.per_page:
            c.showPage()
            slot = 0
        row, col = divmod(slot, layout.cols)
        x = layout.margin_left + col * (layout.label_w + layout.gap_x)
        y = page_h - layout.margin_top - (row + 1) * layout.label_h - row * layout.gap_y
        _draw_label(c, x, y, layout.label_w, layout.label_h, item)
        slot += 1
    c.save()
    return path
