from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app.db.models import User
from app.services import auth_service as auth
from app.ui import theme


def avatar(name: str, active: bool) -> QPixmap:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(theme.ACCENT if active else theme.SURFACE_3))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 64, 64)
    f = QFont(theme.FONT_TEXT)
    f.setPixelSize(24)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(theme.ON_ACCENT if active else theme.MUTED))
    p.drawText(QRectF(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, theme.initials(name))
    p.end()
    return pm


class UserDialog(QDialog):
    """Add a user (with password) or edit an existing one's name, role and status."""

    def __init__(self, parent, user: User | None = None):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle("Edit User" if user else "Add User")
        self.setMinimumWidth(380)

        self.username = QLineEdit()
        self.full_name = QLineEdit()
        self.role = QComboBox()
        self.role.addItems(auth.ROLES)
        self.role.setCurrentText("cashier")
        self.active = QCheckBox("Account active (can log in)")
        self.active.setChecked(True)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        form = QFormLayout()
        form.addRow("Username:", self.username)
        form.addRow("Full name:", self.full_name)
        form.addRow("Role:", self.role)
        if user:
            self.username.setText(user.username)
            self.username.setEnabled(False)
            self.full_name.setText(user.full_name)
            self.role.setCurrentText(user.role)
            self.active.setChecked(user.is_active)
            form.addRow("", self.active)
        else:
            form.addRow("Password:", self.password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def on_save(self):
        try:
            if self.user:
                auth.update_user(self.user.id, full_name=self.full_name.text(),
                                 role=self.role.currentText(), is_active=self.active.isChecked())
            else:
                auth.create_user(self.username.text(), self.full_name.text(), self.password.text(),
                                 self.role.currentText())
        except auth.AuthError as e:
            QMessageBox.warning(self, "Cannot save", str(e))
            return
        self.accept()


class PasswordDialog(QDialog):
    def __init__(self, parent, user: User):
        super().__init__(parent)
        self.user = user
        self.setWindowTitle(f"Reset password — {user.full_name}")
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        for w in (self.password, self.confirm):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        form = QFormLayout()
        form.addRow("New password:", self.password)
        form.addRow("Confirm:", self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("variant", "primary")
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def on_save(self):
        if self.password.text() != self.confirm.text():
            QMessageBox.warning(self, "Passwords differ", "The two passwords don't match.")
            return
        try:
            auth.set_password(self.user.id, self.password.text())
        except auth.AuthError as e:
            QMessageBox.warning(self, "Cannot save", str(e))
            return
        self.accept()


class UsersView(QWidget):
    COLUMNS = ["Username", "Full name", "Role", "Status"]

    def __init__(self):
        super().__init__()
        self.users: list[User] = []

        add_btn = theme.button("Add user", "user-plus", "primary")
        edit_btn = theme.button("Edit", "pencil-simple")
        pw_btn = theme.button("Reset password", "key")
        add_btn.clicked.connect(self.on_add)
        edit_btn.clicked.connect(self.on_edit)
        pw_btn.clicked.connect(self.on_reset_password)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addStretch()
        for b in (edit_btn, pw_btn, add_btn):
            top.addWidget(b)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setIconSize(QSize(32, 32))
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self.on_edit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self):
        self.users = auth.list_users()
        self.table.setRowCount(len(self.users))
        for r, u in enumerate(self.users):
            for c, v in enumerate([u.username, u.full_name, u.role.title(),
                                   "Active" if u.is_active else "Disabled"]):
                item = QTableWidgetItem(v)
                if not u.is_active:
                    item.setForeground(QColor(theme.FAINT))
                elif c == 2 and u.role == "admin":
                    item.setForeground(QColor(theme.ACCENT))
                elif c == 3:
                    item.setForeground(QColor(theme.SUCCESS))
                self.table.setItem(r, c, item)
            self.table.item(r, 0).setIcon(QIcon(avatar(u.full_name, u.is_active)))

    def selected(self) -> User | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.users):
            return self.users[row]
        QMessageBox.information(self, "Select a user", "Click a user in the list first.")
        return None

    def on_add(self):
        if UserDialog(self).exec():
            self.refresh()

    def on_edit(self):
        user = self.selected()
        if user and UserDialog(self, user).exec():
            self.refresh()

    def on_reset_password(self):
        user = self.selected()
        if user and PasswordDialog(self, user).exec():
            QMessageBox.information(self, "Password changed", f"New password set for {user.full_name}.")
