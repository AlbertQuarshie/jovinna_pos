import sys

from PySide6.QtCore import QLockFile, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app import config
from app.db.database import engine, init_db
from app.services.auth_service import has_users
from app.services.backup_service import daily_backup
from app.ui import theme
from app.ui.login_dialog import FirstAdminDialog, LoginDialog
from app.ui.main_window import MainWindow


def set_windows_app_id():
    """Without this, Windows groups the app under python.exe and shows Python's taskbar icon."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"{config.PUBLISHER}.{config.APP_ID}".replace(" ", ""))


class App:
    """Login -> main window -> (log out) -> login again, until the window is closed."""

    def __init__(self):
        set_windows_app_id()
        self.qt = QApplication(sys.argv)
        self.qt.setApplicationName(config.APP_NAME)
        self.qt.setApplicationVersion(config.APP_VERSION)
        self.qt.setOrganizationName(config.PUBLISHER)
        self.qt.setWindowIcon(QIcon(str(config.BASE_DIR / "assets" / "icon.ico")))
        self.qt.setQuitOnLastWindowClosed(False)  # logging out closes the window, not the app
        theme.apply(self.qt)
        self.window: MainWindow | None = None

    def start_services(self):
        # Automatic backups: on start, every hour while open, and on close
        daily_backup()
        self.backup_timer = QTimer(interval=config.BACKUP_EVERY_MINUTES * 60_000, timeout=daily_backup)
        self.backup_timer.start()
        self.qt.aboutToQuit.connect(self.on_quit)

    def on_quit(self):
        daily_backup()
        engine.dispose()  # close the database file cleanly

    def run(self) -> int:
        # Only one copy at a time, so two windows can't sell from the same stock at once
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(config.DATA_DIR / "app.lock"))
        if not self.lock.tryLock(100):
            QMessageBox.information(None, config.APP_NAME,
                                    f"{config.APP_NAME} is already open. Look for it on the taskbar.")
            return 0

        try:
            init_db()
        except RuntimeError as e:
            QMessageBox.critical(None, config.APP_NAME, str(e))
            return 1
        self.start_services()

        if not has_users() and not FirstAdminDialog().exec():
            self.on_quit()
            return 0
        if not self.show_login():
            self.on_quit()
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
    sys.exit(App().run())


if __name__ == "__main__":
    main()
