from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.sopralluoghi import (
    STATI_SOPRALLUOGO,
    Sopralluogo,
    delete_sopralluogo,
    load_sopralluoghi,
    next_sopralluogo_id,
    now_timestamp,
    upsert_sopralluogo,
    validate_sopralluogo,
)
from qt_app.widgets import page_header


class SopralluoghiPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.items: list[Sopralluogo] = []
        self.editing_id: int | None = None
        self.fields: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header("Sopralluoghi", "Elenco e gestione dei sopralluoghi collegati alle segnalazioni."))

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_form_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        self.load_items()
        self.start_new()

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        refresh_button = QPushButton("Aggiorna")
        refresh_button.clicked.connect(self.load_items)
        toolbar.addWidget(refresh_button)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Stato"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(("Tutti",) + STATI_SOPRALLUOGO)
        self.filter_combo.currentTextChanged.connect(self.refresh_table)
        toolbar.addWidget(self.filter_combo)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(("ID", "Segnalazione", "Data", "Ora", "Luogo", "Stato", "Operatori"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.load_selected)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        new_button = QPushButton("Nuovo")
        new_button.clicked.connect(self.start_new)
        delete_button = QPushButton("Elimina")
        delete_button.setProperty("secondary", "true")
        delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(new_button)
        actions.addWidget(delete_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        return panel

    def _build_form_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Scheda sopralluogo")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        for key, label in (
            ("id", "ID"),
            ("segnalazione_id", "Segnalazione n."),
            ("data", "Data sopralluogo"),
            ("ora", "Ora"),
            ("operatori", "Operatori"),
            ("luogo", "Luogo"),
            ("ufficio", "Ufficio destinatario"),
        ):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)
        self.fields["id"].setReadOnly(True)

        self.stato = QComboBox()
        self.stato.addItems(STATI_SOPRALLUOGO)
        form.addRow("Stato", self.stato)
        layout.addLayout(form)

        flags = QHBoxLayout()
        self.presenza_foto = QCheckBox("Foto/allegati presenti")
        self.ulteriori_atti = QCheckBox("Ulteriori atti")
        flags.addWidget(self.presenza_foto)
        flags.addWidget(self.ulteriori_atti)
        flags.addStretch(1)
        layout.addLayout(flags)

        layout.addWidget(QLabel("Esito"))
        self.esito = QTextEdit()
        self.esito.setFixedHeight(95)
        layout.addWidget(self.esito)

        layout.addWidget(QLabel("Note operative"))
        self.note = QTextEdit()
        self.note.setFixedHeight(95)
        layout.addWidget(self.note)

        actions = QHBoxLayout()
        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.save_form)
        clear_button = QPushButton("Annulla")
        clear_button.setProperty("secondary", "true")
        clear_button.clicked.connect(self.start_new)
        actions.addWidget(save_button)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return panel

    def load_items(self) -> None:
        try:
            self.items = load_sopralluoghi()
        except Exception as exc:
            self.items = []
            QMessageBox.warning(self, "Errore lettura", f"Impossibile leggere i sopralluoghi.\n\n{exc}")
        self.refresh_table()

    def refresh_table(self) -> None:
        selected_filter = self.filter_combo.currentText()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        shown = 0
        for item in self.items:
            if selected_filter != "Tutti" and item.stato != selected_filter:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (
                str(item.id_sopralluogo),
                str(item.segnalazione_id),
                item.data_sopralluogo,
                item.ora_sopralluogo,
                item.luogo,
                item.stato,
                item.operatori,
            )
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                if column == 0:
                    table_item.setData(Qt.UserRole, item.id_sopralluogo)
                self.table.setItem(row, column, table_item)
            shown += 1
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.status.setText(f"Sopralluoghi visualizzati: {shown}")

    def selected_item(self) -> Sopralluogo | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        selected_id = int(item.data(Qt.UserRole))
        for record in self.items:
            if record.id_sopralluogo == selected_id:
                return record
        return None

    def load_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        self.editing_id = item.id_sopralluogo
        self.fields["id"].setText(str(item.id_sopralluogo))
        self.fields["segnalazione_id"].setText(str(item.segnalazione_id))
        self.fields["data"].setText(item.data_sopralluogo)
        self.fields["ora"].setText(item.ora_sopralluogo)
        self.fields["operatori"].setText(item.operatori)
        self.fields["luogo"].setText(item.luogo)
        self.fields["ufficio"].setText(item.ufficio_destinatario)
        self.stato.setCurrentText(item.stato)
        self.presenza_foto.setChecked(item.presenza_foto_allegati)
        self.ulteriori_atti.setChecked(item.ulteriori_atti)
        self.esito.setPlainText(item.esito)
        self.note.setPlainText(item.note_operative)

    def start_new(self) -> None:
        self.editing_id = None
        for field in self.fields.values():
            field.clear()
        self.stato.setCurrentText(STATI_SOPRALLUOGO[0])
        self.presenza_foto.setChecked(False)
        self.ulteriori_atti.setChecked(False)
        self.esito.clear()
        self.note.clear()
        self.table.clearSelection()

    def save_form(self) -> None:
        existing = self.find_current_edit()
        now = now_timestamp()
        try:
            segnalazione_id = int(self.fields["segnalazione_id"].text().strip())
        except ValueError:
            QMessageBox.warning(self, "Dati non validi", "Il numero segnalazione e obbligatorio e deve essere numerico.")
            return

        item = Sopralluogo(
            id_sopralluogo=existing.id_sopralluogo if existing else next_sopralluogo_id(load_sopralluoghi()),
            segnalazione_id=segnalazione_id,
            data_sopralluogo=self.fields["data"].text().strip(),
            ora_sopralluogo=self.fields["ora"].text().strip(),
            operatori=self.fields["operatori"].text().strip(),
            luogo=self.fields["luogo"].text().strip(),
            esito=self.esito.toPlainText().strip(),
            note_operative=self.note.toPlainText().strip(),
            presenza_foto_allegati=self.presenza_foto.isChecked(),
            ulteriori_atti=self.ulteriori_atti.isChecked(),
            ufficio_destinatario=self.fields["ufficio"].text().strip(),
            stato=self.stato.currentText(),
            data_creazione=existing.data_creazione if existing else now,
            data_ultima_modifica=now,
        )
        valid, reason = validate_sopralluogo(item)
        if not valid:
            QMessageBox.warning(self, "Dati non validi", reason)
            return

        action = "update" if existing else "create"
        old_status = existing.stato if existing else ""
        try:
            upsert_sopralluogo(item)
        except Exception as exc:
            log_audit_event(
                "sopralluoghi",
                action,
                "sopralluogo",
                str(item.id_sopralluogo),
                "Salvataggio sopralluogo non riuscito",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Salvataggio non riuscito", f"Impossibile salvare il sopralluogo.\n\n{exc}")
            return

        log_audit_event(
            "sopralluoghi",
            action,
            "sopralluogo",
            str(item.id_sopralluogo),
            "Creato sopralluogo" if action == "create" else "Modificato sopralluogo",
            extra={"segnalazione_id": item.segnalazione_id, "stato": item.stato},
        )
        if old_status and old_status != item.stato:
            log_audit_event(
                "sopralluoghi",
                "status_change",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Cambio stato sopralluogo",
                extra={"from": old_status, "to": item.stato},
            )
        self.load_items()
        self.select_item(item.id_sopralluogo)
        QMessageBox.information(self, "Sopralluogo salvato", "Il sopralluogo e stato salvato.")

    def find_current_edit(self) -> Sopralluogo | None:
        if self.editing_id is None:
            return None
        for item in self.items:
            if item.id_sopralluogo == self.editing_id:
                return item
        return None

    def select_item(self, item_id: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == item_id:
                self.table.selectRow(row)
                self.table.setCurrentCell(row, 0)
                return

    def delete_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un sopralluogo da eliminare.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            "Eliminare il sopralluogo selezionato?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            delete_sopralluogo(item.id_sopralluogo)
        except Exception as exc:
            log_audit_event(
                "sopralluoghi",
                "delete",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Eliminazione sopralluogo non riuscita",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Eliminazione non riuscita", f"Impossibile eliminare il sopralluogo.\n\n{exc}")
            return
        log_audit_event("sopralluoghi", "delete", "sopralluogo", str(item.id_sopralluogo), "Eliminato sopralluogo")
        self.load_items()
        self.start_new()
