from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app import config
from app.db.models import User
from app.ui import theme
from app.ui.pos_view import PosView
from app.ui.products_view import ProductsView
from app.ui.reports_view import ReportsView
from app.ui.users_view import UsersView


class MainWindow(QMainWindow):
    logged_out = Signal()

    def __init__(self, user: User):
        super().__init__()
        self.user = user
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)  # free it on log out
        self.setWindowTitle(f"{config.APP_NAME}  ·  {config.SHOP_NAME}")
        self.resize(1280, 800)
        self.setMinimumSize(1100, 680)

        # Pages: (icon, label, subtitle, widget). Cashiers only sell.
        self.pos = PosView(user)
        pages = [("shopping-cart", "Sell", "Scan or tap products to add them to the sale", self.pos)]
        if user.role == "admin":
            pages += [
                ("package", "Products", "Prices, stock, photos and barcode labels", ProductsView()),
                ("chart-bar", "Reports", "Sales, best sellers and end-of-day cash-up", ReportsView()),
                ("users", "Users", "Staff accounts and passwords", UsersView()),
            ]
        self.pages = pages

        self.stack = QStackedWidget()
        for *_, widget in pages:
            self.stack.addWidget(widget)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), 1)
        self.setCentralWidget(root)

        self.go_to(0)

    # ---- layout ----
    def _build_sidebar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sidebar")
        bar.setFixedWidth(224)
        col = QVBoxLayout(bar)
        col.setContentsMargins(16, 22, 16, 16)
        col.setSpacing(4)

        first, _, rest = config.SHOP_NAME.partition(" ")
        logo = QLabel(f'{first.upper()}<span style="color:{theme.ACCENT}"> ●</span>')
        logo.setObjectName("logo")
        sub = QLabel(rest.upper())
        sub.setObjectName("logoSub")
        col.addWidget(logo)
        col.addWidget(sub)
        col.addSpacing(26)

        menu = QLabel("MENU")
        menu.setProperty("role", "faint")
        col.addWidget(menu)
        col.addSpacing(4)

        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        for i, (icon_name, label, *_rest) in enumerate(self.pages):
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(theme.icon(icon_name, theme.MUTED, active_color=theme.ACCENT))
            btn.setIconSize(QSize(20, 20))
            btn.setToolTip(f"{label}  (Ctrl+{i + 1})")
            self.nav.addButton(btn, i)
            col.addWidget(btn)
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self.go_to(i))
        self.nav.idClicked.connect(self.go_to)

        col.addStretch()

        card = QFrame()
        card.setObjectName("userCard")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 6, 10)
        avatar = QLabel(theme.initials(self.user.full_name))
        avatar.setObjectName("avatar")
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        who = QVBoxLayout()
        who.setSpacing(0)
        name = QLabel()
        bold = QFont(theme.FONT_TEXT)
        bold.setPixelSize(14)
        bold.setBold(True)
        name.setFont(bold)
        name.setText(QFontMetrics(bold).elidedText(self.user.full_name, Qt.TextElideMode.ElideRight, 86))
        name.setToolTip(self.user.full_name)
        role = QLabel(self.user.role.title())
        role.setProperty("role", "faint")
        who.addWidget(name)
        who.addWidget(role)
        logout_btn = theme.button("", "sign-out", "ghost", "Log out")
        logout_btn.setIconSize(QSize(20, 20))
        logout_btn.clicked.connect(self.on_logout)
        card_layout.addWidget(avatar)
        card_layout.addLayout(who, 1)
        card_layout.addWidget(logout_btn)
        col.addWidget(card)
        return bar

    def _build_content(self) -> QWidget:
        content = QWidget()
        content.setObjectName("content")
        col = QVBoxLayout(content)
        col.setContentsMargins(24, 18, 24, 18)
        col.setSpacing(14)

        top = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title = QLabel()
        self.title.setProperty("role", "title")
        self.subtitle = QLabel()
        self.subtitle.setProperty("role", "muted")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        top.addLayout(titles)
        top.addStretch()

        self.clock = QLabel()
        self.clock.setProperty("role", "muted")
        self.clock.setFont(theme.mono(13))
        top.addWidget(self.clock, alignment=Qt.AlignmentFlag.AlignTop)
        self._tick()
        timer = QTimer(self, interval=15_000, timeout=self._tick)
        timer.start()

        col.addLayout(top)
        col.addWidget(self.stack, 1)
        return content

    def _tick(self):
        self.clock.setText(datetime.now().strftime("%a %d %b  ·  %H:%M"))

    # ---- navigation ----
    def go_to(self, index: int):
        if not 0 <= index < len(self.pages):
            return
        _, label, subtitle, widget = self.pages[index]
        self.nav.button(index).setChecked(True)
        self.title.setText(label)
        self.subtitle.setText(subtitle)
        self.stack.setCurrentWidget(widget)

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
