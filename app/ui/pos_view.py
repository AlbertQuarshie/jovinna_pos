from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
    QListWidget, QListWidgetItem, QMessageBox, QScrollArea, QStyle, QStyledItemDelegate, QVBoxLayout,
    QWidget,
)

from app import config
from app.db.models import Product, User
from app.services import product_service as ps
from app.services.receipt_service import create_receipt_pdf, last_sale_id
from app.services.sales_service import CartLine, SaleError, complete_sale, find_product
from app.ui import theme

PAYMENT_METHODS = [("cash", "Cash", "money"), ("mobile", "Mobile money", "device-mobile")]
TILE_W, TILE_H, IMG_H = 164, 214, 120


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


class ProductTileDelegate(QStyledItemDelegate):
    """Draws a product as a card: photo, name, price and stock."""

    def sizeHint(self, option, index):
        grid = self.parent().gridSize() if self.parent() else QSize()
        return grid if grid.isValid() else QSize(TILE_W, TILE_H)

    def paint(self, painter: QPainter, option, index):
        p: Product = index.data(Qt.ItemDataRole.UserRole)
        r = QRectF(option.rect).adjusted(5, 5, -5, -5)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        out = p.stock_qty <= 0

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if out:
            painter.setOpacity(0.45)
        painter.setPen(QPen(QColor(theme.ACCENT if hover and not out else theme.BORDER), 1.2))
        painter.setBrush(QColor(theme.SURFACE_2 if hover else theme.SURFACE))
        painter.drawRoundedRect(r, 12, 12)

        img = QRectF(r.left() + 8, r.top() + 8, r.width() - 16, IMG_H)
        painter.drawPixmap(img.topLeft(), theme.product_pixmap(
            p.image_path, p.name, p.main_category, int(img.width()), int(img.height())))

        name_font = QFont(theme.FONT_TEXT)
        name_font.setPixelSize(13)
        painter.setFont(name_font)
        painter.setPen(QColor(theme.TEXT))
        fm = QFontMetrics(name_font)
        text_rect = QRectF(r.left() + 10, img.bottom() + 8, r.width() - 20, fm.height() * 2 + 2)
        name = p.name if fm.horizontalAdvance(p.name) <= text_rect.width() * 1.9 else \
            fm.elidedText(p.name, Qt.TextElideMode.ElideRight, int(text_rect.width() * 1.85))
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, name)

        bottom = QRectF(r.left() + 10, r.bottom() - 28, r.width() - 20, 20)
        painter.setFont(theme.mono(14, bold=True))
        painter.setPen(QColor(theme.ACCENT))
        painter.drawText(bottom, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, money(p.selling_price))

        small = QFont(theme.FONT_TEXT)
        small.setPixelSize(11)
        painter.setFont(small)
        if out:
            colour, stock = theme.DANGER, "Out of stock"
        else:
            colour = theme.ACCENT if p.stock_qty <= p.reorder_level else theme.FAINT
            stock = f"{p.stock_qty} left"
        painter.setPen(QColor(colour))
        painter.drawText(bottom, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, stock)
        painter.restore()


class ProductGrid(QListWidget):
    """Icon grid whose tiles stretch so each row fills the available width."""

    MIN_TILE_W = 156

    def __init__(self):
        super().__init__()
        # Always reserve the scrollbar's space: if it came and went as results change, every tile
        # would resize and the grid would jump.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.empty_label = QLabel("No products match your search.", self.viewport())
        self.empty_label.setProperty("role", "muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width() - 12  # Qt's icon layout needs a little slack to fit the last column
        columns = max(1, width // self.MIN_TILE_W)
        size = QSize(width // columns, TILE_H)
        if size != self.gridSize():
            self.setGridSize(size)
        self.empty_label.setGeometry(0, 40, self.viewport().width(), 40)


class CartRow(QFrame):
    """One line in the cart: thumbnail, name, quantity stepper, line total, remove."""

    def __init__(self, line: CartLine, image_path: str | None, category: str, on_qty, on_remove):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(4, 6, 4, 6)
        row.setSpacing(10)

        thumb = QLabel()
        thumb.setPixmap(theme.product_pixmap(image_path, line.name, category, 40, 40, 8))
        row.addWidget(thumb)

        text = QVBoxLayout()
        text.setSpacing(1)
        name = QLabel(line.name)
        name.setStyleSheet("font-weight: bold; font-size: 13px;")
        name.setMaximumWidth(150)
        name.setToolTip(line.name)
        fm = QFontMetrics(name.font())
        name.setText(fm.elidedText(line.name, Qt.TextElideMode.ElideRight, 150))
        each = QLabel(f"{money(line.unit_price)} each")
        each.setProperty("role", "faint")
        text.addWidget(name)
        text.addWidget(each)
        row.addLayout(text, 1)

        minus = theme.button("", "minus", tooltip="One less")
        plus = theme.button("", "plus", tooltip="One more")
        for b in (minus, plus):
            b.setObjectName("stepBtn")
            b.setIconSize(QSize(12, 12))
        minus.clicked.connect(lambda: on_qty(line, -1))
        plus.clicked.connect(lambda: on_qty(line, 1))
        qty = QLabel(str(line.quantity))
        qty.setFont(theme.mono(14, bold=True))
        qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qty.setMinimumWidth(24)
        row.addWidget(minus)
        row.addWidget(qty)
        row.addWidget(plus)

        total = QLabel(money(line.line_total))
        total.setFont(theme.mono(13, bold=True))
        total.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        total.setMinimumWidth(78)
        row.addWidget(total)

        remove = theme.button("", "x", "ghost", "Remove")
        remove.setIconSize(QSize(14, 14))
        remove.setFixedWidth(28)
        remove.clicked.connect(lambda: on_remove(line))
        row.addWidget(remove)


class PosView(QWidget):
    """Sales screen: scan or tap products into the cart, then take payment."""

    def __init__(self, user: User):
        super().__init__()
        self.user = user
        self.cart: list[CartLine] = []
        self.products: list[Product] = []
        self.main = None   # None = all categories, or e.g. "Accessories"
        self.sub = None    # None = all of the main category, "" = items with no subcategory, or a name

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)
        root.addLayout(self._build_catalogue(), 1)
        root.addWidget(self._build_cart_panel())

        QShortcut(QKeySequence("Escape"), self, activated=lambda: self.scan_input.clear())
        self.load_products()
        self.refresh_cart()

    # ---- left: search, categories, product grid ----
    def _build_catalogue(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(12)

        self.scan_input = QLineEdit()
        self.scan_input.setObjectName("scanInput")
        self.scan_input.setPlaceholderText("Scan a barcode, or type to search products…")
        self.scan_input.addAction(theme.icon("barcode", theme.ACCENT), QLineEdit.ActionPosition.LeadingPosition)
        self.scan_input.setClearButtonEnabled(True)
        self.scan_input.returnPressed.connect(self.on_scan)
        self.scan_input.textChanged.connect(self.filter_grid)

        # Main category first, then its subcategories underneath
        self.main_box = QComboBox()
        self.main_box.setObjectName("mainCategory")
        self.main_box.setMinimumWidth(190)
        self.main_box.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keep the scanner's focus on the search box
        self.main_box.currentIndexChanged.connect(self.on_main_changed)
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        search_row.addWidget(self.main_box)
        search_row.addWidget(self.scan_input, 1)
        col.addLayout(search_row)

        self.chips_row = QHBoxLayout()
        self.chips_row.setSpacing(8)
        self.chips = QButtonGroup(self)
        self.chips.setExclusive(True)
        self.chips.buttonClicked.connect(self.on_sub_clicked)
        self.chips_hint = QLabel("Choose a category to see its subcategories")
        self.chips_hint.setProperty("role", "faint")
        self.results_label = QLabel()
        self.results_label.setProperty("role", "faint")
        col.addLayout(self.chips_row)

        self.grid = ProductGrid()
        self.grid.setObjectName("productGrid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.grid.setMouseTracking(True)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.grid.setItemDelegate(ProductTileDelegate(self.grid))
        self.grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.grid.itemClicked.connect(lambda item: self.add_to_cart(item.data(Qt.ItemDataRole.UserRole)))
        col.addWidget(self.grid, 1)
        return col

    def _rebuild_main_box(self):
        mains = ps.main_categories()
        entries = [("All categories", None)] + [(m, m) for m in mains]
        if entries == [(self.main_box.itemText(i), self.main_box.itemData(i)) for i in range(self.main_box.count())]:
            return
        self.main_box.blockSignals(True)
        self.main_box.clear()
        for label, data in entries:
            self.main_box.addItem(label, data)
        if self.main not in mains:
            self.main, self.sub = None, None
        self.main_box.setCurrentIndex(max(self.main_box.findData(self.main), 0))
        self.main_box.blockSignals(False)

    def _sub_options(self) -> list[tuple[str, str | None]]:
        """(button label, subcategory) for the chosen main category, from the products in it."""
        if self.main is None:
            return []
        in_main = [p for p in self.products if p.main_category == self.main]
        subs = sorted({p.sub_category for p in in_main if p.sub_category}, key=str.lower)
        options = [("All", None)] + [(s, s) for s in subs]
        if any(not p.sub_category for p in in_main):
            options.append(("Other items", ""))  # products saved without a subcategory
        return options

    def _rebuild_chips(self):
        options = self._sub_options()
        if [b.property("sub") for b in self.chips.buttons()] == [o[1] for o in options]                 and [b.text() for b in self.chips.buttons()] == [o[0] for o in options] and options:
            return  # same subcategories: keep the existing buttons (avoids flicker)
        for b in self.chips.buttons():
            self.chips.removeButton(b)
            b.setParent(None)
            b.deleteLater()
        while self.chips_row.count():
            self.chips_row.takeAt(0)
        if self.sub not in [o[1] for o in options]:
            self.sub = None
        if not options:
            self.chips_hint.show()
            self.chips_row.addWidget(self.chips_hint)
        else:
            self.chips_hint.hide()
        for label, sub in options:
            chip = theme.button(label, variant="chip")
            chip.setCheckable(True)
            chip.setProperty("sub", sub)
            chip.setChecked(sub == self.sub)
            chip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.chips.addButton(chip)
            self.chips_row.addWidget(chip)
        self.chips_row.addStretch()
        self.chips_row.addWidget(self.results_label)

    # ---- right: cart and payment ----
    def _build_cart_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(420)
        col = QVBoxLayout(panel)
        col.setContentsMargins(18, 16, 18, 18)
        col.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("Current sale")
        title.setProperty("role", "section")
        self.count_label = QLabel()
        self.count_label.setProperty("role", "muted")
        clear_btn = theme.button("Clear", "trash", "ghost", "Remove everything from the cart")
        clear_btn.clicked.connect(self.clear_cart)
        head.addWidget(title)
        head.addWidget(self.count_label)
        head.addStretch()
        head.addWidget(clear_btn)
        col.addLayout(head)

        self.cart_area = QScrollArea()
        self.cart_area.setWidgetResizable(True)
        self.cart_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cart_box = QWidget()
        self.cart_list = QVBoxLayout(self.cart_box)
        self.cart_list.setContentsMargins(0, 0, 0, 0)
        self.cart_list.setSpacing(0)
        self.cart_area.setWidget(self.cart_box)
        col.addWidget(self.cart_area, 1)

        col.addWidget(self._divider())

        totals = QGridLayout()
        totals.setVerticalSpacing(6)
        self.subtotal_label = self._amount_label()
        self.discount_input = QLineEdit("0")
        self.discount_input.setFont(theme.mono(13))
        self.discount_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.discount_input.setFixedWidth(110)
        self.discount_input.textChanged.connect(self.refresh_totals)
        totals.addWidget(self._muted("Subtotal"), 0, 0)
        totals.addWidget(self.subtotal_label, 0, 1, Qt.AlignmentFlag.AlignRight)
        totals.addWidget(self._muted("Discount"), 1, 0)
        totals.addWidget(self.discount_input, 1, 1, Qt.AlignmentFlag.AlignRight)
        col.addLayout(totals)

        total_row = QHBoxLayout()
        total_caption = QLabel("Total")
        total_caption.setProperty("role", "section")
        self.total_label = QLabel()
        self.total_label.setFont(theme.mono(28, bold=True))
        self.total_label.setStyleSheet(f"color: {theme.ACCENT};")
        total_row.addWidget(total_caption)
        total_row.addStretch()
        total_row.addWidget(self.total_label)
        col.addLayout(total_row)

        col.addWidget(self._divider())

        methods = QHBoxLayout()
        methods.setSpacing(8)
        self.method_group = QButtonGroup(self)
        for value, label, icon_name in PAYMENT_METHODS:
            b = theme.button(f" {label}", variant="segment")
            b.setIcon(theme.icon(icon_name, theme.MUTED, active_color=theme.ACCENT))
            b.setCheckable(True)
            b.setProperty("method", value)
            b.setChecked(value == "cash")
            self.method_group.addButton(b)
            methods.addWidget(b)
        self.method_group.buttonClicked.connect(self.on_method_changed)
        col.addLayout(methods)

        paid_row = QHBoxLayout()
        self.paid_input = QLineEdit()
        self.paid_input.setFont(theme.mono(15))
        self.paid_input.setPlaceholderText("Paid")
        self.paid_input.setToolTip("Amount received from the customer")
        self.paid_input.textChanged.connect(self.refresh_totals)
        self.paid_input.returnPressed.connect(self.on_checkout)
        paid_row.addWidget(self.paid_input, 1)
        self.quick_cash = []
        for label, amount in [("Exact", None), ("500", 500), ("1,000", 1000), ("2,000", 2000)]:
            b = theme.button(label, variant="chip")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, a=amount: self.set_paid(a))
            self.quick_cash.append(b)
            paid_row.addWidget(b)
        col.addLayout(paid_row)

        change_row = QHBoxLayout()
        change_row.addWidget(self._muted("Change"))
        change_row.addStretch()
        self.change_label = QLabel()
        self.change_label.setFont(theme.mono(18, bold=True))
        self.change_label.setStyleSheet(f"color: {theme.SUCCESS};")
        change_row.addWidget(self.change_label)
        col.addLayout(change_row)

        self.charge_btn = theme.button("", "check", "primary")
        self.charge_btn.setObjectName("chargeBtn")
        self.charge_btn.setIconSize(QSize(20, 20))
        self.charge_btn.setShortcut("F12")
        self.charge_btn.clicked.connect(self.on_checkout)
        col.addWidget(self.charge_btn)

        reprint = theme.button("Reprint last receipt", "receipt", "ghost")
        reprint.clicked.connect(self.on_reprint_last)
        col.addWidget(reprint)
        return panel

    @staticmethod
    def _divider() -> QFrame:
        d = QFrame()
        d.setObjectName("divider")
        return d

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        return label

    @staticmethod
    def _amount_label() -> QLabel:
        label = QLabel()
        label.setFont(theme.mono(14))
        return label

    # ---- catalogue ----
    def showEvent(self, event):
        super().showEvent(event)
        self.load_products()  # prices, photos or stock may have changed on the Products page
        self.scan_input.setFocus()

    def load_products(self):
        products = ps.search_products("")
        # Only rebuild the tiles when something visible changed (price, stock, photo, name…)
        signature = [(p.id, p.name, p.barcode, str(p.selling_price), p.stock_qty, p.reorder_level, p.image_path,
                      p.category_label) for p in products]
        if signature == getattr(self, "_signature", None):
            return
        self._signature = signature
        self.products = products
        self._rebuild_main_box()
        self._rebuild_chips()

        self.grid.setUpdatesEnabled(False)
        self.grid.clear()
        for p in products:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(f"{p.name}\nBarcode: {p.barcode}")
            self.grid.addItem(item)
        self.grid.setUpdatesEnabled(True)
        self.filter_grid()

    def on_main_changed(self, _index=None):
        self.main = self.main_box.currentData()
        self.sub = None
        self._rebuild_chips()
        self.filter_grid()
        self.scan_input.setFocus()

    def on_sub_clicked(self, button):
        self.sub = button.property("sub")
        self.filter_grid()
        self.scan_input.setFocus()

    def _matches(self, p: Product, words: list[str]) -> bool:
        # Typing searches every product; the category filters only apply when the box is empty
        if not words:
            if self.main is not None and p.main_category != self.main:
                return False
            if self.sub is not None and p.sub_category != self.sub:
                return False
        haystack = f"{p.name} {p.main_category} {p.sub_category}".lower()
        # every typed word must appear somewhere ("blue pen" finds "Blue Ballpoint Pen"),
        # or the text is the start of a barcode
        return all(w in haystack for w in words) or (len(words) == 1 and p.barcode.startswith(words[0]))

    def visible_products(self) -> list[Product]:
        words = self.scan_input.text().lower().split()
        return [p for p in self.products if self._matches(p, words)]

    def filter_grid(self):
        """Show or hide existing tiles — no rebuilding, so typing and category clicks don't flicker."""
        words = self.scan_input.text().lower().split()
        shown = 0
        self.grid.setUpdatesEnabled(False)
        for row in range(self.grid.count()):
            visible = self._matches(self.grid.item(row).data(Qt.ItemDataRole.UserRole), words)
            self.grid.setRowHidden(row, not visible)
            shown += visible
        self.grid.setUpdatesEnabled(True)
        self.grid.scrollToTop()
        self.grid.empty_label.setVisible(shown == 0)
        total = len(self.products)
        query = self.scan_input.text().strip()
        if query:
            self.results_label.setText(f"{shown} result{'s' if shown != 1 else ''} for “{query}” in all products")
        else:
            self.results_label.setText(f"{total} products" if shown == total else f"{shown} of {total} products")

    # ---- cart actions ----
    def on_scan(self):
        code = self.scan_input.text().strip()
        if not code:
            return
        product = find_product(code)
        if product is None:
            matches = self.visible_products()
            if len(matches) == 1:
                product = matches[0]
            elif matches:
                return  # several matches: the grid is already filtered, tap one
            else:
                QMessageBox.warning(self, "Not found", f"No product matches '{code}'.")
                self.scan_input.selectAll()
                return
        self.scan_input.clear()
        self.add_to_cart(product)

    def add_to_cart(self, product: Product):
        existing = next((l for l in self.cart if l.product_id == product.id), None)
        in_cart = existing.quantity if existing else 0
        if in_cart + 1 > product.stock_qty:
            QMessageBox.warning(self, "Out of stock", f"Only {product.stock_qty} of {product.name} in stock.")
            self.scan_input.setFocus()
            return
        if existing:
            existing.quantity += 1
        else:
            self.cart.append(CartLine(
                product_id=product.id, barcode=product.barcode, name=product.name,
                unit_price=Decimal(product.selling_price), unit_cost=Decimal(product.cost_price),
                quantity=1, stock_qty=product.stock_qty,
            ))
        self.refresh_cart()

    def change_qty(self, line: CartLine, delta: int):
        new_qty = line.quantity + delta
        if new_qty > line.stock_qty:
            QMessageBox.warning(self, "Out of stock", f"Only {line.stock_qty} of {line.name} in stock.")
            return
        if new_qty <= 0:
            self.cart.remove(line)
        else:
            line.quantity = new_qty
        self.refresh_cart()

    def remove_line(self, line: CartLine):
        self.cart.remove(line)
        self.refresh_cart()

    def clear_cart(self):
        self.cart.clear()
        self.discount_input.setText("0")
        self.paid_input.clear()
        self.refresh_cart()

    # ---- display ----
    def refresh_cart(self):
        while self.cart_list.count():
            widget = self.cart_list.takeAt(0).widget()
            if widget:
                widget.setParent(None)  # remove from view now; deleteLater only frees it later
                widget.deleteLater()

        by_id = {p.id: p for p in self.products}
        if not self.cart:
            empty = QLabel("No items yet.\nScan a barcode or tap a product.")
            empty.setProperty("role", "muted")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(160)
            self.cart_list.addWidget(empty)
        for line in self.cart:
            p = by_id.get(line.product_id)
            self.cart_list.addWidget(CartRow(
                line, p.image_path if p else None, p.main_category if p else "",
                self.change_qty, self.remove_line,
            ))
        self.cart_list.addStretch()

        items = sum(l.quantity for l in self.cart)
        self.count_label.setText(f"·  {items} item{'s' if items != 1 else ''}" if items else "")
        self.refresh_totals()
        self.scan_input.setFocus()

    def _decimal(self, text: str) -> Decimal:
        try:
            return Decimal(text.replace(",", "").strip() or "0")
        except InvalidOperation:
            return Decimal("0")

    def subtotal(self) -> Decimal:
        return sum((l.line_total for l in self.cart), Decimal("0"))

    def total(self) -> Decimal:
        return max(self.subtotal() - self._decimal(self.discount_input.text()), Decimal("0"))

    def payment_method(self) -> str:
        return self.method_group.checkedButton().property("method")

    def refresh_totals(self):
        total = self.total()
        self.subtotal_label.setText(money(self.subtotal()))
        self.total_label.setText(money(total))
        if self.payment_method() != "cash":
            self.change_label.setText(money(Decimal("0")))
        else:
            change = self._decimal(self.paid_input.text()) - total if self.paid_input.text().strip() else Decimal("0")
            self.change_label.setText(money(max(change, Decimal("0"))))
        self.charge_btn.setText(f"  Charge  {config.CURRENCY} {money(total)}   (F12)")

    def on_method_changed(self, _button=None):
        cash = self.payment_method() == "cash"
        self.paid_input.setEnabled(cash)
        self.paid_input.setPlaceholderText("Paid" if cash else "Paid in full by " + self.payment_method())
        if not cash:
            self.paid_input.clear()
        for b in self.quick_cash:
            b.setVisible(cash)
        self.refresh_totals()
        self.scan_input.setFocus()

    def set_paid(self, amount: int | None):
        self.paid_input.setText(str(self.total() if amount is None else amount))
        self.paid_input.setFocus()

    # ---- checkout ----
    def on_checkout(self):
        if not self.cart:
            QMessageBox.information(self, "Empty cart", "Scan or tap some products first.")
            return
        paid_text = self.paid_input.text().strip()
        cash = self.payment_method() == "cash"
        paid = self._decimal(paid_text) if (cash and paid_text) else self.total()  # blank = exact amount
        try:
            sale = complete_sale(
                self.cart, amount_paid=paid, payment_method=self.payment_method(),
                discount=self._decimal(self.discount_input.text()), user_id=self.user.id,
            )
        except SaleError as e:
            QMessageBox.warning(self, "Can't complete sale", str(e))
            return

        self.clear_cart()
        self.load_products()  # stock levels changed

        box = QMessageBox(self)
        box.setWindowTitle("Sale complete")
        box.setIconPixmap(theme.icon("check-circle", theme.SUCCESS).pixmap(48, 48))
        box.setText(f"<span style='font-size:13px;color:{theme.MUTED}'>Change to give</span><br>"
                    f"<span style='font-family:\"{theme.FONT_MONO}\";font-size:30px;font-weight:bold;"
                    f"color:{theme.SUCCESS}'>{config.CURRENCY} {money(sale.change_given)}</span>")
        box.setInformativeText(f"Receipt #{sale.id:06d}  ·  Total {money(sale.total)}  ·  "
                               f"Paid {money(sale.amount_paid)} ({sale.payment_method})")
        print_btn = box.addButton("  Print receipt", QMessageBox.ButtonRole.AcceptRole)
        print_btn.setProperty("variant", "primary")
        print_btn.setIcon(theme.icon("printer", theme.ON_ACCENT))
        box.addButton("No receipt", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(print_btn)
        box.exec()
        if box.clickedButton() is print_btn:
            self.open_receipt(sale.id)
        self.scan_input.setFocus()

    def open_receipt(self, sale_id: int):
        try:
            path = create_receipt_pdf(sale_id)
        except Exception as e:
            QMessageBox.warning(self, "Receipt error", str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.scan_input.setFocus()

    def on_reprint_last(self):
        sale_id = last_sale_id()
        if sale_id is None:
            QMessageBox.information(self, "No sales yet", "There are no sales to reprint.")
            return
        self.open_receipt(sale_id)
