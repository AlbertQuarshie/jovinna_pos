from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QVBoxLayout, QWidget,
)

from app.services import mpesa_service as mpesa
from app.ui import theme


class SettingsView(QWidget):
    """Admin settings. M-Pesa keys are saved encrypted on this computer only."""

    def __init__(self):
        super().__init__()
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setMaximumWidth(720)
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(panel, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
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
