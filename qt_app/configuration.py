from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
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
from core.diagnostics import ERROR, OK, WARNING, run_diagnostics
from qt_app.widgets import page_header


CONFIG_FIELDS = (
    ("paths.pass_invalidi_network_folder", "Cartella Pass Invalidi", "dir"),
    ("paths.pass_invalidi_pattern", "Pattern file Pass Invalidi", "text"),
    ("paths.pass_invalidi_docs_folder", "Cartella documenti Pass Invalidi", "dir"),
    ("paths.pass_invalidi_authorization_template", "Modello autorizzazione Pass", "file"),
    ("paths.ospitalita_network_folder", "Cartella Ospitalita Stranieri", "dir"),
    ("paths.ospitalita_patterns", "Pattern file Ospitalita", "text"),
    ("paths.segnalazioni_file", "File segnalazioni JSON", "file"),
    ("paths.documents_dir", "Cartella documenti", "dir"),
    ("paths.segnalazioni_pdf_dir", "Cartella PDF segnalazioni", "dir"),
    ("paths.fascicoli_segnalazioni_dir", "Cartella fascicoli segnalazioni", "dir"),
    ("paths.report_mensili_dir", "Cartella report mensili", "dir"),
    ("paths.logo_path", "Logo applicazione", "file"),
)


class ConfigurationPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.fields: dict[str, QLineEdit] = {}

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

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        save_button = QPushButton("Salva configurazione")
        save_button.clicked.connect(self.save)
        form_card_layout.addWidget(save_button, alignment=Qt.AlignRight)
        form_card_layout.addWidget(self.status)
        layout.addWidget(form_card, 3)

        diagnostics_card = QFrame()
        diagnostics_card.setObjectName("Card")
        diagnostics_layout = QVBoxLayout(diagnostics_card)
        diagnostics_layout.setContentsMargins(18, 18, 18, 18)
        diagnostics_layout.setSpacing(12)

        diagnostics_button = QPushButton("Esegui verifica")
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
        raw_config = self._load_raw_config()
        raw_config.setdefault("paths", {})

        for key, field in self.fields.items():
            section, name = key.split(".", 1)
            value = field.text().strip()
            if name == "ospitalita_patterns":
                raw_config.setdefault(section, {})[name] = [item.strip() for item in value.split(";") if item.strip()]
            elif value:
                raw_config.setdefault(section, {})[name] = value

        try:
            save_config(raw_config)
        except OSError as exc:
            QMessageBox.critical(self, "Configurazione non salvata", f"Impossibile salvare il file.\n\n{exc}")
            return

        self.config = load_config(force_reload=True)
        self.status.setText("Configurazione salvata. Riavvia PassApp per ricaricare tutti i moduli gia importati.")
        QMessageBox.information(self, "Configurazione salvata", "I percorsi sono stati salvati correttamente.")

    def refresh_diagnostics(self) -> None:
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

    @staticmethod
    def _get_value(config: dict, key: str) -> str:
        section, name = key.split(".", 1)
        value = config.get(section, {}).get(name, "")
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value)

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
