from decimal import Decimal

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QMessageBox,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.db.models import Product
from app.services.label_service import LAYOUTS, LabelItem, create_labels_pdf


class LabelsDialog(QDialog):
    """Choose how many labels per product and the sheet type, then open the PDF to print."""

    def __init__(self, parent, products: list[Product]):
        super().__init__(parent)
        self.products = products
        self.setWindowTitle("Print Barcode Labels")
        self.setMinimumSize(560, 380)

        self.table = QTableWidget(len(products), 3)
        self.table.setHorizontalHeaderLabels(["Product", "Barcode", "Labels"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.copies: list[QSpinBox] = []
        for r, p in enumerate(products):
            self.table.setItem(r, 0, QTableWidgetItem(p.name))
            self.table.setItem(r, 1, QTableWidgetItem(p.barcode))
            spin = QSpinBox()
            spin.setRange(0, 1000)
            spin.setValue(max(p.stock_qty, 1))  # default: one label per item in stock
            self.copies.append(spin)
            self.table.setCellWidget(r, 2, spin)

        self.layout_box = QComboBox()
        for key, layout in LAYOUTS.items():
            self.layout_box.addItem(layout.name, key)
        self.layout_box.currentIndexChanged.connect(self.on_layout_changed)

        self.skip = QSpinBox()
        self.skip.setToolTip("Leave this many labels empty at the start of the sheet")

        form = QFormLayout()
        form.addRow("Label type:", self.layout_box)
        form.addRow("Skip used labels on sheet:", self.skip)

        buttons = QDialogButtonBox()
        buttons.addButton("Create PDF", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_create)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(form)
        layout.addWidget(QLabel("The PDF opens when ready — print it at 100% / \"Actual size\"."))
        layout.addWidget(buttons)

        self.on_layout_changed()

    def on_layout_changed(self):
        per_page = LAYOUTS[self.layout_box.currentData()].per_page
        self.skip.setRange(0, max(per_page - 1, 0))
        self.skip.setEnabled(per_page > 1)

    def on_create(self):
        items = [
            LabelItem(p.barcode, p.name, Decimal(p.selling_price), spin.value())
            for p, spin in zip(self.products, self.copies) if spin.value() > 0
        ]
        if not items:
            QMessageBox.information(self, "No labels", "Set at least one product to 1 or more labels.")
            return
        try:
            path = create_labels_pdf(items, self.layout_box.currentData(), self.skip.value())
        except Exception as e:
            QMessageBox.warning(self, "Could not create labels", str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.accept()
