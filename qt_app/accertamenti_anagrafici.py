from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
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

from app_config import resolve_path
from core.accertamenti_anagrafici import (
    ACCERTAMENTI_FILE,
    DEFAULT_ACCERTAMENTI_EXCEL,
    STATI_ACCERTAMENTO,
    AccertamentoAnagrafico,
    initialize_accertamenti_from_excel_if_needed,
    import_accertamenti_from_excel,
    load_accertamenti,
    negative_attempts,
    next_accertamento_numero,
    normalize_time,
    now_timestamp,
    save_accertamenti,
    save_accertamenti_to_excel,
    validate_accertamento,
)
from core.audit import log_audit_event
from core.backups import create_excel_backup
from core.file_state import FileSnapshot, file_matches_snapshot
from core.workcopies import create_working_copy
from qt_app.widgets import page_header


WORK_COPY_DIR = resolve_path("data/workcopies")


class AccertamentoEditDialog(QDialog):
    def __init__(self, item: AccertamentoAnagrafico, parent: QWidget | None = None):
        super().__init__(parent)
        self.source = item
        self.result_item: AccertamentoAnagrafico | None = None
        self.setWindowTitle(f"Accertamento anagrafico n. {item.numero}")
        self.setModal(True)
        self.resize(760, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(f"Accertamento n. {item.numero}")
        title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.nominativo = QLineEdit(item.nominativo)
        self.indirizzo = QLineEdit(item.indirizzo)
        self.note = QTextEdit()
        self.note.setMinimumHeight(80)
        self.note.setPlainText(item.note)
        form.addRow("Nominativo", self.nominativo)
        form.addRow("Indirizzo", self.indirizzo)
        form.addRow("Note disponibilita", self.note)
        root.addLayout(form)

        attempts = QGridLayout()
        attempts.setHorizontalSpacing(12)
        attempts.setVerticalSpacing(8)
        attempts.addWidget(QLabel("Esito"), 0, 0)
        attempts.addWidget(QLabel("Data"), 0, 1)
        attempts.addWidget(QLabel("Ora"), 0, 2)

        self.attempt_fields: dict[str, tuple[QLineEdit, QLineEdit]] = {}
        rows = (
            ("primo_negativo", "1° negativo", item.primo_negativo_data, item.primo_negativo_ora),
            ("secondo_negativo", "2° negativo", item.secondo_negativo_data, item.secondo_negativo_ora),
            ("terzo_negativo", "3° negativo", item.terzo_negativo_data, item.terzo_negativo_ora),
            ("positivo", "Positivo", item.positivo_data, item.positivo_ora),
        )
        for row, (key, label, data, ora) in enumerate(rows, start=1):
            data_edit = QLineEdit(data)
            data_edit.setPlaceholderText("GG/MM/AAAA")
            ora_edit = QLineEdit(ora)
            ora_edit.setPlaceholderText("HH:MM")
            attempts.addWidget(QLabel(label), row, 0)
            attempts.addWidget(data_edit, row, 1)
            attempts.addWidget(ora_edit, row, 2)
            self.attempt_fields[key] = (data_edit, ora_edit)
        root.addLayout(attempts)

        quick_actions = QHBoxLayout()
        today_positive = QPushButton("Positivo adesso")
        today_positive.setProperty("secondary", "true")
        today_positive.clicked.connect(self.set_positive_now)
        clear_positive = QPushButton("Svuota positivo")
        clear_positive.setProperty("secondary", "true")
        clear_positive.clicked.connect(self.clear_positive)
        quick_actions.addStretch(1)
        quick_actions.addWidget(today_positive)
        quick_actions.addWidget(clear_positive)
        root.addLayout(quick_actions)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.accept_form)
        cancel_button = QPushButton("Annulla")
        cancel_button.setProperty("secondary", "true")
        cancel_button.clicked.connect(self.reject)
        actions.addWidget(save_button)
        actions.addWidget(cancel_button)
        root.addLayout(actions)

    def set_positive_now(self) -> None:
        data_edit, ora_edit = self.attempt_fields["positivo"]
        now = dt.datetime.now()
        data_edit.setText(now.strftime("%d/%m/%Y"))
        ora_edit.setText(now.strftime("%H:%M"))

    def clear_positive(self) -> None:
        data_edit, ora_edit = self.attempt_fields["positivo"]
        data_edit.clear()
        ora_edit.clear()

    def accept_form(self) -> None:
        now = now_timestamp()

        def pair(key: str) -> tuple[str, str]:
            data_edit, ora_edit = self.attempt_fields[key]
            ora = normalize_time(ora_edit.text().strip())
            return data_edit.text().strip(), ora if ora is not None else ora_edit.text().strip()

        primo_data, primo_ora = pair("primo_negativo")
        secondo_data, secondo_ora = pair("secondo_negativo")
        terzo_data, terzo_ora = pair("terzo_negativo")
        positivo_data, positivo_ora = pair("positivo")
        item = AccertamentoAnagrafico(
            numero=self.source.numero,
            nominativo=self.nominativo.text().strip(),
            indirizzo=self.indirizzo.text().strip(),
            note=self.note.toPlainText().strip(),
            primo_negativo_data=primo_data,
            primo_negativo_ora=primo_ora,
            secondo_negativo_data=secondo_data,
            secondo_negativo_ora=secondo_ora,
            terzo_negativo_data=terzo_data,
            terzo_negativo_ora=terzo_ora,
            positivo_data=positivo_data,
            positivo_ora=positivo_ora,
            data_creazione=self.source.data_creazione or now,
            data_ultima_modifica=now,
        )
        valid, reason = validate_accertamento(item)
        if not valid:
            QMessageBox.warning(self, "Dati non validi", reason)
            return
        self.result_item = item
        self.accept()


class AccertamentiAnagraficiPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.items: list[AccertamentoAnagrafico] = []
        self.editing_numero: int | None = None
        self.json_path = self._configured_path("accertamenti_anagrafici_file", ACCERTAMENTI_FILE)
        self.excel_path = self._configured_path("accertamenti_anagrafici_excel", DEFAULT_ACCERTAMENTI_EXCEL)
        self.working_copy_file: Path | None = None
        self.source_file_snapshot: FileSnapshot | None = None
        self.dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(
            page_header(
                "Accertamenti Anagrafici",
                "Elenco accertamenti di residenza, tentativi negativi e chiusura positiva.",
            )
        )

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        self.load_items()
        self.clear_detail()

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        refresh_button = QPushButton("Aggiorna")
        refresh_button.clicked.connect(self.load_items)
        new_button = QPushButton("Nuovo")
        new_button.clicked.connect(self.new_accertamento)
        self.edit_button = QPushButton("Modifica")
        self.edit_button.clicked.connect(self.edit_current)
        self.save_button = QPushButton("Salva modifiche")
        self.save_button.clicked.connect(self.save_changes)
        delete_button = QPushButton("Elimina")
        delete_button.setProperty("secondary", "true")
        delete_button.clicked.connect(self.delete_selected)
        toolbar.addWidget(refresh_button)
        toolbar.addWidget(new_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(delete_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        filters = QGridLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca nominativo, indirizzo o note")
        self.search.textChanged.connect(self.refresh_table)
        filters.addWidget(self.search, 0, 0, 1, 3)
        filters.addWidget(QLabel("Stato"), 0, 3)
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(("Tutti",) + STATI_ACCERTAMENTO)
        self.filter_combo.currentTextChanged.connect(self.refresh_table)
        filters.addWidget(self.filter_combo, 0, 4)
        filters.setColumnStretch(2, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ("N°", "Nominativo", "Indirizzo", "Note", "1° negativo", "2° negativo", "3° negativo", "Positivo", "Stato")
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.load_selected)
        self.table.itemDoubleClicked.connect(lambda _item: self.edit_current())
        layout.addWidget(self.table, 1)
        return panel

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Dettaglio accertamento")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        self.summary_title = QLabel("Nessun accertamento selezionato")
        self.summary_title.setStyleSheet("font-size: 12pt; font-weight: 700;")
        self.summary_title.setWordWrap(True)
        layout.addWidget(self.summary_title)

        self.summary_meta = QLabel("")
        self.summary_meta.setObjectName("Muted")
        self.summary_meta.setWordWrap(True)
        layout.addWidget(self.summary_meta)

        self.summary_status = QLabel("")
        self.summary_status.setObjectName("Muted")
        self.summary_status.setWordWrap(True)
        layout.addWidget(self.summary_status)

        layout.addWidget(QLabel("Note"))
        self.note_view = QTextEdit()
        self.note_view.setReadOnly(True)
        self.note_view.setMinimumHeight(120)
        layout.addWidget(self.note_view)

        actions = QHBoxLayout()
        self.detail_edit_button = QPushButton("Modifica")
        self.detail_edit_button.clicked.connect(self.edit_current)
        mark_positive = QPushButton("Completa adesso")
        mark_positive.setProperty("secondary", "true")
        mark_positive.clicked.connect(self.complete_selected_now)
        clear_button = QPushButton("Annulla")
        clear_button.setProperty("secondary", "true")
        clear_button.clicked.connect(self.clear_detail)
        actions.addWidget(self.detail_edit_button)
        actions.addWidget(mark_positive)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        self.mark_positive_button = mark_positive
        return panel

    def load_items(self) -> None:
        if self.dirty and not self._confirm_pending_before_reload():
            return
        try:
            imported = initialize_accertamenti_from_excel_if_needed(json_path=self.json_path, excel_path=self.excel_path)
            self._prepare_working_copy()
            if self.working_copy_file is not None:
                self.items = import_accertamenti_from_excel(self.working_copy_file)
                save_accertamenti(self.items, self.json_path)
            else:
                self.items = load_accertamenti(self.json_path)
            self.dirty = False
        except Exception as exc:
            self.items = []
            QMessageBox.warning(self, "Errore lettura", f"Impossibile leggere gli accertamenti anagrafici.\n\n{exc}")
            imported = False
        self.refresh_table()
        if imported:
            self.status.setText(f"Importati accertamenti dal file Excel: {len(self.items)}")
        self._refresh_buttons()

    def _prepare_working_copy(self) -> None:
        self.working_copy_file = None
        self.source_file_snapshot = None
        if not self.excel_path.exists():
            return
        result = create_working_copy(self.excel_path, WORK_COPY_DIR, prefix="accertamenti_anagrafici_")
        self.working_copy_file = result.path
        self.source_file_snapshot = result.snapshot

    def refresh_table(self) -> None:
        selected_filter = self.filter_combo.currentText()
        needle = self.search.text().strip().lower()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        shown = 0
        counts = {key: 0 for key in STATI_ACCERTAMENTO}
        for item in self.items:
            counts[item.stato] = counts.get(item.stato, 0) + 1
            if selected_filter != "Tutti" and item.stato != selected_filter:
                continue
            haystack = " ".join((item.nominativo, item.indirizzo, item.note)).lower()
            if needle and needle not in haystack:
                continue
            self._add_table_row(item)
            shown += 1
        self.table.blockSignals(False)
        self.table.resizeColumnsToContents()
        self.status.setText(
            "Accertamenti visualizzati: "
            f"{shown} | da fare: {counts.get('da fare', 0)} | in corso: {counts.get('in corso', 0)} | completati: {counts.get('completato', 0)}"
        )
        self._refresh_buttons()

    def _add_table_row(self, item: AccertamentoAnagrafico) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = (
            str(item.numero),
            item.nominativo,
            item.indirizzo,
            item.note,
            self._format_pair(item.primo_negativo_data, item.primo_negativo_ora),
            self._format_pair(item.secondo_negativo_data, item.secondo_negativo_ora),
            self._format_pair(item.terzo_negativo_data, item.terzo_negativo_ora),
            self._format_pair(item.positivo_data, item.positivo_ora),
            item.stato.upper(),
        )
        for column, value in enumerate(values):
            table_item = QTableWidgetItem(value)
            if column == 0:
                table_item.setData(Qt.UserRole, item.numero)
            if item.stato == "completato":
                font = QFont(table_item.font())
                font.setStrikeOut(True)
                table_item.setFont(font)
                table_item.setForeground(QColor("#8A8F98"))
            self.table.setItem(row, column, table_item)

    def selected_item(self) -> AccertamentoAnagrafico | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        selected_numero = int(item.data(Qt.UserRole))
        for record in self.items:
            if record.numero == selected_numero:
                return record
        return None

    def load_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            return
        self.editing_numero = item.numero
        self.summary_title.setText(f"N. {item.numero} - {item.nominativo}")
        self.summary_meta.setText(f"Indirizzo: {item.indirizzo or '-'}")
        attempts = []
        for idx, (data, ora) in enumerate(negative_attempts(item), start=1):
            attempts.append(f"{idx}° negativo: {self._format_pair(data, ora) or '-'}")
        attempts.append(f"Positivo: {self._format_pair(item.positivo_data, item.positivo_ora) or '-'}")
        attempts.append(f"Stato: {item.stato.upper()}")
        self.summary_status.setText("\n".join(attempts))
        self.note_view.setPlainText(item.note)
        self._set_detail_enabled(True)

    def clear_detail(self) -> None:
        self.editing_numero = None
        self.table.clearSelection()
        self.summary_title.setText("Nessun accertamento selezionato")
        self.summary_meta.setText("")
        self.summary_status.setText("")
        self.note_view.clear()
        self._set_detail_enabled(False)

    def new_accertamento(self) -> None:
        item = AccertamentoAnagrafico(
            numero=next_accertamento_numero(self.items),
            data_creazione=now_timestamp(),
        )
        self._open_dialog(item, existing=None)

    def edit_current(self) -> None:
        existing = self.selected_item()
        if existing is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un accertamento da modificare.")
            return
        self._open_dialog(existing, existing=existing)

    def _open_dialog(self, item: AccertamentoAnagrafico, existing: AccertamentoAnagrafico | None) -> None:
        dialog = AccertamentoEditDialog(item, self)
        if dialog.exec() != QDialog.Accepted or dialog.result_item is None:
            return
        self.save_item(dialog.result_item, existing)

    def save_item(self, item: AccertamentoAnagrafico, existing: AccertamentoAnagrafico | None) -> None:
        action = "update" if existing else "create"
        old_status = existing.stato if existing else ""
        replaced = False
        for idx, current in enumerate(self.items):
            if current.numero == item.numero:
                self.items[idx] = item
                replaced = True
                break
        if not replaced:
            self.items.append(item)
        self.items = sorted(self.items, key=lambda record: record.numero)
        self.dirty = True
        log_audit_event(
            "accertamenti_anagrafici",
            f"{action}_pending",
            "accertamento",
            str(item.numero),
            "Creato accertamento anagrafico nella copia di lavoro"
            if action == "create"
            else "Modificato accertamento anagrafico nella copia di lavoro",
            extra={"stato": item.stato},
        )
        if old_status and old_status != item.stato:
            log_audit_event(
                "accertamenti_anagrafici",
                "status_change",
                "accertamento",
                str(item.numero),
                "Cambio stato accertamento anagrafico",
                extra={"from": old_status, "to": item.stato},
            )
        self.refresh_table()
        self.select_item(item.numero)
        QMessageBox.information(
            self,
            "Modifica registrata",
            "Modifica registrata. Usa Salva modifiche per aggiornare il file Excel originale.",
        )

    def complete_selected_now(self) -> None:
        item = self.selected_item()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un accertamento da completare.")
            return
        if item.stato == "completato":
            return
        updated = AccertamentoAnagrafico.from_dict(item.to_dict())
        if updated is None:
            return
        now = dt.datetime.now()
        updated.positivo_data = now.strftime("%d/%m/%Y")
        updated.positivo_ora = now.strftime("%H:%M")
        updated.data_ultima_modifica = now_timestamp()
        self.save_item(updated, item)

    def select_item(self, numero: int) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == numero:
                self.table.selectRow(row)
                self.table.setCurrentCell(row, 0)
                return

    def delete_selected(self) -> None:
        item = self.selected_item()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un accertamento da eliminare.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            "Eliminare l'accertamento selezionato?\n\nL'eliminazione sara applicata al file Excel solo con Salva modifiche.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.items = [record for record in self.items if record.numero != item.numero]
        self.dirty = True
        log_audit_event("accertamenti_anagrafici", "delete_pending", "accertamento", str(item.numero), "Eliminazione accertamento anagrafico registrata nella copia di lavoro")
        self.refresh_table()
        self.clear_detail()
        QMessageBox.information(
            self,
            "Eliminazione registrata",
            "Accertamento segnato per l'eliminazione. Usa Salva modifiche per aggiornare il file Excel originale.",
        )

    def save_changes(self) -> bool:
        if not self.dirty:
            QMessageBox.information(self, "Nessuna modifica", "Non ci sono modifiche da salvare.")
            return False
        if self.working_copy_file is None:
            QMessageBox.warning(self, "Salvataggio non disponibile", "Copia di lavoro non disponibile.")
            return False
        if not file_matches_snapshot(self.source_file_snapshot):
            QMessageBox.warning(
                self,
                "File originale modificato",
                "Il file originale e stato modificato dopo l'apertura della copia di lavoro. Ricarica i dati prima di salvare.",
            )
            return False
        try:
            save_accertamenti_to_excel(self.working_copy_file, self.items)
            create_excel_backup(self.excel_path, "accertamenti_anagrafici")
            log_audit_event("accertamenti_anagrafici", "backup", "excel", None, "Backup file originale Accertamenti Anagrafici creato da Qt")
            shutil.copy2(self.working_copy_file, self.excel_path)
            save_accertamenti(self.items, self.json_path)
        except Exception as exc:
            log_audit_event(
                "accertamenti_anagrafici",
                "save",
                "excel",
                None,
                "Salvataggio modifiche Accertamenti Anagrafici non riuscito",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Salvataggio non riuscito", f"Impossibile salvare le modifiche.\n\nDettagli:\n{exc}")
            return False

        self.dirty = False
        log_audit_event(
            "accertamenti_anagrafici",
            "save",
            "excel",
            None,
            "Salvate modifiche Accertamenti Anagrafici sul file originale",
            extra={"count": len(self.items)},
        )
        QMessageBox.information(self, "Salvataggio completato", "Le modifiche sono state salvate sul file Excel originale.")
        self.load_items()
        return True

    def _confirm_pending_before_reload(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Modifiche non salvate",
            "Sono presenti modifiche non salvate.\nVuoi salvarle prima di aggiornare?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Yes:
            return self.save_changes()
        self.dirty = False
        return True

    def _set_detail_enabled(self, selected: bool) -> None:
        self.edit_button.setEnabled(selected)
        self.detail_edit_button.setEnabled(selected)
        current = self.selected_item()
        self.mark_positive_button.setEnabled(selected and current is not None and current.stato != "completato")
        self.save_button.setEnabled(self.dirty)

    def _refresh_buttons(self) -> None:
        selected = self.selected_item() is not None
        self._set_detail_enabled(selected)

    @staticmethod
    def _format_pair(data: str, ora: str) -> str:
        if data and ora:
            return f"{data} {ora}"
        return data or ora

    def _configured_path(self, key: str, default: Path) -> Path:
        value = self.config.get("paths", {}).get(key, str(default))
        path = Path(value)
        return path if path.is_absolute() else resolve_path(path)
