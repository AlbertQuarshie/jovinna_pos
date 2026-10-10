import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app import config
from app.db.database import init_db
from app.services.auth_service import has_users
from app.ui import theme
from app.ui.login_dialog import FirstAdminDialog, LoginDialog
from app.ui.main_window import MainWindow


class App:
    """Login -> main window -> (log out) -> login again, until the window is closed."""

    def __init__(self):
        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName(config.SHOP_NAME)
        self.qt.setQuitOnLastWindowClosed(False)  # logging out closes the window, not the app
        theme.apply(self.qt)
        self.window: MainWindow | None = None

    def run(self) -> int:
        if not has_users() and not FirstAdminDialog().exec():
            return 0
        if not self.show_login():
            return 0
        return self.qt.exec()

    def show_login(self) -> bool:
        dialog = LoginDialog()
        if not dialog.exec():
            self.qt.quit()
            return False
        self.window = MainWindow(dialog.user)
        self.window.logged_out.connect(lambda: QTimer.singleShot(0, self.show_login))
        self.window.show()
        return True


def main():
    init_db()
    sys.exit(App().run())


if __name__ == "__main__":
    main()
