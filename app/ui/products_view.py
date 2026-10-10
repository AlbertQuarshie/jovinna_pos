from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app import config
from app.db.models import Product
from app.services import image_service as images
from app.services import product_service as ps
from app.ui import theme
from app.ui.labels_dialog import LabelsDialog


def money(value) -> str:
    return f"{Decimal(value):,.2f}"


class ProductDialog(QDialog):
    """Add or edit a single product."""

    def __init__(self, parent, product: Product | None = None):
        super().__init__(parent)
        self.product = product
        self.setWindowTitle("Edit product" if product else "Add product")
        self.setMinimumWidth(640)
        # Photo: KEEP = unchanged, None = removed, str = newly imported file name
        self.image = ps.KEEP
        self.current_image = product.image_path if product else None

        self.barcode = QLineEdit()
        self.barcode.setPlaceholderText("Scan the item's barcode, or click Generate")
        gen_btn = theme.button("Generate", "magic-wand")
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
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)
        # Scanners press Enter after the code; don't let that submit the form early
        for btn in buttons.buttons():
            btn.setAutoDefault(False)
        gen_btn.setAutoDefault(False)
        self.barcode.returnPressed.connect(self.name.setFocus)

        # Photo column
        self.preview = QLabel()
        self.preview.setFixedSize(180, 180)
        choose_btn = theme.button("Choose photo", "image")
        choose_btn.clicked.connect(self.on_choose_photo)
        self.remove_photo_btn = theme.button("Remove photo", "trash", "ghost")
        self.remove_photo_btn.clicked.connect(self.on_remove_photo)
        for b in (choose_btn, self.remove_photo_btn):
            b.setAutoDefault(False)
        photo_col = QVBoxLayout()
        photo_col.addWidget(self.preview)
        photo_col.addWidget(choose_btn)
        photo_col.addWidget(self.remove_photo_btn)
        photo_col.addStretch()

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addLayout(photo_col)
        body.addLayout(form, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addLayout(body)
        layout.addWidget(buttons)
        self.name.textChanged.connect(self.update_preview)
        self.category.currentTextChanged.connect(self.update_preview)

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
        self.update_preview()

    def shown_image(self) -> str | None:
        return self.current_image if self.image is ps.KEEP else self.image

    def update_preview(self):
        name = self.name.text().strip() or "New product"
        self.preview.setPixmap(theme.product_pixmap(self.shown_image(), name, self.category.currentText(), 180, 180, 12))
        self.remove_photo_btn.setVisible(self.shown_image() is not None)

    def _discard_new_image(self):
        if isinstance(self.image, str):
            images.delete_image(self.image)

    def on_choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose a product photo", "", images.SUPPORTED)
        if not path:
            return
        try:
            new = images.import_image(path)
        except images.ImageError as e:
            QMessageBox.warning(self, "Can't use that photo", str(e))
            return
        self._discard_new_image()
        self.image = new
        self.update_preview()

    def on_remove_photo(self):
        self._discard_new_image()
        self.image = None
        self.update_preview()

    def reject(self):
        self._discard_new_image()  # cancelled: don't keep a photo nobody saved
        super().reject()

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
                stock_qty=self.stock.value(), reorder_level=self.reorder.value(), image=self.image,
            )
        except ps.ProductError as e:
            QMessageBox.warning(self, "Cannot save", str(e))
            return
        self.accept()


class ProductsView(QWidget):
    COLUMNS = ["", "Name", "Barcode", "Category", "Cost", "Price", "Stock", "Status"]

    def __init__(self):
        super().__init__()
        self.products: list[Product] = []

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by name or scan barcode…")
        self.search.addAction(theme.icon("magnifying-glass"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.show_inactive = QCheckBox("Show hidden")
        self.show_inactive.toggled.connect(self.refresh)

        add_btn = theme.button("Add product", "plus", "primary")
        edit_btn = theme.button("Edit", "pencil-simple")
        stock_btn = theme.button("Add stock", "stack")
        labels_btn = theme.button("Print labels", "barcode")
        labels_btn.setToolTip("Select one or more products (Ctrl/Shift + click), then print barcode stickers")
        self.toggle_btn = theme.button("Hide", "eye-slash")
        add_btn.clicked.connect(self.on_add)
        edit_btn.clicked.connect(self.on_edit)
        stock_btn.clicked.connect(self.on_add_stock)
        labels_btn.clicked.connect(self.on_print_labels)
        self.toggle_btn.clicked.connect(self.on_toggle_active)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.search, 1)
        top.addWidget(self.show_inactive)
        for b in (edit_btn, stock_btn, labels_btn, self.toggle_btn, add_btn):
            top.addWidget(b)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(56)
        self.table.setIconSize(QSize(42, 42))
        self.table.setColumnWidth(0, 60)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self.on_edit)
        self.table.itemSelectionChanged.connect(self.update_toggle_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
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
        theme.clear_image_cache()
        for r, p in enumerate(self.products):
            low = p.is_active and p.stock_qty <= p.reorder_level
            status = "Hidden" if not p.is_active else ("LOW STOCK" if low else "OK")
            category = p.category.name if p.category else ""
            values = ["", p.name, p.barcode, category,
                      money(p.cost_price), money(p.selling_price), str(p.stock_qty), status]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (4, 5, 6):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    item.setFont(theme.mono(13))
                if c == 7:
                    item.setForeground(QColor(theme.FAINT if not p.is_active else theme.DANGER if low else theme.SUCCESS))
                elif not p.is_active:
                    item.setForeground(QColor(theme.FAINT))
                elif low and c == 6:
                    item.setForeground(QColor(theme.DANGER))
                self.table.setItem(r, c, item)
            self.table.item(r, 0).setIcon(QIcon(theme.product_pixmap(p.image_path, p.name, category, 42, 42, 8)))
        self.update_toggle_label()

    def selected(self) -> Product | None:
        row = self.table.currentRow()
        return self.products[row] if 0 <= row < len(self.products) else None

    def selected_products(self) -> list[Product]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.products[r] for r in rows]

    def update_toggle_label(self):
        p = self.selected()
        hidden = bool(p and not p.is_active)
        self.toggle_btn.setText("Unhide" if hidden else "Hide")
        self.toggle_btn.setIcon(theme.icon("eye" if hidden else "eye-slash", theme.TEXT))

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
        qty, ok = QInputDialog.getInt(self, "Add stock", f"How many '{p.name}' received?\n"
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
