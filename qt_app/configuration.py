from __future__ import annotations

import json

from PySide6.QtCore import QThread, Qt
from services.ai.chatgpt_auth import ChatGPTAuth
from services.ai.exceptions import AIServiceError
from qt_app.workers import ChatGPTSignInWorker
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_config import CONFIG_PATH, load_config, save_config
from core.auth import ADMIN_USERNAME, ROLE_ADMIN, AuthError, AuthenticatedUser, create_user, list_users
from core.diagnostics import ERROR, OK, WARNING, run_diagnostics
from qt_app.workers import ChatGPTHealthWorker
from qt_app.widgets import page_header


CONFIG_FIELDS = (
    ("paths.pass_invalidi_network_folder", "Cartella Pass Invalidi", "dir"),
    ("paths.pass_invalidi_pattern", "Pattern file Pass Invalidi", "text"),
    ("paths.pass_invalidi_docs_folder", "Cartella documenti Pass Invalidi", "dir"),
    ("paths.pass_invalidi_authorization_template", "Modello autorizzazione Pass", "file"),
    ("paths.accertamenti_anagrafici_file", "Archivio Accertamenti Anagrafici", "file"),
    ("paths.accertamenti_anagrafici_excel", "Excel iniziale Accertamenti Anagrafici", "file"),
    ("paths.ospitalita_network_folder", "Cartella Ospitalita Stranieri", "dir"),
    ("paths.ospitalita_patterns", "Pattern file Ospitalita", "text"),
    ("paths.segnalazioni_file", "File segnalazioni JSON", "file"),
    ("paths.documents_dir", "Cartella documenti", "dir"),
    ("paths.segnalazioni_pdf_dir", "Cartella PDF segnalazioni", "dir"),
    ("paths.fascicoli_segnalazioni_dir", "Cartella fascicoli segnalazioni", "dir"),
    ("paths.report_mensili_dir", "Cartella report mensili", "dir"),
    ("paths.logo_path", "Logo applicazione", "file"),
    ("ai.model", "Modello ChatGPT", "text"),
    ("ai.timeout", "Timeout (secondi)", "text"),
    ("ai.documents_enabled", "Bozze documenti con ChatGPT (true/false)", "text"),
)


class ConfigurationPage(QWidget):
    def __init__(
        self,
        config: dict,
        current_user: AuthenticatedUser | None = None,
        authentication_enabled: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.config = config
        self.authentication_enabled = authentication_enabled
        self.current_user = current_user or (
            AuthenticatedUser(ADMIN_USERNAME, ROLE_ADMIN) if authentication_enabled else None
        )
        self.fields: dict[str, QLineEdit | QComboBox] = {}
        self._health_thread: QThread | None = None
        self._health_worker: ChatGPTHealthWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(
            page_header(
                "Configurazione",
                "Imposta i percorsi usati dai moduli operativi e verifica l'ambiente locale.",
            )
        )

        form_card = QFrame()
        form_card.setObjectName("Card")
        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(18, 18, 18, 18)
        form_card_layout.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        grid = QGridLayout(scroll_content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(9)
        grid.setColumnStretch(1, 1)

        current_config = load_config(force_reload=True)
        for row, (key, label, browse_type) in enumerate(CONFIG_FIELDS):
            self._add_field_row(grid, row, key, label, browse_type, current_config)

        scroll.setWidget(scroll_content)
        form_card_layout.addWidget(scroll)

        self.account_status = QLabel("")
        self.account_status.setWordWrap(True)
        form_card_layout.addWidget(self.account_status)
        account_row = QHBoxLayout()
        self.sign_in_button = QPushButton("Continue with ChatGPT")
        self.sign_in_button.clicked.connect(self.sign_in_chatgpt)
        self.disconnect_button = QPushButton("Scollega ChatGPT")
        self.disconnect_button.clicked.connect(self.disconnect_chatgpt)
        usage_button = QPushButton("Gestisci utilizzo")
        usage_button.clicked.connect(self.manage_chatgpt_usage)
        for button in (self.sign_in_button, self.disconnect_button, usage_button):
            account_row.addWidget(button)
        form_card_layout.addLayout(account_row)
        self._refresh_chatgpt_account()
        self.status = QLabel("")
        self.status.setObjectName("Muted")
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        self.test_chatgpt_button = QPushButton("Verifica connessione ChatGPT")
        self.test_chatgpt_button.setProperty("secondary", "true")
        self.test_chatgpt_button.setEnabled(self._can_manage_configuration())
        self.test_chatgpt_button.clicked.connect(self.test_chatgpt)
        save_button = QPushButton("Salva configurazione")
        save_button.setEnabled(self._can_manage_configuration())
        save_button.clicked.connect(self.save)
        self._set_chatgpt_busy(False)
        buttons_row.addWidget(self.test_chatgpt_button)
        buttons_row.addWidget(save_button)
        form_card_layout.addLayout(buttons_row)
        form_card_layout.addWidget(self.status)
        layout.addWidget(form_card, 3)

        diagnostics_card = QFrame()
        diagnostics_card.setObjectName("Card")
        diagnostics_layout = QVBoxLayout(diagnostics_card)
        diagnostics_layout.setContentsMargins(18, 18, 18, 18)
        diagnostics_layout.setSpacing(12)

        diagnostics_button = QPushButton("Esegui verifica")
        diagnostics_button.setEnabled(self._can_manage_configuration())
        diagnostics_button.clicked.connect(self.refresh_diagnostics)
        diagnostics_layout.addWidget(diagnostics_button, alignment=Qt.AlignRight)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Esito", "Controllo", "Dettaglio"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        diagnostics_layout.addWidget(self.table)
        layout.addWidget(diagnostics_card, 2)

        if self.authentication_enabled and self._can_manage_configuration():
            self._add_user_management_section(layout)

        config_path = QLabel(f"File configurazione: {CONFIG_PATH}")
        config_path.setObjectName("Muted")
        layout.addWidget(config_path)

    def _add_field_row(
        self,
        grid: QGridLayout,
        row: int,
        key: str,
        label: str,
        browse_type: str,
        config: dict,
    ) -> None:
        label_widget = QLabel(label)
        label_widget.setObjectName("Muted")
        if key == "ai.model":
            field = QComboBox()
            field.addItem("Automatico dal tuo account", "")
            current = self._get_value(config, key)
            if current:
                field.addItem(current, current)
                field.setCurrentIndex(1)
        else:
            field = QLineEdit(self._get_value(config, key))
        self.fields[key] = field

        grid.addWidget(label_widget, row, 0)
        grid.addWidget(field, row, 1)
        if browse_type in {"dir", "file"}:
            button = QPushButton("Sfoglia")
            button.setProperty("secondary", "true")
            button.clicked.connect(lambda _checked=False, line_edit=field, mode=browse_type: self._browse(line_edit, mode))
            grid.addWidget(button, row, 2)
        else:
            grid.addWidget(QLabel(""), row, 2)

    def _browse(self, field: QLineEdit, browse_type: str) -> None:
        if browse_type == "dir":
            selected = QFileDialog.getExistingDirectory(self, "Seleziona cartella", field.text())
        else:
            selected, _filter = QFileDialog.getOpenFileName(self, "Seleziona file", field.text())
        if selected:
            field.setText(selected)

    def save(self) -> None:
        if not self._can_manage_configuration():
            QMessageBox.warning(self, "Accesso riservato", "Solo l'amministratore puo modificare la configurazione.")
            return

        try:
            raw_config = self._config_from_fields(self._load_raw_config())
        except ValueError as exc:
            QMessageBox.warning(self, "Configurazione non valida", str(exc))
            return

        try:
            save_config(raw_config)
        except OSError as exc:
            QMessageBox.critical(self, "Configurazione non salvata", f"Impossibile salvare il file.\n\n{exc}")
            return

        self.config = load_config(force_reload=True)
        self.status.setText("Configurazione salvata. Riavvia PassApp per ricaricare tutti i moduli gia importati.")
        QMessageBox.information(self, "Configurazione salvata", "I percorsi sono stati salvati correttamente.")

    def test_chatgpt(self) -> None:
        if not self._can_manage_configuration():
            QMessageBox.warning(self, "Accesso riservato", "Solo l'amministratore puo verificare ChatGPT.")
            return

        if self._health_thread is not None:
            return
        try:
            config = self._config_from_fields(self._load_raw_config())
        except ValueError as exc:
            QMessageBox.warning(self, "Configurazione non valida", str(exc))
            return
        ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
        self.status.setText("Verifica ChatGPT in corso...")
        self._set_chatgpt_busy(True)
        thread = QThread(self)
        worker = ChatGPTHealthWorker(ai_config)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._health_ready)
        worker.failed.connect(self._health_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(lambda _result: worker.deleteLater())
        worker.failed.connect(lambda _message: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._health_finished)
        self._health_thread = thread
        self._health_worker = worker
        thread.start()

    def _health_ready(self, result) -> None:
        self._refresh_chatgpt_account()
        field = self.fields["ai.model"]
        selected = field.currentData()
        field.clear()
        field.addItem("Automatico dal tuo account", "")
        for slug, label in result.models:
            field.addItem(label, slug)
        index = field.findData(selected)
        if index >= 0:
            field.setCurrentIndex(index)
        if result.available and result.model_available:
            detail = f"{result.message}\n\nModello: {result.configured_model}"
            self.status.setText("ChatGPT connesso.")
            QMessageBox.information(self, "ChatGPT connesso", detail)
            return
        detail = f"{result.message}\n\nModello: {result.configured_model}"
        self.status.setText("ChatGPT non disponibile.")
        QMessageBox.warning(self, "ChatGPT non disponibile", detail)

    def _health_failed(self, detail: str) -> None:
        self.status.setText("ChatGPT non disponibile.")
        QMessageBox.warning(self, "ChatGPT non disponibile", detail)

    def _health_finished(self) -> None:
        self._health_thread = None
        self._health_worker = None
        self._set_chatgpt_busy(False)

    def _set_chatgpt_busy(self, busy):
        allowed = self._can_manage_configuration() and not busy
        for button in (self.sign_in_button, self.disconnect_button, self.test_chatgpt_button):
            button.setEnabled(allowed)

    def _refresh_chatgpt_account(self):
        try:
            state = ChatGPTAuth().summary()
            if state["connected"]:
                permission = "Uso del piano autorizzato." if state["sharing"] else "Uso del piano da autorizzare."
                text = f"ChatGPT: {state['email']} ? {permission}"
            else:
                text = "ChatGPT non collegato. Accedi e autorizza l'uso del tuo piano Plus o Pro."
        except AIServiceError as exc:
            text = str(exc)
        self.account_status.setText(text + "\nLe richieste inviano i dati selezionati a OpenAI e consumano i limiti del piano. Le bozze richiedono revisione.")

    def sign_in_chatgpt(self):
        if not self._can_manage_configuration() or self._health_thread is not None:
            return
        self._set_chatgpt_busy(True)
        self.status.setText("Completa l'accesso e autorizza PassApp nel browser. Attesa massima: 5 minuti.")
        thread = QThread(self)
        worker = ChatGPTSignInWorker()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._sign_in_ready)
        worker.failed.connect(self._health_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._health_finished)
        thread.finished.connect(thread.deleteLater)
        self._health_thread, self._health_worker = thread, worker
        thread.start()

    def _sign_in_ready(self, _state):
        self._refresh_chatgpt_account()
        self.status.setText("Accesso completato. Usa Verifica connessione ChatGPT per caricare i modelli.")

    def disconnect_chatgpt(self):
        if not self._can_manage_configuration() or self._health_thread is not None:
            return
        try:
            ChatGPTAuth().disconnect()
            self._refresh_chatgpt_account()
            self.status.setText("Credenziali locali eliminate. Per revocare l'accesso apri le impostazioni ChatGPT.")
            field = self.fields["ai.model"]
            field.clear()
            field.addItem("Automatico dal tuo account", "")
        except AIServiceError as exc:
            self._health_failed(str(exc))

    @staticmethod
    def manage_chatgpt_usage():
        import webbrowser
        webbrowser.open("https://chatgpt.com/settings/usage")

    def refresh_diagnostics(self) -> None:
        if not self._can_manage_configuration():
            QMessageBox.warning(self, "Accesso riservato", "Solo l'amministratore puo verificare la configurazione.")
            return

        self.table.setRowCount(0)
        for item in run_diagnostics():
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate((item.status, item.name, item.detail)):
                table_item = QTableWidgetItem(value)
                table_item.setForeground(self._status_color(item.status))
                self.table.setItem(row, column, table_item)
        self.status.setText("Verifica configurazione completata.")

    @staticmethod
    def _load_raw_config() -> dict:
        if not CONFIG_PATH.exists():
            return {}
        try:
            payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _config_from_fields(self, raw_config: dict) -> dict:
        raw_config.setdefault("paths", {})
        raw_config["ai"] = dict(load_config(force_reload=True).get("ai", {}))
        raw_config["ai"]["provider"] = "chatgpt"
        for key, field in self.fields.items():
            section, name = key.split(".", 1)
            value = field.currentData() if isinstance(field, QComboBox) else field.text().strip()
            if name == "timeout" and not 1 <= int(value) <= 600:
                raise ValueError("Il timeout deve essere compreso tra 1 e 600 secondi.")
            if name == "ospitalita_patterns":
                raw_config.setdefault(section, {})[name] = [item.strip() for item in value.split(";") if item.strip()]
            elif section == "ai":
                if name in {"timeout", "max_tokens"}:
                    raw_config.setdefault(section, {})[name] = int(value)
                elif name == "temperature":
                    raw_config.setdefault(section, {})[name] = float(value)
                elif name in {"stream", "allow_lan", "documents_enabled"}:
                    raw_config.setdefault(section, {})[name] = value.lower() in {"1", "true", "yes", "si", "on"}
                else:
                    raw_config.setdefault(section, {})[name] = value
            elif value:
                raw_config.setdefault(section, {})[name] = value
        return raw_config

    @staticmethod
    def _get_value(config: dict, key: str) -> str:
        section, name = key.split(".", 1)
        value = config.get(section, {}).get(name, "")
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value)

    def _can_manage_configuration(self) -> bool:
        return not self.authentication_enabled or bool(self.current_user and self.current_user.is_admin)

    def _add_user_management_section(self, layout: QVBoxLayout) -> None:
        users_card = QFrame()
        users_card.setObjectName("Card")
        users_layout = QVBoxLayout(users_card)
        users_layout.setContentsMargins(18, 18, 18, 18)
        users_layout.setSpacing(12)

        title = QLabel("Profili utente")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        users_layout.addWidget(title)

        form_row = QHBoxLayout()
        self.new_username_field = QLineEdit()
        self.new_username_field.setPlaceholderText("Nuovo username")
        self.new_password_field = QLineEdit()
        self.new_password_field.setPlaceholderText("Password")
        self.new_password_field.setEchoMode(QLineEdit.Password)
        create_button = QPushButton("Crea profilo")
        create_button.clicked.connect(self.create_profile)
        form_row.addWidget(self.new_username_field, 1)
        form_row.addWidget(self.new_password_field, 1)
        form_row.addWidget(create_button)
        users_layout.addLayout(form_row)

        self.users_table = QTableWidget(0, 3)
        self.users_table.setHorizontalHeaderLabels(("Username", "Ruolo", "Creato il"))
        self.users_table.verticalHeader().setVisible(False)
        self.users_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.users_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        users_layout.addWidget(self.users_table)
        layout.addWidget(users_card, 2)
        self.refresh_users()

    def create_profile(self) -> None:
        try:
            create_user(
                self.new_username_field.text(),
                self.new_password_field.text(),
                created_by=self.current_user,
            )
        except AuthError as exc:
            QMessageBox.warning(self, "Profilo non creato", str(exc))
            return

        self.new_username_field.clear()
        self.new_password_field.clear()
        self.refresh_users()
        QMessageBox.information(self, "Profilo creato", "Il nuovo profilo utente e stato creato correttamente.")

    def refresh_users(self) -> None:
        self.users_table.setRowCount(0)
        for user in list_users():
            row = self.users_table.rowCount()
            self.users_table.insertRow(row)
            role = "Amministratore" if user["role"] == ROLE_ADMIN else "Utente"
            created_at = user.get("created_at", "")
            created_at = created_at[:19].replace("T", " ") if created_at else ""
            for column, value in enumerate((user["username"], role, created_at)):
                self.users_table.setItem(row, column, QTableWidgetItem(value))

    @staticmethod
    def _status_color(status: str):
        from PySide6.QtGui import QColor

        if status == OK:
            return QColor("#1E9E6B")
        if status == WARNING:
            return QColor("#C97A10")
        if status == ERROR:
            return QColor("#C0392B")
        return QColor("#6B6560")
