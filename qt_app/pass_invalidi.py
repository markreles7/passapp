from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.dates import format_date, giorni_rimanenti
from pass_invalidi import CARTELLA_RETE, get_status
from qt_app.widgets import page_header
from qt_app.workers import PassInvalidiLoadWorker


FILTERS = (
    ("tutti", "Tutti"),
    ("valid", "Validi"),
    ("soon", "In scadenza"),
    ("expired", "Scaduti"),
)


class PassInvalidiPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.records: list[dict] = []
        self.filtered: list[dict] = []
        self.files: list[str] = []
        self.thread: QThread | None = None
        self.worker: PassInvalidiLoadWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header("Pass Invalidi", "Registro pass, filtri scadenze e consultazione dettagli."))

        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls = QVBoxLayout(controls_card)
        controls.setContentsMargins(16, 16, 16, 16)
        controls.setSpacing(12)

        top = QHBoxLayout()
        self.refresh_button = QPushButton("Aggiorna")
        self.refresh_button.clicked.connect(self.refresh)
        open_folder = QPushButton("Apri cartella")
        open_folder.setProperty("secondary", "true")
        open_folder.clicked.connect(self.open_folder)
        top.addWidget(self.refresh_button)
        top.addWidget(open_folder)
        top.addStretch(1)
        controls.addLayout(top)

        filters = QGridLayout()
        filters.setHorizontalSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca nominativo")
        self.search.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search, 0, 0, 1, 2)

        self.year_filter = QComboBox()
        self.year_filter.addItem("Tutti")
        self.year_filter.currentTextChanged.connect(self.apply_filters)
        filters.addWidget(QLabel("Anno"), 0, 2)
        filters.addWidget(self.year_filter, 0, 3)

        self.status_filter = QComboBox()
        self.status_filter.addItems([label for _key, label in FILTERS])
        self.status_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(QLabel("Stato"), 0, 4)
        filters.addWidget(self.status_filter, 0, 5)
        filters.setColumnStretch(1, 1)
        controls.addLayout(filters)

        stats = QHBoxLayout()
        self.total_label = QLabel("Totale: 0")
        self.file_label = QLabel("File: 0")
        self.expired_label = QLabel("Scaduti: 0")
        self.soon_label = QLabel("In scad.: 0")
        for label in (self.total_label, self.file_label, self.expired_label, self.soon_label):
            label.setObjectName("Badge")
            label.setStyleSheet("background: #DBEAFE; color: #2D6BE4;")
            stats.addWidget(label)
        stats.addStretch(1)
        controls.addLayout(stats)
        layout.addWidget(controls_card)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(("N.", "Cognome e Nome", "Indirizzo", "Rilascio", "Scadenza", "Stato", "Note", "File"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.doubleClicked.connect(lambda _index: self.show_detail())
        layout.addWidget(self.table, 1)

        self.status = QLabel("Premi Aggiorna per caricare i registri configurati.")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

    def refresh(self) -> None:
        if self.thread is not None:
            return
        self.refresh_button.setEnabled(False)
        self.refresh_button.setText("Caricamento...")
        self.status.setText(f"Lettura da {CARTELLA_RETE} ...")
        self.table.setRowCount(0)

        self.thread = QThread(self)
        self.worker = PassInvalidiLoadWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._load_done)
        self.worker.failed.connect(self._load_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def _load_done(self, records, files, errors) -> None:
        self.records = list(records)
        self.files = list(files)
        self._refresh_years()
        self._refresh_stats()
        self.apply_filters()
        if errors:
            QMessageBox.warning(self, "Errori di lettura", "Alcuni file non sono stati letti correttamente:\n\n" + "\n".join(errors))
        self.status.setText(f"Caricati {len(self.files)} file e {len(self.records)} pass.")

    def _load_failed(self, detail: str) -> None:
        self.status.setText(f"Errore caricamento: {detail}")
        QMessageBox.critical(self, "Caricamento non riuscito", detail)

    def _thread_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.refresh_button.setText("Aggiorna")
        self.thread = None
        self.worker = None

    def _refresh_years(self) -> None:
        years = sorted({self._record_year(record) for record in self.records if self._record_year(record)}, reverse=True)
        current = self.year_filter.currentText()
        self.year_filter.blockSignals(True)
        self.year_filter.clear()
        self.year_filter.addItems(["Tutti"] + years)
        index = self.year_filter.findText(current)
        self.year_filter.setCurrentIndex(index if index >= 0 else 0)
        self.year_filter.blockSignals(False)

    def _refresh_stats(self) -> None:
        records = [record for record in self.records if not record.get("_deleted")]
        expired = sum(1 for record in records if get_status(record.get("scadenza")) == "expired")
        soon = sum(1 for record in records if get_status(record.get("scadenza")) == "soon")
        self.total_label.setText(f"Totale: {len(records)}")
        self.file_label.setText(f"File: {len(self.files)}")
        self.expired_label.setText(f"Scaduti: {expired}")
        self.soon_label.setText(f"In scad.: {soon}")

    def apply_filters(self) -> None:
        query_parts = self.search.text().strip().lower().split()
        selected_year = self.year_filter.currentText()
        filter_key = FILTERS[self.status_filter.currentIndex()][0]
        out = []
        for record in self.records:
            if record.get("_deleted"):
                continue
            if selected_year != "Tutti" and self._record_year(record) != selected_year:
                continue
            name = str(record.get("nome", "")).lower()
            if query_parts and not all(part in name for part in query_parts):
                continue
            status = get_status(record.get("scadenza"))
            if filter_key != "tutti" and status != filter_key:
                continue
            out.append(record)
        self.filtered = out
        self.populate_table(out)
        self.status.setText(f"Risultati visualizzati: {len(out)}")

    def populate_table(self, records: list[dict]) -> None:
        self.table.setRowCount(0)
        for record in records:
            row = self.table.rowCount()
            self.table.insertRow(row)
            status_key = get_status(record.get("scadenza"))
            values = (
                str(record.get("numero", "")),
                str(record.get("nome", "")),
                str(record.get("indirizzo") or "-"),
                format_date(record.get("rilascio")),
                format_date(record.get("scadenza")),
                self._status_label(record),
                str(record.get("note") or "-"),
                str(record.get("source") or ""),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, row)
                if status_key == "expired":
                    item.setForeground(Qt.red)
                elif status_key == "soon":
                    item.setForeground(Qt.darkYellow)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def show_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered):
            return
        record = self.filtered[row]
        detail = "\n".join(
            (
                f"Numero: {record.get('numero', '')}",
                f"Nominativo: {record.get('nome', '')}",
                f"Indirizzo: {record.get('indirizzo') or '-'}",
                f"Rilascio: {format_date(record.get('rilascio'))}",
                f"Scadenza: {format_date(record.get('scadenza'))}",
                f"Stato: {self._status_label(record)}",
                f"Note: {record.get('note') or '-'}",
                f"File: {record.get('source') or '-'}",
            )
        )
        QMessageBox.information(self, "Dettaglio pass", detail)

    def open_folder(self) -> None:
        if os.path.isdir(CARTELLA_RETE):
            subprocess.Popen(f'explorer "{CARTELLA_RETE}"')
            return
        QMessageBox.warning(self, "Cartella non trovata", f"Impossibile aprire:\n{CARTELLA_RETE}")

    @staticmethod
    def _record_year(record: dict) -> str:
        import re

        source = str(record.get("source", ""))
        years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", source)]
        return str(max(years)) if years else ""

    @staticmethod
    def _status_label(record: dict) -> str:
        status = get_status(record.get("scadenza"))
        days = giorni_rimanenti(record.get("scadenza"))
        if status == "expired":
            return f"Scaduto ({abs(days)}gg fa)" if days is not None else "Scaduto"
        if status == "soon":
            return f"Scade in {days}gg" if days is not None else "In scadenza"
        if status == "valid":
            return "Valido"
        return "-"
