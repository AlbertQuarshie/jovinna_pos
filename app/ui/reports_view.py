import csv
from datetime import datetime, time, timedelta
from decimal import Decimal

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from app import config
from app.services import report_service as rs
from app.services.receipt_service import create_receipt_pdf


def money(value: Decimal) -> str:
    return f"{value:,.2f}"


def make_table(headers: list[str], stretch_col: int = 0) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    return t


def fill_table(table: QTableWidget, rows: list[list], numeric_cols: set[int]):
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(str(value))
            if c in numeric_cols:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, c, item)


class StatCard(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self.setObjectName("statCard")
        self.value = QLabel("—")
        self.value.setObjectName("statValue")
        self.note = QLabel("")
        self.note.setObjectName("statNote")
        layout = QVBoxLayout(self)
        caption = QLabel(title.upper())
        caption.setObjectName("statTitle")
        layout.addWidget(caption)
        layout.addWidget(self.value)
        layout.addWidget(self.note)

    def set(self, value: str, note: str = ""):
        self.value.setText(value)
        self.note.setText(note)


class ReportsView(QWidget):
    PERIODS = ["Today", "Yesterday", "This week", "This month", "Last month", "Custom"]

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            #statCard { background: #f3f6fa; border: 1px solid #dde4ee; border-radius: 8px; }
            #statTitle { color: #5b6b80; font-size: 11px; font-weight: bold; }
            #statValue { color: #1f3a5f; font-size: 22px; font-weight: bold; }
            #statNote { color: #5b6b80; font-size: 12px; }
        """)

        # Period picker
        self.period = QComboBox()
        self.period.addItems(self.PERIODS)
        self.period.currentTextChanged.connect(self.on_period_changed)
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_to = QDateEdit(calendarPopup=True)
        for d in (self.date_from, self.date_to):
            d.setDisplayFormat("dd/MM/yyyy")
            d.setDate(QDate.currentDate())
            d.dateChanged.connect(self.on_custom_dates)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        export_btn = QPushButton("Export to Excel (CSV)")
        export_btn.clicked.connect(self.on_export)

        top = QHBoxLayout()
        top.addWidget(QLabel("Period:"))
        top.addWidget(self.period)
        top.addWidget(QLabel("From:"))
        top.addWidget(self.date_from)
        top.addWidget(QLabel("To:"))
        top.addWidget(self.date_to)
        top.addStretch()
        top.addWidget(refresh_btn)
        top.addWidget(export_btn)

        # Summary cards
        self.cards = {key: StatCard(title) for key, title in [
            ("revenue", f"Sales ({config.CURRENCY})"), ("profit", f"Profit ({config.CURRENCY})"),
            ("count", "Transactions"), ("items", "Items sold"),
        ]}
        cards = QGridLayout()
        for i, card in enumerate(self.cards.values()):
            cards.addWidget(card, 0, i)

        # Detail tabs
        self.sales_table = make_table(["Receipt", "Date & time", "Cashier", "Items", "Total", "Payment"], 2)
        self.sales_table.doubleClicked.connect(self.on_open_receipt)
        self.top_table = make_table(["Barcode", "Product", "Qty sold", "Sales", "Profit"], 1)
        self.payment_table = make_table(["Payment method", "Transactions", "Amount"])
        self.cashier_table = make_table(["Cashier", "Transactions", "Amount"])
        self.low_table = make_table(["Barcode", "Product", "In stock", "Alert level"], 1)

        cashup = QWidget()
        cashup_layout = QVBoxLayout(cashup)
        cashup_layout.addWidget(QLabel("<b>By payment method</b> — cash should match the money in the drawer"))
        cashup_layout.addWidget(self.payment_table)
        cashup_layout.addWidget(QLabel("<b>By cashier</b>"))
        cashup_layout.addWidget(self.cashier_table)

        sales_tab = QWidget()
        sales_layout = QVBoxLayout(sales_tab)
        sales_layout.addWidget(QLabel("Double-click a sale to open its receipt."))
        sales_layout.addWidget(self.sales_table)

        self.tabs = QTabWidget()
        self.tabs.addTab(sales_tab, "Sales")
        self.tabs.addTab(self.top_table, "Best sellers")
        self.tabs.addTab(cashup, "Cash-up")
        self.tabs.addTab(self.low_table, "Low stock")

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(cards)
        layout.addWidget(self.tabs, 1)

        self.on_period_changed("Today")

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    # ---- period handling ----
    def on_period_changed(self, period: str):
        today = QDate.currentDate()
        ranges = {
            "Today": (today, today),
            "Yesterday": (today.addDays(-1), today.addDays(-1)),
            "This week": (today.addDays(1 - today.dayOfWeek()), today),
            "This month": (QDate(today.year(), today.month(), 1), today),
        }
        last_month_end = QDate(today.year(), today.month(), 1).addDays(-1)
        ranges["Last month"] = (QDate(last_month_end.year(), last_month_end.month(), 1), last_month_end)
        if period in ranges:
            start, end = ranges[period]
            for widget, value in ((self.date_from, start), (self.date_to, end)):
                widget.blockSignals(True)
                widget.setDate(value)
                widget.blockSignals(False)
        self.refresh()

    def on_custom_dates(self):
        if self.period.currentText() != "Custom":
            self.period.blockSignals(True)
            self.period.setCurrentText("Custom")
            self.period.blockSignals(False)
        self.refresh()

    def date_range(self) -> tuple[datetime, datetime]:
        start = datetime.combine(self.date_from.date().toPython(), time.min)
        end = datetime.combine(self.date_to.date().toPython(), time.min) + timedelta(days=1)
        return start, max(end, start + timedelta(days=1))

    # ---- data ----
    def refresh(self):
        start, end = self.date_range()
        s = rs.summary(start, end)
        self.cards["revenue"].set(money(s.revenue), f"Discounts given: {money(s.discounts)}")
        self.cards["profit"].set(money(s.profit), f"Margin: {s.margin_pct:.1f}%")
        self.cards["count"].set(str(s.sales_count), f"Average sale: {money(s.average_sale)}")
        self.cards["items"].set(str(s.items_sold), "")

        fill_table(self.sales_table, [
            [f"#{i:06d}", t.strftime("%d/%m/%Y %H:%M"), who, q, money(total), m.title()]
            for i, t, who, q, total, m in rs.sales_list(start, end)
        ], {3, 4})
        fill_table(self.top_table, [
            [b, n, q, money(r), money(p)] for b, n, q, r, p in rs.top_products(start, end)
        ], {2, 3, 4})
        fill_table(self.payment_table, [
            [m.title(), n, money(t)] for m, n, t in rs.by_payment_method(start, end)
        ], {1, 2})
        fill_table(self.cashier_table, [
            [name, n, money(t)] for name, n, t in rs.by_cashier(start, end)
        ], {1, 2})
        fill_table(self.low_table, [
            [p.barcode, p.name, p.stock_qty, p.reorder_level] for p in rs.low_stock()
        ], {2, 3})
        self.tabs.setTabText(3, f"Low stock ({self.low_table.rowCount()})")

    def on_open_receipt(self, index):
        sale_id = int(self.sales_table.item(index.row(), 0).text().lstrip("#"))
        try:
            path = create_receipt_pdf(sale_id)
        except Exception as e:
            QMessageBox.warning(self, "Receipt error", str(e))
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def on_export(self):
        """Save the table in the open tab as a CSV file, which opens in Excel."""
        current = self.tabs.currentWidget()
        tables = [current] if isinstance(current, QTableWidget) else current.findChildren(QTableWidget)
        name = self.tabs.tabText(self.tabs.currentIndex()).split(" (")[0].lower().replace(" ", "_")
        start, end = self.date_range()
        default = f"{name}_{start:%Y-%m-%d}_to_{end - timedelta(days=1):%Y-%m-%d}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export report", default, "CSV files (*.csv)")
        if not path:
            return
        def cell(t: QTableWidget, r: int, c: int) -> str:
            text = t.item(r, c).text()
            plain = text.replace(",", "")
            # "1,050.00" -> "1050.00" so Excel treats amounts as numbers
            return plain if plain.replace(".", "", 1).lstrip("-").isdigit() else text

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            for t in tables:
                writer.writerow([t.horizontalHeaderItem(c).text() for c in range(t.columnCount())])
                for r in range(t.rowCount()):
                    writer.writerow([cell(t, r, c) for c in range(t.columnCount())])
                writer.writerow([])
        QMessageBox.information(self, "Exported", f"Saved to:\n{path}")
