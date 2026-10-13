import shutil

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QProgressDialog, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app import config
from app.services import import_service as imp
from app.ui import theme

TEMPLATE = config.BASE_DIR / "templates" / "Jovinna_Products_Template.xlsx"


class ImportDialog(QDialog):
    """Pick the Excel sheet, preview what will happen to every row, then import."""

    COLUMNS = ["Row", "Result", "Name", "Category", "Price", "Stock", "Barcode", "Photo"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import products from Excel")
        self.resize(1000, 600)
        self.rows: list[imp.ImportRow] = []
        self.imported = False

        intro = QLabel("Fill in the product template in Excel (put the photos in the same folder), "
                       "then choose the file. Nothing is saved until you click Import.")
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        template_btn = theme.button("Save blank template…", "download-simple")
        template_btn.clicked.connect(self.on_save_template)
        choose_btn = theme.button("Choose Excel file…", "table", "primary")
        choose_btn.clicked.connect(self.on_choose)
        top = QHBoxLayout()
        top.addWidget(intro, 1)
        top.addWidget(template_btn)
        top.addWidget(choose_btn)

        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 240)  # long error messages wrap instead of squeezing names
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)

        self.import_btn = theme.button("Import", "check", "primary")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.on_import)
        close_btn = theme.button("Close")
        close_btn.clicked.connect(self.reject)
        bottom = QHBoxLayout()
        bottom.addWidget(self.summary, 1)
        bottom.addWidget(close_btn)
        bottom.addWidget(self.import_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self.table, 1)
        layout.addLayout(bottom)

    def on_save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save product template", TEMPLATE.name, "Excel (*.xlsx)")
        if path:
            shutil.copy(TEMPLATE, path)
            QMessageBox.information(self, "Template saved", f"Saved to:\n{path}")

    def on_choose(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the product sheet", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            self.rows = imp.read_sheet(path)
        except imp.SheetError as e:
            QMessageBox.warning(self, "Can't read that file", str(e))
            return
        self.show_preview()

    def show_preview(self):
        colours = {"new": theme.SUCCESS, "update": theme.ACCENT, "error": theme.DANGER}
        self.table.setRowCount(len(self.rows))
        for i, r in enumerate(self.rows):
            result = {"new": "New", "update": "Update"}.get(r.action, "Error: " + "; ".join(r.problems))
            values = [str(r.row), result, r.name, " › ".join(x for x in (r.main, r.sub) if x),
                      f"{r.price:,.2f}" if r.price is not None else "", str(r.stock),
                      r.barcode or "(new)", r.photo.name if r.photo else ""]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 1:
                    item.setForeground(QColor(colours[r.action]))
                    item.setToolTip(result)
                self.table.setItem(i, c, item)
        new = sum(r.action == "new" for r in self.rows)
        upd = sum(r.action == "update" for r in self.rows)
        bad = sum(r.action == "error" for r in self.rows)
        self.summary.setText(
            f"<span style='color:{theme.SUCCESS}'>{new} new</span>  ·  "
            f"<span style='color:{theme.ACCENT}'>{upd} to update</span>  ·  "
            f"<span style='color:{theme.DANGER}'>{bad} with errors (skipped — fix them in Excel and choose the file again)</span>")
        self.table.resizeRowsToContents()
        self.import_btn.setEnabled(new + upd > 0)
        self.import_btn.setText(f"  Import {new + upd} products")

    def on_import(self):
        todo = sum(r.ok for r in self.rows)
        progress = QProgressDialog("Importing products…", None, 0, todo, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        def step(done, total):
            progress.setValue(done)
            QApplication.processEvents()

        result = imp.apply(self.rows, step)
        progress.close()
        theme.clear_image_cache()
        self.imported = True
        msg = f"{result.created} products added, {result.updated} updated."
        if result.failed:
            msg += "\n\nThese rows couldn't be saved:\n" + "\n".join(result.failed[:15])
        QMessageBox.information(self, "Import finished", msg)
        self.accept()
