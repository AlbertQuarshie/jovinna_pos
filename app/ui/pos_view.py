from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import config
from app.db.models import User
from app.services.receipt_service import create_receipt_pdf, last_sale_id
from app.services.sales_service import CartLine, SaleError, complete_sale, find_product


def money(value: Decimal) -> str:
    return f"{config.CURRENCY} {value:,.2f}"


class PosView(QWidget):
    """Sales screen: scan barcodes into the cart, then take payment."""

    COLUMNS = ["Barcode", "Item", "Price", "Qty", "Total"]

    def __init__(self, user: User):
        super().__init__()
        self.user = user
        self.cart: list[CartLine] = []

        # Scanner input — scanners type the code and press Enter
        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("Scan barcode or type code and press Enter…")
        self.scan_input.setObjectName("scanInput")
        self.scan_input.returnPressed.connect(self.on_scan)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        qty_plus = QPushButton("+ Qty")
        qty_minus = QPushButton("− Qty")
        remove_btn = QPushButton("Remove item")
        clear_btn = QPushButton("Clear cart")
        qty_plus.clicked.connect(lambda: self.change_qty(1))
        qty_minus.clicked.connect(lambda: self.change_qty(-1))
        remove_btn.clicked.connect(self.remove_selected)
        clear_btn.clicked.connect(self.clear_cart)

        cart_buttons = QHBoxLayout()
        for b in (qty_plus, qty_minus, remove_btn, clear_btn):
            cart_buttons.addWidget(b)
        cart_buttons.addStretch()

        left = QVBoxLayout()
        left.addWidget(self.scan_input)
        left.addWidget(self.table)
        left.addLayout(cart_buttons)

        # Payment panel
        self.total_label = QLabel(money(Decimal("0")))
        self.total_label.setObjectName("totalLabel")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.discount_input = QLineEdit("0")
        self.discount_input.textChanged.connect(self.refresh_totals)
        self.payment_method = QComboBox()
        self.payment_method.addItems(["cash", "mobile", "card"])
        self.paid_input = QLineEdit()
        self.paid_input.setPlaceholderText("Amount received")
        self.paid_input.textChanged.connect(self.refresh_totals)
        self.paid_input.returnPressed.connect(self.on_checkout)
        self.change_label = QLabel(money(Decimal("0")))

        form = QFormLayout()
        form.addRow("Discount:", self.discount_input)
        form.addRow("Payment:", self.payment_method)
        form.addRow("Paid:", self.paid_input)
        form.addRow("Change:", self.change_label)

        checkout_btn = QPushButton("Complete Sale (F12)")
        checkout_btn.setObjectName("checkoutBtn")
        checkout_btn.setShortcut("F12")
        checkout_btn.clicked.connect(self.on_checkout)

        right = QVBoxLayout()
        right.addWidget(QLabel("TOTAL"))
        right.addWidget(self.total_label)
        right.addLayout(form)
        right.addStretch()
        reprint_btn = QPushButton("Reprint Last Receipt")
        reprint_btn.clicked.connect(self.on_reprint_last)
        right.addWidget(reprint_btn)
        right.addWidget(checkout_btn)

        right_panel = QWidget()
        right_panel.setLayout(right)
        right_panel.setFixedWidth(320)

        root = QHBoxLayout(self)
        root.addLayout(left, 1)
        root.addWidget(right_panel)

        self.scan_input.setFocus()

    # ---- cart actions ----
    def on_scan(self):
        code = self.scan_input.text().strip()
        self.scan_input.clear()
        if not code:
            return

        product = find_product(code)
        if product is None:
            QMessageBox.warning(self, "Not found", f"No product with barcode '{code}'.")
            self.scan_input.setFocus()
            return

        existing = next((l for l in self.cart if l.product_id == product.id), None)
        in_cart = existing.quantity if existing else 0
        if in_cart + 1 > product.stock_qty:
            QMessageBox.warning(self, "Out of stock", f"Only {product.stock_qty} of {product.name} in stock.")
            return

        if existing:
            existing.quantity += 1
        else:
            self.cart.append(CartLine(
                product_id=product.id, barcode=product.barcode, name=product.name,
                unit_price=Decimal(product.selling_price), unit_cost=Decimal(product.cost_price),
                quantity=1, stock_qty=product.stock_qty,
            ))
        self.refresh_table()

    def change_qty(self, delta: int):
        row = self.table.currentRow()
        if row < 0:
            return
        line = self.cart[row]
        new_qty = line.quantity + delta
        if new_qty > line.stock_qty:
            QMessageBox.warning(self, "Out of stock", f"Only {line.stock_qty} of {line.name} in stock.")
            return
        if new_qty <= 0:
            self.cart.pop(row)
        else:
            line.quantity = new_qty
        self.refresh_table(select_row=min(row, len(self.cart) - 1))

    def remove_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.cart.pop(row)
            self.refresh_table()

    def clear_cart(self):
        self.cart.clear()
        self.discount_input.setText("0")
        self.paid_input.clear()
        self.refresh_table()

    # ---- display ----
    def refresh_table(self, select_row: int | None = None):
        self.table.setRowCount(len(self.cart))
        for r, line in enumerate(self.cart):
            values = [line.barcode, line.name, money(line.unit_price), str(line.quantity), money(line.line_total)]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(r, c, item)
        target = select_row if select_row is not None else len(self.cart) - 1
        if target >= 0:
            self.table.selectRow(target)
        self.refresh_totals()
        self.scan_input.setFocus()

    def _decimal(self, text: str) -> Decimal:
        try:
            return Decimal(text.replace(",", "").strip() or "0")
        except InvalidOperation:
            return Decimal("0")

    def total(self) -> Decimal:
        subtotal = sum((l.line_total for l in self.cart), Decimal("0"))
        return max(subtotal - self._decimal(self.discount_input.text()), Decimal("0"))

    def refresh_totals(self):
        total = self.total()
        self.total_label.setText(money(total))
        change = self._decimal(self.paid_input.text()) - total
        self.change_label.setText(money(max(change, Decimal("0"))))

    # ---- checkout ----
    def on_checkout(self):
        if not self.cart:
            QMessageBox.information(self, "Empty cart", "Scan some items first.")
            return
        paid_text = self.paid_input.text().strip()
        paid = self._decimal(paid_text) if paid_text else self.total()  # blank = exact amount
        try:
            sale = complete_sale(
                self.cart, amount_paid=paid, payment_method=self.payment_method.currentText(),
                discount=self._decimal(self.discount_input.text()), user_id=self.user.id,
            )
        except SaleError as e:
            QMessageBox.warning(self, "Cannot complete sale", str(e))
            return

        self.clear_cart()

        box = QMessageBox(self)
        box.setWindowTitle("Sale complete")
        box.setText(f"<h3>Change: {money(sale.change_given)}</h3>")
        box.setInformativeText(f"Receipt #{sale.id:06d} — Total {money(sale.total)}, "
                               f"paid {money(sale.amount_paid)} ({sale.payment_method})")
        print_btn = box.addButton("Print Receipt", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("No Receipt", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(print_btn)
        box.exec()
        if box.clickedButton() is print_btn:
            self.open_receipt(sale.id)

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
