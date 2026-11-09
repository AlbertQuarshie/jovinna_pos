from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from app import config
from app.services import app_settings, backup_service
from app.services import mpesa_service as mpesa
from app.ui import theme


def _panel(title: str, intro: str = "") -> tuple[QFrame, QVBoxLayout]:
    panel = QFrame()
    panel.setObjectName("panel")
    col = QVBoxLayout(panel)
    col.setContentsMargins(24, 20, 24, 20)
    col.setSpacing(12)
    heading = QLabel(title)
    heading.setProperty("role", "section")
    col.addWidget(heading)
    if intro:
        text = QLabel(intro)
        text.setWordWrap(True)
        text.setProperty("role", "muted")
        col.addWidget(text)
    return panel, col


def _wrap(widget: QWidget, panel: QFrame) -> None:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(panel)


class AppearanceSection(QFrame):
    def __init__(self):
        super().__init__()
        panel, col = _panel("Appearance", "Choose how the app looks on this computer. You can also switch "
                                          "with the sun / moon button at the top right.")
        self.buttons = QButtonGroup(self)
        row = QHBoxLayout()
        for mode, label, icon_name in (("dark", " Dark", "moon"), ("light", " Light", "sun")):
            b = theme.button(label, icon_name, "segment")
            b.setCheckable(True)
            b.setChecked(theme.MODE == mode)
            b.setProperty("mode", mode)
            b.setMinimumWidth(130)
            self.buttons.addButton(b)
            row.addWidget(b)
        row.addStretch()
        self.buttons.buttonClicked.connect(self.on_pick)
        col.addLayout(row)
        _wrap(self, panel)

    def on_pick(self, button):
        window = self.window()
        if hasattr(window, "change_theme"):
            window.change_theme(button.property("mode"))


class ShopSection(QFrame):
    FIELDS = (("shop_name", "Shop name:"), ("shop_tagline", "Tagline:"), ("shop_phone", "Phone:"),
              ("shop_address", "Address:"), ("receipt_footer", "Receipt message:"))

    def __init__(self):
        super().__init__()
        panel, col = _panel("Shop and receipts", "Shown on receipts, barcode labels and the login screen.")
        self.fields = {key: QLineEdit() for key, _ in self.FIELDS}
        self.fields["receipt_footer"].setPlaceholderText("e.g. Thank you! Welcome back anytime")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        for key, label in self.FIELDS:
            form.addRow(label, self.fields[key])
        col.addLayout(form)
        save = theme.button("Save", "check", "primary")
        save.clicked.connect(self.on_save)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(save)
        col.addLayout(row)
        _wrap(self, panel)
        values = app_settings.load()
        for key, w in self.fields.items():
            w.setText(values[key] or "")

    def on_save(self):
        values = {k: w.text().strip() for k, w in self.fields.items()}
        if not values["shop_name"]:
            QMessageBox.warning(self, "Shop name", "Enter the shop name.")
            return
        app_settings.save(**values)
        QMessageBox.information(self, "Saved", "Shop details saved. New receipts and labels use them now; "
                                               "the sidebar name updates next time you log in.")


class BackupSection(QFrame):
    def __init__(self):
        super().__init__()
        panel, col = _panel("Backups", "The database is copied automatically when the app opens, every hour "
                                       "and when it closes. A second copy outside this computer protects "
                                       "against theft or a broken disk.")
        self.copy_dir = QLineEdit()
        self.copy_dir.setPlaceholderText("Optional: a Google Drive folder or a flash drive")
        browse = theme.button("Browse…", "folder-open")
        browse.clicked.connect(self.on_browse)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.copy_dir, 1)
        dir_row.addWidget(browse)
        self.keep_days = QSpinBox()
        self.keep_days.setRange(7, 365)
        self.keep_days.setSuffix(" days")
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Second copy to:", dir_row)
        form.addRow("Keep backups for:", self.keep_days)
        col.addLayout(form)
        self.last = QLabel()
        self.last.setProperty("role", "faint")
        self.last.setWordWrap(True)
        col.addWidget(self.last)
        open_btn = theme.button("Open folder", "folder-open")
        open_btn.clicked.connect(self.on_open)
        now_btn = theme.button("Back up now", "cloud-arrow-up")
        now_btn.clicked.connect(self.on_backup_now)
        save = theme.button("Save", "check", "primary")
        save.clicked.connect(self.on_save)
        row = QHBoxLayout()
        row.addStretch()
        for b in (open_btn, now_btn, save):
            row.addWidget(b)
        col.addLayout(row)
        _wrap(self, panel)
        values = app_settings.load()
        self.copy_dir.setText(values["backup_copy_dir"] or "")
        self.keep_days.setValue(int(values["backup_keep_days"]))
        self.show_last()

    def show_last(self):
        latest = backup_service.latest_backup()
        when = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%d %b %Y, %H:%M") if latest else "never"
        self.last.setText(f"Last backup: {when}   ·   Saved in {backup_service.DAILY_DIR}")

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose where to keep a second copy of the backups")
        if folder:
            self.copy_dir.setText(folder)

    def on_open(self):
        backup_service.DAILY_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(backup_service.DAILY_DIR)))

    def on_save(self):
        folder = self.copy_dir.text().strip()
        if folder and not Path(folder).is_dir():
            QMessageBox.warning(self, "Folder not found", "That folder doesn't exist. Is the flash drive plugged in?")
            return
        app_settings.save(backup_copy_dir=folder, backup_keep_days=self.keep_days.value())
        QMessageBox.information(self, "Saved", "Backup settings saved.")

    def on_backup_now(self):
        path = backup_service.daily_backup()
        self.show_last()
        if path is None:
            QMessageBox.warning(self, "Backup failed",
                                f"The backup couldn't be made. Details are in:\n{backup_service.LOG_FILE}")
            return
        extra = f"\nA second copy went to {config.BACKUP_COPY_DIR}" if config.BACKUP_COPY_DIR else ""
        QMessageBox.information(self, "Backed up", f"Saved {path.name}{extra}")


class SettingsView(QScrollArea):
    """Admin settings: appearance, shop details, backups and M-Pesa."""

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 12, 0)
        col.setSpacing(16)
        for section in (AppearanceSection(), ShopSection(), BackupSection(), MpesaSection()):
            section.setMaximumWidth(760)
            col.addWidget(section)
        col.addStretch()
        self.setWidget(page)


class MpesaSection(QFrame):
    """M-Pesa STK Push. Keys are saved encrypted on this computer only."""

    def __init__(self):
        super().__init__()
        panel = QFrame()
        panel.setObjectName("panel")
        col = QVBoxLayout(panel)
        col.setContentsMargins(24, 20, 24, 20)
        col.setSpacing(12)

        title = QLabel("M-Pesa STK Push")
        title.setProperty("role", "section")
        intro = QLabel("Sends the payment prompt to the customer's phone when they pay by M-Pesa. "
                       "Keys come from your Safaricom Daraja app (developer.safaricom.co.ke). They're "
                       "stored encrypted on this computer only.")
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")

        self.enabled = QCheckBox("Use STK Push for mobile money payments")
        self.environment = QComboBox()
        self.environment.addItem("Test (Safaricom sandbox, shortcode 174379)", "sandbox")
        self.environment.addItem("Live (real payments to the till)", "live")
        self.environment.currentIndexChanged.connect(self.update_fields)
        self.consumer_key = QLineEdit()
        self.consumer_secret = QLineEdit()
        self.passkey = QLineEdit()
        for w in (self.consumer_secret, self.passkey):
            w.setEchoMode(QLineEdit.EchoMode.Password)
        self.store_number = QLineEdit()
        self.store_number.setPlaceholderText("Store / head office number from Safaricom")
        self.till_number = QLineEdit()
        self.till_number.setPlaceholderText("The Buy Goods till customers pay to")
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("https://jovinna-mpesa.yourname.workers.dev")
        self.server_key = QLineEdit()
        self.server_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.server_key.setPlaceholderText("The APP_KEY you set on the server")
        self.callback_url = QLineEdit()
        self.callback_url.setPlaceholderText("Only if you don't use a callback server, e.g. webhook.site while testing")
        self.callback_shown = QLabel()
        self.callback_shown.setProperty("role", "faint")
        self.callback_shown.setWordWrap(True)
        self.callback_shown.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self.server_url, self.server_key, self.callback_url):
            w.textChanged.connect(self.update_callback_shown)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("", self.enabled)
        form.addRow("Mode:", self.environment)
        form.addRow("Consumer Key:", self.consumer_key)
        form.addRow("Consumer Secret:", self.consumer_secret)
        self.live_rows = [("Passkey:", self.passkey), ("Store number:", self.store_number),
                          ("Till number:", self.till_number)]
        for label, w in self.live_rows:
            form.addRow(label, w)
        form.addRow("Callback server:", self.server_url)
        form.addRow("Server key:", self.server_key)
        form.addRow("Other callback URL:", self.callback_url)
        form.addRow("", self.callback_shown)
        self.form = form
        self.sandbox_note = QLabel("Test mode uses Safaricom's test shortcode 174379, so only the Consumer "
                                   "Key and Secret from your sandbox app are needed.")
        self.sandbox_note.setWordWrap(True)
        self.sandbox_note.setProperty("role", "faint")

        test_btn = theme.button("Test connection", "wifi-high")
        test_btn.clicked.connect(self.on_test)
        server_btn = theme.button("Test callback server", "link")
        server_btn.clicked.connect(self.on_test_server)
        save_btn = theme.button("Save", "check", "primary")
        save_btn.clicked.connect(self.on_save)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(server_btn)
        buttons.addWidget(test_btn)
        buttons.addWidget(save_btn)

        for w in (title, intro):
            col.addWidget(w)
        col.addLayout(form)
        col.addWidget(self.sandbox_note)
        col.addLayout(buttons)

        _wrap(self, panel)
        self.load()

    def load(self):
        s = mpesa.load_settings()
        self.enabled.setChecked(s.enabled)
        self.environment.setCurrentIndex(max(self.environment.findData(s.environment), 0))
        for name in ("consumer_key", "consumer_secret", "passkey", "store_number", "till_number", "callback_url",
                     "server_url", "server_key"):
            getattr(self, name).setText(getattr(s, name))
        self.update_fields()
        self.update_callback_shown()

    def current(self) -> mpesa.Settings:
        return mpesa.Settings(
            environment=self.environment.currentData(), enabled=self.enabled.isChecked(),
            **{n: getattr(self, n).text().strip()
               for n in ("consumer_key", "consumer_secret", "passkey", "store_number", "till_number",
                         "callback_url", "server_url", "server_key")})

    def update_fields(self):
        live = self.environment.currentData() == "live"
        for _, w in self.live_rows:
            self.form.setRowVisible(w, live)
        self.sandbox_note.setVisible(not live)

    def update_callback_shown(self):
        s = self.current()
        note = "" if mpesa.has_server(s) or s.callback_url.strip() else " (placeholder: no M-Pesa codes)"
        self.callback_shown.setText(f"Safaricom will send results to: {mpesa.callback_url(s)}{note}")

    def on_test_server(self):
        s = self.current()
        if not mpesa.has_server(s):
            QMessageBox.information(self, "Callback server", "Enter the callback server address and key first.")
            return
        try:
            mpesa.test_server(s)
        except mpesa.MpesaError as e:
            QMessageBox.warning(self, "Callback server", str(e))
            return
        QMessageBox.information(self, "Callback server", "The callback server is working and accepted the key.")

    def on_test(self):
        try:
            mpesa.test_connection(self.current())
        except mpesa.MpesaError as e:
            QMessageBox.warning(self, "Connection failed", str(e))
            return
        QMessageBox.information(self, "Connected", "Safaricom accepted the keys.")

    def on_save(self):
        s = self.current()
        if s.enabled and not s.ready:
            QMessageBox.warning(self, "Missing details", "Fill in every field shown before turning STK Push on.")
            return
        mpesa.save_settings(s)
        QMessageBox.information(self, "Saved", "M-Pesa settings saved.")
