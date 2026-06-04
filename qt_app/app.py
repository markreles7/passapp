from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app_config import load_config
from qt_app.login import LoginDialog
from qt_app.main_window import MainWindow
from qt_app.theme import build_app_stylesheet


def main() -> int:
    config = load_config()
    app = QApplication(sys.argv)
    app.setApplicationName(config["ui"]["app_name"])
    app.setOrganizationName("Polizia Locale")
    app.setStyleSheet(build_app_stylesheet(config))

    login = LoginDialog()
    if login.exec() != LoginDialog.Accepted or login.user is None:
        return 0

    window = MainWindow(config, current_user=login.user)
    window.show()
    return app.exec()
