from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from app import config
from app.db.models import User
from app.ui.pos_view import PosView
from app.ui.products_view import ProductsView
from app.ui.reports_view import ReportsView
from app.ui.users_view import UsersView

STYLE = """
QWidget { font-size: 14px; }
#header { background: #1f3a5f; color: white; padding: 12px 16px; }
#shopName { font-size: 22px; font-weight: bold; color: white; }
#tagline { color: #cfdcec; }
#userLabel { color: white; }
#logoutBtn { background: transparent; color: white; border: 1px solid #cfdcec; border-radius: 4px; }
#logoutBtn:hover { background: #2c4d78; }
#scanInput { font-size: 18px; padding: 10px; border: 2px solid #1f3a5f; border-radius: 6px; }
#totalLabel { font-size: 32px; font-weight: bold; color: #1f3a5f; }
#checkoutBtn { background: #2e7d32; color: white; font-size: 18px; padding: 14px; border-radius: 6px; }
#checkoutBtn:hover { background: #256628; }
QPushButton { padding: 6px 12px; }
"""


class MainWindow(QMainWindow):
    logged_out = Signal()

    def __init__(self, user: User):
        super().__init__()
        self.user = user
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # free it on log out
        self.setWindowTitle(f"{config.SHOP_NAME} — POS")
        self.resize(1200, 750)
        self.setStyleSheet(STYLE)

        header = QWidget()
        header.setObjectName("header")
        titles = QVBoxLayout()
        name = QLabel(config.SHOP_NAME)
        name.setObjectName("shopName")
        tagline = QLabel(config.SHOP_TAGLINE)
        tagline.setObjectName("tagline")
        titles.addWidget(name)
        titles.addWidget(tagline)

        user_label = QLabel(f"{user.full_name}  ·  {user.role.title()}")
        user_label.setObjectName("userLabel")
        logout_btn = QPushButton("Log out")
        logout_btn.setObjectName("logoutBtn")
        logout_btn.clicked.connect(self.on_logout)

        header_layout = QHBoxLayout(header)
        header_layout.addLayout(titles)
        header_layout.addStretch()
        header_layout.addWidget(user_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_layout.addWidget(logout_btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Cashiers only sell; the admin also manages products, sees reports and manages users
        self.pos = PosView(user)
        tabs = QTabWidget()
        tabs.addTab(self.pos, "Sales (POS)")
        if user.role == "admin":
            tabs.addTab(ProductsView(), "Products")
            tabs.addTab(ReportsView(), "Reports")
            tabs.addTab(UsersView(), "Users")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header)
        layout.addWidget(tabs)
        self.setCentralWidget(central)

    def on_logout(self):
        if self.pos.cart:
            answer = QMessageBox.question(self, "Log out", "There are items in the cart. Discard them and log out?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._logging_out = True
        self.close()

    def closeEvent(self, event):
        super().closeEvent(event)
        if getattr(self, "_logging_out", False):
            self.logged_out.emit()  # back to the login screen
        else:
            QApplication.quit()  # window closed with X: exit the app
