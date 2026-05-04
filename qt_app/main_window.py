from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from qt_app.configuration import ConfigurationPage
from qt_app.contacts import ContactsPage
from qt_app.dashboard import DashboardPage
from qt_app.ospitalita import OspitalitaPage
from qt_app.pass_invalidi import PassInvalidiPage
from qt_app.report import ReportPage
from qt_app.segnalazioni import SegnalazioniPage
from qt_app.sidebar import Sidebar
from qt_app.sopralluoghi import SopralluoghiPage
from qt_app.widgets import PlaceholderPage


class MainWindow(QMainWindow):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        window = config["ui"]["window"]
        self.setWindowTitle(config["ui"]["main_title"])
        self.resize(window["width"], window["height"])
        self.setMinimumSize(window["min_width"], window["min_height"])

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        root_layout.addWidget(self.sidebar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.pages: dict[str, QWidget] = {}
        self._add_page("dashboard", DashboardPage(config))
        self._add_page("pass_invalidi", PassInvalidiPage(config))
        segnalazioni_page = SegnalazioniPage(config)
        sopralluoghi_page = SopralluoghiPage(config)
        segnalazioni_page.request_sopralluoghi.connect(self.open_sopralluoghi_for_segnalazione)
        self._add_page("segnalazioni", segnalazioni_page)
        self._add_page("sopralluoghi", sopralluoghi_page)
        self._add_page("ospitalita", OspitalitaPage(config))
        self._add_page("report", ReportPage(config))
        self._add_page("contatti", ContactsPage(config))
        self._add_page("configurazione", ConfigurationPage(config))

        self.sidebar.selected.connect(self.show_page)
        self.show_page("dashboard")

    def _add_page(self, key: str, page: QWidget) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)

    def _add_placeholder(self, key: str, title: str, subtitle: str) -> None:
        self._add_page(key, PlaceholderPage(title, subtitle))

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(key)

    def open_sopralluoghi_for_segnalazione(self, segnalazione_id: int, create_new: bool, luogo: str) -> None:
        page = self.pages.get("sopralluoghi")
        if page is None:
            return
        if hasattr(page, "open_for_segnalazione"):
            page.open_for_segnalazione(segnalazione_id, create_new=create_new, luogo=luogo)
        self.show_page("sopralluoghi")
