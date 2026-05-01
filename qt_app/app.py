from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app_config import load_config
from qt_app.main_window import MainWindow
from qt_app.theme import build_app_stylesheet


def main() -> int:
    config = load_config()
    app = QApplication(sys.argv)
    app.setApplicationName(config["ui"]["app_name"])
    app.setOrganizationName("Polizia Locale")
    app.setStyleSheet(build_app_stylesheet(config))

    window = MainWindow(config)
    window.show()
    return app.exec()
