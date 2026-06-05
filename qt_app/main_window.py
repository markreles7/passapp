from __future__ import annotations

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QMessageBox, QStackedWidget, QWidget

from core.auth import ADMIN_USERNAME, ROLE_ADMIN, AuthenticatedUser
from qt_app.accertamenti_anagrafici import AccertamentiAnagraficiPage
from qt_app.configuration import ConfigurationPage
from qt_app.contacts import ContactsPage
from qt_app.dashboard import DashboardPage
from qt_app.ospitalita import OspitalitaPage
from qt_app.pass_invalidi import PassInvalidiPage
from qt_app.report import ReportPage
from qt_app.segnalazioni import SegnalazioniPage
from qt_app.sidebar import Sidebar
from qt_app.updater import UpdateCheckWorker, start_update_and_restart
from qt_app.sopralluoghi import SopralluoghiPage
from qt_app.widgets import PlaceholderPage


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: dict,
        current_user: AuthenticatedUser | None = None,
        authentication_enabled: bool = False,
    ):
        super().__init__()
        self.config = config
        self.authentication_enabled = authentication_enabled
        self.current_user = current_user or (
            AuthenticatedUser(ADMIN_USERNAME, ROLE_ADMIN) if authentication_enabled else None
        )
        self._update_thread: QThread | None = None
        self._update_worker: UpdateCheckWorker | None = None
        window = config["ui"]["window"]
        self.setWindowTitle(config["ui"]["main_title"])
        self.resize(window["width"], window["height"])
        self.setMinimumSize(window["min_width"], window["min_height"])

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.sidebar = Sidebar(self.current_user, authentication_enabled=self.authentication_enabled)
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
        self._add_page("accertamenti_anagrafici", AccertamentiAnagraficiPage(config))
        self._add_page("ospitalita", OspitalitaPage(config))
        self._add_page("report", ReportPage(config))
        self._add_page("contatti", ContactsPage(config))
        if self._can_access_admin_pages():
            self._add_page(
                "configurazione",
                ConfigurationPage(
                    config,
                    current_user=self.current_user,
                    authentication_enabled=self.authentication_enabled,
                ),
            )
            self._add_placeholder("diagnostica", "Diagnostica", "Pagina Qt minima per la verifica della configurazione.")
        self._add_placeholder("audit", "Storico modifiche", "Pagina Qt minima per consultazione audit.")

        self.sidebar.selected.connect(self.show_page)
        self.show_page("dashboard")
        QTimer.singleShot(1200, self.check_for_updates)

    def _add_page(self, key: str, page: QWidget) -> None:
        self.pages[key] = page
        self.stack.addWidget(page)

    def _add_placeholder(self, key: str, title: str, subtitle: str) -> None:
        self._add_page(key, PlaceholderPage(title, subtitle))

    def show_page(self, key: str) -> None:
        if key in {"configurazione", "diagnostica"} and not self._can_access_admin_pages():
            QMessageBox.warning(
                self,
                "Accesso riservato",
                "Solo l'amministratore puo aprire o verificare la configurazione.",
            )
            return
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(key)

    def _can_access_admin_pages(self) -> bool:
        return not self.authentication_enabled or bool(self.current_user and self.current_user.is_admin)

    def check_for_updates(self) -> None:
        if self._update_thread is not None:
            return

        thread = QThread(self)
        worker = UpdateCheckWorker()
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._handle_update_info)
        worker.failed.connect(self._handle_update_check_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(lambda _info: worker.deleteLater())
        worker.failed.connect(lambda _message: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_update_check)

        self._update_thread = thread
        self._update_worker = worker
        thread.start()

    def _handle_update_info(self, info) -> None:
        if not info.available:
            return

        if not info.can_apply:
            QMessageBox.warning(self, "Aggiornamento disponibile", info.message)
            return

        detail = (
            f"{info.message}\n\n"
            f"Sorgente: {info.upstream}\n"
            "Se accetti, l'app si chiude, aggiorna i file, ricrea l'EXE e si riavvia."
        )
        choice = QMessageBox.question(
            self,
            "Aggiornamento disponibile",
            detail,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if choice != QMessageBox.Yes:
            return

        try:
            start_update_and_restart()
        except OSError as exc:
            QMessageBox.critical(self, "Aggiornamento non avviato", str(exc))
            return

        app = QApplication.instance()
        if app is not None:
            app.quit()

    def _handle_update_check_error(self, _message: str) -> None:
        return

    def _clear_update_check(self) -> None:
        self._update_thread = None
        self._update_worker = None

    def open_sopralluoghi_for_segnalazione(self, segnalazione_id: int, create_new: bool, luogo: str) -> None:
        page = self.pages.get("sopralluoghi")
        if page is None:
            return
        if hasattr(page, "open_for_segnalazione"):
            page.open_for_segnalazione(segnalazione_id, create_new=create_new, luogo=luogo)
        self.show_page("sopralluoghi")
