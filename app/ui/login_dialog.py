from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from app import config
from app.db.models import User
from app.services import auth_service as auth
from app.ui import theme


def _title(text: str, sub: str) -> list[QLabel]:
    first, _, rest = config.SHOP_NAME.partition(" ")
    logo = QLabel(f'{first.upper()}<span style="color:{theme.ACCENT}"> ●</span>')
    logo.setObjectName("logo")
    logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
    logo_sub = QLabel(rest.upper())
    logo_sub.setObjectName("logoSub")
    logo_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title = QLabel(text)
    title.setProperty("role", "section")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle = QLabel(sub)
    subtitle.setProperty("role", "muted")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setWordWrap(True)
    spacer = QLabel()
    spacer.setFixedHeight(10)
    return [logo, logo_sub, spacer, title, subtitle]


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user: User | None = None
        self.setWindowTitle(f"{config.SHOP_NAME} — Log in")
        self.setMinimumWidth(400)

        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")
        self.username.addAction(theme.icon("user"), QLineEdit.ActionPosition.LeadingPosition)
        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.addAction(theme.icon("lock"), QLineEdit.ActionPosition.LeadingPosition)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.username.returnPressed.connect(self.password.setFocus)

        login_btn = theme.button("Log in", "sign-in", "primary")
        login_btn.setObjectName("chargeBtn")
        login_btn.setDefault(True)
        login_btn.clicked.connect(self.on_login)  # also the default button, so Enter logs in

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(10)
        for w in _title("Welcome back", "Log in to start selling"):
            layout.addWidget(w)
        layout.addSpacing(8)
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addSpacing(6)
        layout.addWidget(login_btn)
        self.username.setFocus()

    def on_login(self):
        try:
            self.user = auth.authenticate(self.username.text(), self.password.text())
        except auth.AuthError as e:
            QMessageBox.warning(self, "Login failed", str(e))
            self.password.clear()
            self.password.setFocus()
            return
        self.accept()


class FirstAdminDialog(QDialog):
    """Shown once, on a brand-new install, to create the owner's admin account."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create admin account")
        self.setMinimumWidth(400)

        self.full_name = QLineEdit()
        self.username = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        for w in (self.password, self.confirm):
            w.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Your full name:", self.full_name)
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)
        form.addRow("Confirm password:", self.confirm)

        buttons = QDialogButtonBox()
        create_btn = buttons.addButton("Create account", QDialogButtonBox.ButtonRole.AcceptRole)
        create_btn.setProperty("variant", "primary")
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_create)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(10)
        for w in _title("Welcome", "Create the owner (admin) account. The admin can add cashiers, "
                                    "edit products and prices, and see reports."):
            layout.addWidget(w)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def on_create(self):
        if self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Passwords differ", "The two passwords don't match.")
            return
        try:
            auth.create_user(self.username.text(), self.full_name.text(), self.password.text(), "admin")
        except auth.AuthError as e:
            QMessageBox.warning(self, "Cannot create account", str(e))
            return
        self.accept()
