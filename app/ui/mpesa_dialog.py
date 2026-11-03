from concurrent.futures import Future, ThreadPoolExecutor
from decimal import Decimal

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from app import config
from app.services import mpesa_service as mpesa
from app.ui import theme

POLL_SECONDS = 5
GIVE_UP_SECONDS = 120  # Safaricom expires the prompt after about a minute
CODE_TRIES = 5         # times to ask the callback server for the M-Pesa code (2 s apart)

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mpesa")


class MpesaDialog(QDialog):
    """Sends the STK push and waits for the customer to pay. accept() = paid; self.checkout_id holds
    Safaricom's reference. Network calls run in the background so the window never freezes."""

    def __init__(self, parent, settings: mpesa.Settings, phone: str, amount: Decimal, reference: str):
        super().__init__(parent)
        self.settings, self.phone, self.amount, self.reference = settings, phone, amount, reference
        self.checkout_id: str | None = None
        self.receipt_code: str | None = None   # M-Pesa code, when a callback server is set up
        self.print_receipt = False             # the cashier's choice on the confirmation screen
        self.future: Future | None = None
        self.waited = 0
        self.setWindowTitle("M-Pesa payment")
        self.setMinimumWidth(480)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        amount_label = QLabel(f"{config.CURRENCY} {mpesa.whole_shillings(amount):,}")
        amount_label.setFont(theme.mono(26, bold=True))
        amount_label.setStyleSheet(f"color: {theme.ACCENT};")
        amount_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        to = QLabel(f"to 0{phone[3:6]} {phone[6:9]} {phone[9:]}")
        to.setProperty("role", "muted")
        to.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel("Sending the request to the customer's phone…")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setMinimumHeight(84)  # room for the 3-line confirmation
        if settings.environment == "sandbox":
            test = QLabel("TEST MODE — Safaricom sandbox (test shortcode 174379)")
            test.setStyleSheet(f"color: {theme.DANGER}; font-size: 11px; font-weight: bold;")
            test.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.retry_btn = theme.button("Send again", "arrows-clockwise", "primary")
        self.retry_btn.clicked.connect(self.send)
        # Ask Safaricom again right now, e.g. the customer paid late or the internet dropped
        self.check_btn = theme.button("Check payment", "magnifying-glass")
        self.check_btn.clicked.connect(self.check_now)
        self.check_btn.hide()
        self.cancel_btn = theme.button("Cancel", "x")
        self.cancel_btn.clicked.connect(self.reject)
        # Confirmation screen buttons, shown once the payment is received
        self.print_btn = theme.button("Print receipt", "printer", "primary")
        self.print_btn.clicked.connect(lambda: self._finish(True))
        self.no_print_btn = theme.button("No receipt")
        self.no_print_btn.clicked.connect(lambda: self._finish(False))
        for b in (self.print_btn, self.no_print_btn):
            b.hide()
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.check_btn)
        buttons.addWidget(self.retry_btn)
        buttons.addWidget(self.no_print_btn)
        buttons.addWidget(self.print_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(8)
        layout.addWidget(self.icon)
        layout.addWidget(amount_label)
        layout.addWidget(to)
        layout.addSpacing(8)
        layout.addWidget(self.status)
        if settings.environment == "sandbox":
            layout.addWidget(test)
        layout.addSpacing(8)
        layout.addLayout(buttons)

        self.timer = QTimer(self, interval=500, timeout=self._check)
        QTimer.singleShot(0, self.send)

    def _set(self, icon: str, colour: str, text: str):
        self.icon.setPixmap(theme.icon(icon, colour).pixmap(52, 52))
        self.status.setText(text)

    def send(self):
        self.retry_btn.hide()
        self.check_btn.hide()
        self.checkout_id = None
        self.waited = 0
        self._set("device-mobile", theme.ACCENT, "Sending the request to the customer's phone…")
        self.future = _pool.submit(mpesa.stk_push, self.settings, self.phone, self.amount, self.reference)
        self.stage = "push"
        self.timer.start()

    def _check(self):
        """Runs every half second on the UI thread; only looks at finished background work."""
        if self.future is None or not self.future.done():
            return
        try:
            result = self.future.result()
        except mpesa.MpesaError as e:
            return self._fail(str(e))
        except Exception as e:  # noqa: BLE001
            return self._fail(f"Something went wrong: {e}")

        if self.stage == "push":
            self.checkout_id = result
            self._set("device-mobile", theme.ACCENT,
                      "Ask the customer to enter their M-Pesa PIN on their phone…")
            self.stage = "wait"
            self.future = None
            self.check_btn.show()
            QTimer.singleShot(POLL_SECONDS * 1000, self._poll)
            return

        if self.stage == "code":
            self.future = None
            if result and result.get("receipt"):
                self.receipt_code = result["receipt"]
                return self._confirm()
            self.code_tries += 1
            if self.code_tries >= CODE_TRIES:
                return self._confirm()  # paid either way; just no code to show
            QTimer.singleShot(2000, self._fetch_code)
            return

        state, message = result
        self.future = None
        if state == "paid":
            self._set("check-circle", theme.SUCCESS, "Payment received")
            for b in (self.cancel_btn, self.check_btn, self.retry_btn):
                b.hide()
            if mpesa.has_server(self.settings):
                # Safaricom's callback (with the M-Pesa code) can arrive a few seconds after this
                self.status.setText("Payment received. Getting the M-Pesa code…")
                self.stage, self.code_tries = "code", 0
                self._fetch_code()
            else:
                self._confirm()
        elif state == "failed":
            self._fail(message)
        elif self.waited >= GIVE_UP_SECONDS:
            self._fail("No answer from the customer's phone. Send again, or take another payment method.")
        else:
            self.status.setText(message)
            QTimer.singleShot(POLL_SECONDS * 1000, self._poll)

    def _fetch_code(self):
        if self.isVisible() and self.stage == "code":
            self.future = _pool.submit(mpesa.fetch_result, self.settings, self.checkout_id)

    def _confirm(self):
        """Paid: show what was received so the cashier can check it against the till's SMS."""
        self.timer.stop()
        self.stage = "paid"
        lines = [f"<b style='font-size:16px;color:{theme.SUCCESS}'>Payment received</b>",
                 f"from 0{self.phone[3:6]}***{self.phone[-3:]}"]
        if self.receipt_code:
            lines.append(f"M-Pesa code: <b style='font-family:\"{theme.FONT_MONO}\"'>{self.receipt_code}</b>")
        self.status.setText("<br>".join(lines))
        self.print_btn.show()
        self.no_print_btn.show()
        self.print_btn.setDefault(True)
        self.print_btn.setFocus()

    def _finish(self, print_receipt: bool):
        self.print_receipt = print_receipt
        self.accept()

    def _poll(self):
        if self.isVisible() and self.checkout_id and self.stage == "wait":
            self.waited += POLL_SECONDS
            self.future = _pool.submit(mpesa.query, self.settings, self.checkout_id)

    def check_now(self):
        """Manual check: works while waiting and after a failure or timeout."""
        if not self.checkout_id or (self.future and not self.future.done()):
            return
        self.status.setText("Checking with Safaricom…")
        self.retry_btn.hide()
        self.stage = "wait"
        self.waited = min(self.waited, GIVE_UP_SECONDS - POLL_SECONDS)  # allow one more automatic round
        self.future = _pool.submit(mpesa.query, self.settings, self.checkout_id)
        self.timer.start()

    def _fail(self, message: str):
        self.timer.stop()
        self.future = None
        self.stage = "failed"
        self._set("warning-circle", theme.DANGER, message)
        self.retry_btn.show()
        self.check_btn.setVisible(self.checkout_id is not None)

    def reject(self):
        self.timer.stop()
        self.stage = "closed"
        super().reject()
