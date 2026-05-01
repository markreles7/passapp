from __future__ import annotations

import os
import re

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

from ospitalita_stranieri import FOLDER_OSPITALITA
from qt_app.widgets import page_header
from qt_app.workers import OspitalitaLoadWorker


class OspitalitaPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.records: list[dict] = []
        self.filtered: list[dict] = []
        self.files: list[str] = []
        self.insights: list[str] = []
        self.thread: QThread | None = None
        self.worker: OspitalitaLoadWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header("Ospitalita Stranieri", "Comunicazioni ospitalita, ricerca e consultazione registri."))

        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls = QVBoxLayout(controls_card)
        controls.setContentsMargins(16, 16, 16, 16)
        controls.setSpacing(12)

        top = QHBoxLayout()
        self.refresh_button = QPushButton("Aggiorna")
        self.refresh_button.clicked.connect(self.refresh)
        top.addWidget(self.refresh_button)
        top.addStretch(1)
        controls.addLayout(top)

        filters = QGridLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca progressivo, protocollo, nominativo, indirizzo o data")
        self.search.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search, 0, 0, 1, 3)
        filters.addWidget(QLabel("Anno"), 0, 3)
        self.year_filter = QComboBox()
        self.year_filter.addItem("Tutti")
        self.year_filter.currentTextChanged.connect(self.apply_filters)
        filters.addWidget(self.year_filter, 0, 4)
        filters.setColumnStretch(2, 1)
        controls.addLayout(filters)

        stats = QHBoxLayout()
        self.total_label = QLabel("Totale: 0")
        self.file_label = QLabel("File: 0")
        for label in (self.total_label, self.file_label):
            label.setObjectName("Badge")
            label.setStyleSheet("background: #DCFCE7; color: #1E9E6B;")
            stats.addWidget(label)
        stats.addStretch(1)
        controls.addLayout(stats)
        layout.addWidget(controls_card)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("N.", "Protocollo", "Denunciante", "Straniero", "Data", "Dettaglio", "File"))
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
        self.status.setText(f"Lettura da {FOLDER_OSPITALITA} ...")
        self.table.setRowCount(0)

        self.thread = QThread(self)
        self.worker = OspitalitaLoadWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._load_done)
        self.worker.failed.connect(self._load_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def _load_done(self, records, files, errors, insights) -> None:
        self.records = list(records)
        self.files = list(files)
        self.insights = list(insights)
        self._refresh_years()
        self.apply_filters()
        self.total_label.setText(f"Totale: {len(self.records)}")
        self.file_label.setText(f"File: {len(self.files)}")
        if errors:
            QMessageBox.warning(self, "Alcuni file non letti", "Sono presenti errori di importazione:\n\n" + "\n".join(errors[:10]))
        insight = self.insights[0] if self.insights else "Nessun mapping header disponibile."
        self.status.setText(f"Caricati {len(self.files)} file e {len(self.records)} record. {insight}")

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

    def apply_filters(self) -> None:
        query = self.search.text().strip().lower()
        selected_year = self.year_filter.currentText()
        out = []
        for record in self.records:
            if record.get("_deleted"):
                continue
            if selected_year != "Tutti" and self._record_year(record) != selected_year:
                continue
            searchable = " ".join(
                str(record.get(key, ""))
                for key in (
                    "progressivo",
                    "protocollo",
                    "data_presentazione",
                    "denunciante_dichiarante",
                    "cittadino_ospitato",
                    "indirizzo",
                    "tipo_comunicazione",
                )
            ).lower()
            if query and query not in searchable:
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
            values = (
                self._value(record.get("progressivo")),
                self._value(record.get("protocollo")),
                self._compact(record.get("denunciante_dichiarante")),
                self._compact(record.get("cittadino_ospitato")),
                self._value(record.get("data_presentazione")),
                self._compact(record.get("tipo_comunicazione"), record.get("indirizzo")),
                self._value(record.get("source")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, row)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def show_detail(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered):
            return
        record = self.filtered[row]
        lines = [
            f"Progressivo: {self._value(record.get('progressivo'))}",
            f"Protocollo: {self._value(record.get('protocollo'))}",
            f"Data presentazione: {self._value(record.get('data_presentazione'))}",
            f"Denunciante/dichiarante: {self._value(record.get('denunciante_dichiarante'))}",
            f"Cittadino ospitato: {self._value(record.get('cittadino_ospitato'))}",
            f"Indirizzo: {self._value(record.get('indirizzo'))}",
            f"Tipo comunicazione: {self._value(record.get('tipo_comunicazione'))}",
            f"File: {self._value(record.get('source'))}",
            f"Foglio: {self._value(record.get('sheet'))}",
        ]
        QMessageBox.information(self, "Dettaglio ospitalita", "\n".join(lines))

    @staticmethod
    def _record_year(record: dict) -> str:
        source = str(record.get("source", ""))
        years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", source)]
        return str(max(years)) if years else ""

    @staticmethod
    def _value(value) -> str:
        text = str(value or "").strip()
        return text if text else "-"

    @classmethod
    def _compact(cls, *values) -> str:
        parts = []
        for value in values:
            text = cls._value(value)
            if text != "-" and text not in parts:
                parts.append(text)
        return " | ".join(parts) if parts else "-"
