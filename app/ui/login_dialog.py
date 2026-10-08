from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from app import config
from app.db.models import User
from app.services import auth_service as auth


def _title(text: str, sub: str) -> list[QLabel]:
    title = QLabel(text)
    title.setStyleSheet("font-size: 20px; font-weight: bold; color: #1f3a5f;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle = QLabel(sub)
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setWordWrap(True)
    return [title, subtitle]


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.user: User | None = None
        self.setWindowTitle(f"{config.SHOP_NAME} — Log in")
        self.setMinimumWidth(360)

        self.username = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.username.returnPressed.connect(self.password.setFocus)

        form = QFormLayout()
        form.addRow("Username:", self.username)
        form.addRow("Password:", self.password)

        buttons = QDialogButtonBox()
        buttons.addButton("Log in", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_login)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for w in _title(config.SHOP_NAME, "Log in to start selling"):
            layout.addWidget(w)
        layout.addLayout(form)
        layout.addWidget(buttons)
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
        buttons.addButton("Create account", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.on_create)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        for w in _title("Welcome!", "Create the owner (admin) account. The admin can add cashiers, "
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
