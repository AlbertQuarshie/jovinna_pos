from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QHeaderView, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from app.db.models import User
from app.services import auth_service as auth


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

        add_btn = QPushButton("+ Add User")
        edit_btn = QPushButton("Edit")
        pw_btn = QPushButton("Reset Password")
        add_btn.clicked.connect(self.on_add)
        edit_btn.clicked.connect(self.on_edit)
        pw_btn.clicked.connect(self.on_reset_password)
        top = QHBoxLayout()
        for b in (add_btn, edit_btn, pw_btn):
            top.addWidget(b)
        top.addStretch()

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self.on_edit)

        layout = QVBoxLayout(self)
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
                    item.setForeground(QColor("#999999"))
                self.table.setItem(r, c, item)

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
