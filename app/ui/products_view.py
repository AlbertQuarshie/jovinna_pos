from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QInputDialog, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import config
from app.db.models import Product
from app.services import product_service as ps
from app.ui.labels_dialog import LabelsDialog


def money(value) -> str:
    return f"{Decimal(value):,.2f}"


class ProductDialog(QDialog):
    """Add or edit a single product."""

    def __init__(self, parent, product: Product | None = None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("Edit Product" if product else "Add Product")
        self.setMinimumWidth(420)

        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Scan the item's barcode, or click Generate")
        gen_btn = QPushButton("Generate")
        gen_btn.setToolTip("Create an in-store barcode for items without one")
        gen_btn.clicked.connect(lambda: self.barcode.setText(ps.generate_internal_barcode()))
        barcode_row = QHBoxLayout()
        barcode_row.addWidget(self.barcode)
        barcode_row.addWidget(gen_btn)

        self.name = QLineEdit()
        self.category = QComboBox()
        self.category.setEditable(True)  # type a new name to create a category
        self.category.addItems([c.name for c in ps.list_categories()])
        self.cost = QLineEdit("0")
        self.price = QLineEdit()
        self.stock = QSpinBox()
        self.stock.setRange(0, 1_000_000)
        self.reorder = QSpinBox()
        self.reorder.setRange(0, 100_000)
        self.reorder.setValue(5)

        form = QFormLayout()
        form.addRow("Barcode:", barcode_row)
        form.addRow("Name:", self.name)
        form.addRow("Category:", self.category)
        form.addRow(f"Cost price ({config.CURRENCY}):", self.cost)
        form.addRow(f"Selling price ({config.CURRENCY}):", self.price)
        form.addRow("Stock qty:", self.stock)
        form.addRow("Low-stock alert at:", self.reorder)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)
        # Scanners press Enter after the code; don't let that submit the form early
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
        gen_btn.setAutoDefault(False)
        self.barcode.returnPressed.connect(self.name.setFocus)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        if product:
            self.barcode.setText(product.barcode)
            self.name.setText(product.name)
            self.category.setCurrentText(product.category.name if product.category else "")
            self.cost.setText(str(product.cost_price))
            self.price.setText(str(product.selling_price))
            self.stock.setValue(product.stock_qty)
            self.reorder.setValue(product.reorder_level)
            self.name.setFocus()
        else:
            self.category.setCurrentText("")
            self.barcode.setFocus()

    def on_save(self):
        try:
            cost = Decimal(self.cost.text().replace(",", "").strip() or "0")
            price = Decimal(self.price.text().replace(",", "").strip())
        except InvalidOperation:
            QMessageBox.warning(self, "Invalid price", "Enter prices as numbers, e.g. 150 or 99.50")
            return
        try:
            ps.save_product(
                self.product.id if self.product else None,
                barcode=self.barcode.text(), name=self.name.text(),
                category_name=self.category.currentText(), cost_price=cost, selling_price=price,
                stock_qty=self.stock.value(), reorder_level=self.reorder.value(),
            )
        except ps.ProductError as e:
            QMessageBox.warning(self, "Cannot save", str(e))
            return
        self.accept()


class ProductsView(QWidget):
    COLUMNS = ["Barcode", "Name", "Category", "Cost", "Price", "Stock", "Status"]

    def __init__(self):
        super().__init__()
        self.products: list[Product] = []

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or scan barcode…")
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("Show hidden")
        self.show_inactive.toggled.connect(self.refresh)

        add_btn = QPushButton("+ Add Product")
        edit_btn = QPushButton("Edit")
        stock_btn = QPushButton("Add Stock")
        labels_btn = QPushButton("Print Labels")
        labels_btn.setToolTip("Select one or more products (Ctrl/Shift + click), then print barcode stickers")
        self.toggle_btn = QPushButton("Hide")
        add_btn.clicked.connect(self.on_add)
        edit_btn.clicked.connect(self.on_edit)
        stock_btn.clicked.connect(self.on_add_stock)
        labels_btn.clicked.connect(self.on_print_labels)
        self.toggle_btn.clicked.connect(self.on_toggle_active)

        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.show_inactive)
        for b in (add_btn, edit_btn, stock_btn, labels_btn, self.toggle_btn):
            top.addWidget(b)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.on_edit)
        self.table.itemSelectionChanged.connect(self.update_toggle_label)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)

        self.refresh()

    def showEvent(self, event):
        # Stock changes after sales on the POS tab, so reload whenever this tab is opened
        super().showEvent(event)
        self.refresh()

    def refresh(self):
        self.products = ps.search_products(self.search.text(), self.show_inactive.isChecked())
        self.table.setRowCount(len(self.products))
        low_stock = QColor("#fdecea")
        for r, p in enumerate(self.products):
            low = p.is_active and p.stock_qty <= p.reorder_level
            status = "Hidden" if not p.is_active else ("LOW STOCK" if low else "OK")
            values = [p.barcode, p.name, p.category.name if p.category else "",
                      money(p.cost_price), money(p.selling_price), str(p.stock_qty), status]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if low:
                    item.setBackground(low_stock)
                if not p.is_active:
                    item.setForeground(QColor("#999999"))
                self.table.setItem(r, c, item)
        self.update_toggle_label()

    def selected(self) -> Product | None:
        row = self.table.currentRow()
        return self.products[row] if 0 <= row < len(self.products) else None

    def selected_products(self) -> list[Product]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.products[r] for r in rows]

    def update_toggle_label(self):
        p = self.selected()
        self.toggle_btn.setText("Unhide" if p and not p.is_active else "Hide")

    def on_add(self):
        if ProductDialog(self).exec():
            self.refresh()

    def on_edit(self):
        p = self.selected()
        if p is None:
            QMessageBox.information(self, "Select a product", "Click a product in the list first.")
            return
        if ProductDialog(self, p).exec():
            self.refresh()

    def on_add_stock(self):
        p = self.selected()
        if p is None:
            QMessageBox.information(self, "Select a product", "Click a product in the list first.")
            return
        qty, ok = QInputDialog.getInt(self, "Add Stock", f"How many '{p.name}' received?\n"
                                      f"(currently {p.stock_qty} in stock)", 1, 1, 1_000_000)
        if ok:
            ps.add_stock(p.id, qty)
            self.refresh()

    def on_print_labels(self):
        products = [p for p in self.selected_products() if p.is_active]
        if not products:
            QMessageBox.information(self, "Select products",
                                    "Select one or more products first (Ctrl/Shift + click for several).")
            return
        LabelsDialog(self, products).exec()

    def on_toggle_active(self):
        p = self.selected()
        if p is None:
            return
        if p.is_active:
            msg = f"Hide '{p.name}'? It won't be sellable, but its sales history is kept."
            if QMessageBox.question(self, "Hide product", msg) != QMessageBox.StandardButton.Yes:
                return
        ps.set_active(p.id, not p.is_active)
        self.refresh()
