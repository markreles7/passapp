from __future__ import annotations

import datetime
import os
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.backups import create_excel_backup
from core.dates import format_date, giorni_rimanenti, parse_date
from core.file_state import FileSnapshot, file_matches_snapshot
from core.pass_invalidi_authorizations import (
    build_authorization_output_path,
    build_authorization_payload,
    default_expiry,
    find_authorization_doc_for_record,
    generate_authorization_doc_with_word,
    resolve_authorization_template,
)
from core.pass_invalidi_excel import (
    compose_full_name,
    compute_authorization_expiry,
    find_record_by_numero,
    record_numero_int,
    reserve_numero_slot,
    split_cognome_nome,
    upsert_pending_record,
    write_pending_to_xlsx,
    write_pending_with_excel_com,
)
from core.workcopies import create_working_copy
from pass_invalidi import AUTH_CITY_DEFAULT, AUTH_DOCS_DIR, AUTH_TEMPLATE_PATH, CARTELLA_RETE, WORK_COPY_DIR, get_status, logger
from qt_app.widgets import page_header
from qt_app.workers import PassInvalidiLoadWorker


FILTERS = (
    ("tutti", "Tutti"),
    ("valid", "Validi"),
    ("soon", "In scadenza"),
    ("expired", "Scaduti"),
)


class PassInvalidiEditDialog(QDialog):
    def __init__(self, record: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Modifica nominativo invalidi" if record else "Nuovo nominativo invalidi")
        self.setModal(True)
        self.resize(520, 360)
        self.result_record: dict[str, str] | None = None
        edit_record = record or {}
        cognome_default = str(edit_record.get("cognome", "")).strip()
        nome_default = str(edit_record.get("nome_proprio", "")).strip()
        if not cognome_default and not nome_default:
            cognome_default, nome_default = split_cognome_nome(edit_record.get("nome", ""))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.cognome = QLineEdit(cognome_default)
        self.nome = QLineEdit(nome_default)
        self.nato_il = QLineEdit(format_date(edit_record.get("nato_il", "")) if record else "")
        self.indirizzo = QLineEdit(str(edit_record.get("indirizzo", "")).strip())
        self.rilascio = QLineEdit(format_date(edit_record.get("rilascio", "")) if record else "")
        self.scadenza = QLineEdit(format_date(edit_record.get("scadenza", "")) if record else "")
        self.note = QTextEdit(str(edit_record.get("note", "")).strip())
        self.note.setFixedHeight(72)
        for widget in (self.nato_il, self.rilascio, self.scadenza):
            widget.setPlaceholderText("GG/MM/AAAA")
        form.addRow("Cognome", self.cognome)
        form.addRow("Nome", self.nome)
        form.addRow("Nato il", self.nato_il)
        form.addRow("Indirizzo", self.indirizzo)
        form.addRow("Rilascio", self.rilascio)
        form.addRow("Scadenza", self.scadenza)
        form.addRow("Note", self.note)
        layout.addLayout(form)

        hint = QLabel("La scadenza viene proposta da rilascio e data nascita; puoi correggerla prima di salvare.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salva")
        buttons.button(QDialogButtonBox.Cancel).setText("Annulla")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.rilascio.textChanged.connect(self._refresh_scadenza_auto)
        self.nato_il.textChanged.connect(self._refresh_scadenza_auto)

    def _refresh_scadenza_auto(self) -> None:
        data_rilascio = parse_date(self.rilascio.text().strip())
        data_nascita = parse_date(self.nato_il.text().strip())
        if data_rilascio is None or data_nascita is None:
            return
        self.scadenza.setText(compute_authorization_expiry(data_rilascio, data_nascita).strftime("%d/%m/%Y"))

    def _accept(self) -> None:
        cognome = self.cognome.text().strip().upper()
        nome = self.nome.text().strip()
        nato_il_text = self.nato_il.text().strip()
        indirizzo = self.indirizzo.text().strip()
        rilascio_text = self.rilascio.text().strip()
        scadenza_text = self.scadenza.text().strip()
        note = self.note.toPlainText().strip()

        if not cognome or not nome or not indirizzo:
            QMessageBox.warning(self, "Dati incompleti", "Compila cognome, nome e indirizzo.")
            return
        data_nascita = parse_date(nato_il_text)
        data_rilascio = parse_date(rilascio_text)
        data_scadenza = parse_date(scadenza_text)
        if data_nascita is None:
            QMessageBox.warning(self, "Data non valida", "Data nascita non valida. Usa GG/MM/AAAA.")
            return
        if data_rilascio is None:
            QMessageBox.warning(self, "Data non valida", "Data rilascio non valida. Usa GG/MM/AAAA.")
            return
        if data_scadenza is None:
            QMessageBox.warning(self, "Data non valida", "Data scadenza non valida. Usa GG/MM/AAAA.")
            return

        auto_text = compute_authorization_expiry(data_rilascio, data_nascita).strftime("%d/%m/%Y")
        current_text = data_scadenza.strftime("%d/%m/%Y")
        if current_text != auto_text:
            answer = QMessageBox.question(
                self,
                "Conferma scadenza",
                f"Scadenza calcolata: {auto_text}\nScadenza inserita: {current_text}\n\nVuoi mantenere quella inserita?",
            )
            if answer != QMessageBox.Yes:
                return

        self.result_record = {
            "cognome": cognome,
            "nome_proprio": nome.strip(),
            "nome": compose_full_name(cognome, nome),
            "nato_il": data_nascita.strftime("%d/%m/%Y"),
            "indirizzo": indirizzo,
            "rilascio": data_rilascio.strftime("%d/%m/%Y"),
            "scadenza": data_scadenza.strftime("%d/%m/%Y"),
            "note": note,
        }
        self.accept()


class PassInvalidiAuthorizationDialog(QDialog):
    def __init__(self, record: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Crea autorizzazione pass invalidi")
        self.setModal(True)
        self.resize(620, 430)
        self.payload_input: dict[str, object] | None = None

        cognome_default, nome_default = split_cognome_nome(record.get("nome", ""))
        protocol_date_default = parse_date(record.get("rilascio")) or datetime.date.today()
        birth_default = parse_date(record.get("nato_il"))
        expiry_fallback = parse_date(record.get("scadenza")) or protocol_date_default
        expiry_default = default_expiry(protocol_date_default, birth_default, expiry_fallback)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.protocollo_numero = QLineEdit()
        self.protocollo_data = QLineEdit(protocol_date_default.strftime("%d/%m/%Y"))
        self.sesso = QComboBox()
        self.sesso.addItems(("F", "M"))
        self.cognome = QLineEdit(cognome_default)
        self.nome = QLineEdit(nome_default)
        self.luogo_nascita = QLineEdit()
        self.data_nascita = QLineEdit(format_date(record.get("nato_il", "")) if record.get("nato_il") else "")
        self.comune_residenza = QLineEdit("Pegognaga")
        self.indirizzo_residenza = QLineEdit(str(record.get("indirizzo", "")).strip())
        self.data_scadenza = QLineEdit(expiry_default.strftime("%d/%m/%Y"))
        self.comune_emissione = QLineEdit(AUTH_CITY_DEFAULT)
        for widget in (self.protocollo_data, self.data_nascita, self.data_scadenza):
            widget.setPlaceholderText("GG/MM/AAAA")

        form.addRow("Numero protocollo", self.protocollo_numero)
        form.addRow("Data protocollo", self.protocollo_data)
        form.addRow("Sesso", self.sesso)
        form.addRow("Cognome", self.cognome)
        form.addRow("Nome", self.nome)
        form.addRow("Luogo di nascita", self.luogo_nascita)
        form.addRow("Data di nascita", self.data_nascita)
        form.addRow("Comune di residenza", self.comune_residenza)
        form.addRow("Indirizzo di residenza", self.indirizzo_residenza)
        form.addRow("Scadenza autorizzazione", self.data_scadenza)
        form.addRow("Comune emissione", self.comune_emissione)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Crea")
        buttons.button(QDialogButtonBox.Cancel).setText("Annulla")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.protocollo_data.textChanged.connect(self._refresh_expiry)
        self.data_nascita.textChanged.connect(self._refresh_expiry)

    def _refresh_expiry(self) -> None:
        protocol_date = parse_date(self.protocollo_data.text().strip())
        birth_date = parse_date(self.data_nascita.text().strip())
        if protocol_date is None or birth_date is None:
            return
        self.data_scadenza.setText(compute_authorization_expiry(protocol_date, birth_date).strftime("%d/%m/%Y"))

    def _accept(self) -> None:
        protocol_number = self.protocollo_numero.text().strip()
        protocol_date = parse_date(self.protocollo_data.text().strip())
        cognome = self.cognome.text().strip().upper()
        nome = self.nome.text().strip().title()
        luogo_nascita = self.luogo_nascita.text().strip()
        data_nascita = parse_date(self.data_nascita.text().strip())
        comune_residenza = self.comune_residenza.text().strip()
        indirizzo_residenza = self.indirizzo_residenza.text().strip()
        data_scadenza = parse_date(self.data_scadenza.text().strip())
        comune_emissione = self.comune_emissione.text().strip() or AUTH_CITY_DEFAULT

        if not protocol_number:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci il numero protocollo.")
            return
        if protocol_date is None:
            QMessageBox.warning(self, "Data non valida", "Data protocollo non valida.")
            return
        if not cognome or not nome:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci cognome e nome.")
            return
        if not luogo_nascita:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci il luogo di nascita.")
            return
        if data_nascita is None:
            QMessageBox.warning(self, "Data non valida", "Data di nascita non valida.")
            return
        if not comune_residenza or not indirizzo_residenza:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci residenza completa.")
            return
        if data_scadenza is None:
            QMessageBox.warning(self, "Data non valida", "Data di scadenza non valida.")
            return

        self.payload_input = {
            "protocol_number": protocol_number,
            "protocol_date": protocol_date,
            "sesso": self.sesso.currentText(),
            "cognome": cognome,
            "nome": nome,
            "luogo_nascita": luogo_nascita,
            "data_nascita": data_nascita,
            "comune_residenza": comune_residenza,
            "indirizzo_residenza": indirizzo_residenza,
            "data_scadenza": data_scadenza,
            "comune_emissione": comune_emissione,
        }
        self.accept()


class PassInvalidiPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.all_records_loaded: list[dict] = []
        self.records: list[dict] = []
        self.filtered: list[dict] = []
        self.files: list[str] = []
        self.source_files: list[str] = []
        self.primary_source_file: str | None = None
        self.working_copy_file: Path | None = None
        self.source_file_snapshot: FileSnapshot | None = None
        self.pending_records: list[dict] = []
        self.last_year_value = "Tutti"
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
        self.new_button = QPushButton("Nuovo")
        self.new_button.clicked.connect(self.new_record)
        self.edit_button = QPushButton("Modifica")
        self.edit_button.clicked.connect(self.edit_record)
        self.delete_button = QPushButton("Elimina")
        self.delete_button.setProperty("danger", "true")
        self.delete_button.clicked.connect(self.delete_record)
        self.save_button = QPushButton("Salva modifiche")
        self.save_button.clicked.connect(lambda _checked=False: self.save_changes())
        self.open_auth_button = QPushButton("Apri autorizzazione")
        self.open_auth_button.setProperty("secondary", "true")
        self.open_auth_button.clicked.connect(self.open_authorization)
        self.create_auth_button = QPushButton("Crea autorizzazione")
        self.create_auth_button.setProperty("secondary", "true")
        self.create_auth_button.clicked.connect(self.create_authorization)
        open_folder = QPushButton("Apri cartella")
        open_folder.setProperty("secondary", "true")
        open_folder.clicked.connect(self.open_folder)
        top.addWidget(self.refresh_button)
        top.addWidget(self.new_button)
        top.addWidget(self.edit_button)
        top.addWidget(self.delete_button)
        top.addWidget(self.save_button)
        top.addWidget(self.open_auth_button)
        top.addWidget(self.create_auth_button)
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
        self.year_filter.currentTextChanged.connect(self._on_year_changed)
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
        self.table.itemSelectionChanged.connect(self._refresh_edit_buttons)
        layout.addWidget(self.table, 1)

        self.status = QLabel("Premi Aggiorna per caricare i registri configurati.")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)
        self._refresh_edit_buttons()

    def refresh(self) -> None:
        if self.thread is not None:
            return
        if self.pending_records and not self._confirm_pending_before_context_switch():
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
        self.all_records_loaded = list(records)
        self.files = list(files)
        self.pending_records = []
        self._refresh_years()
        self._apply_year_context()
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
        years = sorted({self._file_year(path) for path in self.files if self._file_year(path)}, reverse=True)
        current = self.year_filter.currentText()
        self.year_filter.blockSignals(True)
        self.year_filter.clear()
        self.year_filter.addItems(["Tutti"] + years)
        index = self.year_filter.findText(current)
        self.year_filter.setCurrentIndex(index if index >= 0 else 0)
        self.last_year_value = self.year_filter.currentText()
        self.year_filter.blockSignals(False)

    def _apply_year_context(self) -> None:
        selected_year = self.year_filter.currentText().strip()
        selected_files = list(self.files)
        selected_records = list(self.all_records_loaded)
        if selected_year and selected_year != "Tutti":
            selected_files = [path for path in self.files if self._file_year(path) == selected_year]
            source_names = {os.path.basename(path) for path in selected_files}
            selected_records = [
                record for record in self.all_records_loaded
                if str(record.get("source", "")).strip() in source_names
            ]

        self.source_files = selected_files
        self.records = selected_records
        if selected_year == "Tutti" and len(selected_files) != 1:
            self.primary_source_file = None
        else:
            self.primary_source_file = selected_files[0] if selected_files else None
        self._prepare_working_copy()
        self._refresh_edit_buttons()

    def _on_year_changed(self, next_year: str) -> None:
        next_year = (next_year or "Tutti").strip()
        if next_year == self.last_year_value:
            self.apply_filters()
            return
        if self.pending_records and not self._confirm_pending_before_context_switch():
            self.year_filter.blockSignals(True)
            self.year_filter.setCurrentText(self.last_year_value)
            self.year_filter.blockSignals(False)
            return
        self.last_year_value = next_year
        self.pending_records = []
        self._apply_year_context()
        self._refresh_stats()
        self.apply_filters()

    def _refresh_stats(self) -> None:
        records = [record for record in self.records if not record.get("_deleted")]
        expired = sum(1 for record in records if get_status(record.get("scadenza")) == "expired")
        soon = sum(1 for record in records if get_status(record.get("scadenza")) == "soon")
        self.total_label.setText(f"Totale: {len(records)}")
        self.file_label.setText(f"File: {len(self.source_files)}")
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
        record = self._selected_record()
        if record is None:
            return
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

    def _prepare_working_copy(self) -> None:
        self.working_copy_file = None
        self.source_file_snapshot = None
        if not self.primary_source_file:
            return
        try:
            result = create_working_copy(self.primary_source_file, WORK_COPY_DIR, prefix="invalidi_")
            if result.removed_old_copies:
                logger.info("Rimosse %s copie di lavoro vecchie pass invalidi", result.removed_old_copies)
            self.working_copy_file = result.path
            self.source_file_snapshot = result.snapshot
        except OSError:
            logger.exception("Impossibile creare copia di lavoro pass invalidi")
            QMessageBox.warning(self, "Copia di lavoro non disponibile", "Non e stato possibile creare la copia di lavoro del registro.")

    def _refresh_edit_buttons(self) -> None:
        can_edit = self.working_copy_file is not None
        has_selection = self.table.currentRow() >= 0
        self.new_button.setEnabled(can_edit)
        self.edit_button.setEnabled(can_edit and has_selection)
        self.delete_button.setEnabled(can_edit and has_selection)
        self.save_button.setEnabled(bool(self.pending_records))
        self.open_auth_button.setEnabled(has_selection)
        self.create_auth_button.setEnabled(has_selection)

    def _confirm_pending_before_context_switch(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Modifiche non salvate",
            "Sono presenti modifiche non salvate.\nVuoi salvarle prima di continuare?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Yes:
            return self.save_changes(trigger_reload=False)
        self._discard_pending_changes()
        return True

    def _discard_pending_changes(self) -> None:
        for pending in reversed(self.pending_records):
            mode = pending.get("mode")
            source = str(pending.get("source", "")).strip()
            numero = record_numero_int(pending)
            if numero is None:
                continue
            if mode in {"update_slot", "update_existing", "delete_existing"}:
                target = find_record_by_numero(self.records, numero, source)
                original = pending.get("original_snapshot")
                if target is not None and isinstance(original, dict):
                    target.clear()
                    target.update(original)
            elif mode == "append":
                self.records = [
                    record for record in self.records
                    if not (
                        record.get("_pending")
                        and record_numero_int(record) == numero
                        and str(record.get("source", "")).strip() == source
                    )
                ]
        self.pending_records = []
        self._refresh_edit_buttons()
        self._refresh_stats()
        self.apply_filters()

    def _current_source_name(self) -> str:
        return os.path.basename(self.primary_source_file).strip() if self.primary_source_file else ""

    def _selected_record(self) -> dict | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.filtered):
            return None
        return self.filtered[row]

    def new_record(self) -> None:
        if not self.working_copy_file:
            QMessageBox.warning(self, "Operazione non disponibile", "Seleziona un anno specifico per modificare il registro.")
            return
        dialog = PassInvalidiEditDialog(parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.result_record is None:
            return

        source_name = self._current_source_name()
        numero, target_record, original_snapshot, mode = reserve_numero_slot(self.records, source_name)
        record_data = dict(dialog.result_record)
        if target_record is None:
            target_record = {"numero": numero, "source": source_name, "_pending": True}
            self.records.append(target_record)
        else:
            target_record["_pending"] = True
        target_record.update({"numero": numero, "source": source_name, **record_data})
        upsert_pending_record(
            self.pending_records,
            {"mode": mode, "source": source_name, "numero": numero, **record_data, "original_snapshot": original_snapshot},
        )
        log_audit_event(
            "pass_invalidi",
            "create",
            "pass_invalidi",
            str(numero),
            "Nuovo nominativo registrato nella copia di lavoro Qt",
            extra={"source": source_name},
        )
        self._refresh_stats()
        self._refresh_edit_buttons()
        self.apply_filters()
        QMessageBox.information(self, "Inserimento registrato", "Nominativo aggiunto. Usa Salva modifiche per aggiornare il file Excel.")

    def edit_record(self) -> None:
        if not self.working_copy_file:
            QMessageBox.warning(self, "Modifica non disponibile", "Seleziona un anno specifico per modificare il registro.")
            return
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un nominativo da modificare.")
            return
        numero = record_numero_int(record)
        if numero is None:
            QMessageBox.warning(self, "Record non valido", "Numero progressivo non valido.")
            return
        dialog = PassInvalidiEditDialog(record, self)
        if dialog.exec() != QDialog.Accepted or dialog.result_record is None:
            return
        source_name = str(record.get("source", "")).strip() or self._current_source_name()
        original_snapshot = dict(record)
        record["_pending"] = True
        record.update({"numero": numero, "source": source_name, **dialog.result_record})
        upsert_pending_record(
            self.pending_records,
            {
                "mode": "update_existing",
                "source": source_name,
                "numero": numero,
                **dialog.result_record,
                "original_snapshot": original_snapshot,
            },
        )
        log_audit_event(
            "pass_invalidi",
            "update",
            "pass_invalidi",
            str(numero),
            "Modifica nominativo registrata nella copia di lavoro Qt",
            extra={"source": source_name},
        )
        self._refresh_stats()
        self._refresh_edit_buttons()
        self.apply_filters()
        QMessageBox.information(self, "Modifica registrata", "Record aggiornato. Usa Salva modifiche per aggiornare il file Excel.")

    def delete_record(self) -> None:
        if not self.working_copy_file:
            QMessageBox.warning(self, "Eliminazione non disponibile", "Seleziona un anno specifico per modificare il registro.")
            return
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un nominativo da eliminare.")
            return
        numero = record_numero_int(record)
        if numero is None:
            QMessageBox.warning(self, "Record non valido", "Numero progressivo non valido.")
            return
        nome = str(record.get("nome", "")).strip() or f"n. {numero}"
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Vuoi eliminare il pass invalidi di {nome}?\n\nL'eliminazione sara applicata al file Excel solo con Salva modifiche.",
        )
        if answer != QMessageBox.Yes:
            return
        source_name = str(record.get("source", "")).strip() or self._current_source_name()
        original_snapshot = dict(record)
        record["_pending"] = True
        record["_deleted"] = True
        upsert_pending_record(
            self.pending_records,
            {"mode": "delete_existing", "source": source_name, "numero": numero, "original_snapshot": original_snapshot},
        )
        log_audit_event(
            "pass_invalidi",
            "delete_pending",
            "pass_invalidi",
            str(numero),
            "Eliminazione pass invalidi registrata nella copia di lavoro Qt",
            extra={"source": source_name},
        )
        self._refresh_stats()
        self._refresh_edit_buttons()
        self.apply_filters()
        QMessageBox.information(self, "Eliminazione registrata", "Record segnato per l'eliminazione. Usa Salva modifiche per aggiornare il file Excel.")

    def save_changes(self, trigger_reload: bool = True) -> bool:
        if not self.pending_records:
            QMessageBox.information(self, "Nessuna modifica", "Non ci sono modifiche da salvare.")
            return False
        if not self.working_copy_file or not self.primary_source_file:
            QMessageBox.warning(self, "Salvataggio non disponibile", "Copia di lavoro non disponibile.")
            return False
        suffix = self.working_copy_file.suffix.lower()
        if suffix not in (".xlsx", ".xls"):
            QMessageBox.warning(self, "Formato non supportato", "Il salvataggio modifiche e supportato per file .xls/.xlsx.")
            return False
        if not file_matches_snapshot(self.source_file_snapshot):
            QMessageBox.warning(
                self,
                "File originale modificato",
                "Il file originale e stato modificato dopo l'apertura della copia di lavoro. Ricarica i dati prima di salvare.",
            )
            return False
        try:
            if suffix == ".xlsx":
                write_pending_to_xlsx(self.working_copy_file, self.pending_records)
            else:
                write_pending_with_excel_com(self.working_copy_file, self.pending_records)
            create_excel_backup(self.primary_source_file, "pass_invalidi")
            log_audit_event("pass_invalidi", "backup", "excel", None, "Backup file originale Pass Invalidi creato da Qt")
            shutil.copy2(self.working_copy_file, self.primary_source_file)
        except Exception as exc:
            logger.exception("Errore salvataggio modifiche pass invalidi Qt")
            log_audit_event(
                "pass_invalidi",
                "save",
                "excel",
                None,
                "Salvataggio modifiche Pass Invalidi Qt non riuscito",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Salvataggio non riuscito", f"Impossibile salvare le modifiche.\n\nDettagli:\n{exc}")
            return False

        saved_count = len(self.pending_records)
        for record in self.records:
            record.pop("_pending", None)
            record.pop("_deleted", None)
        self.pending_records = []
        self._refresh_edit_buttons()
        log_audit_event(
            "pass_invalidi",
            "save",
            "excel",
            None,
            "Salvate modifiche Pass Invalidi sul file originale da Qt",
            extra={"count": saved_count},
        )
        QMessageBox.information(self, "Salvataggio completato", "Le modifiche sono state salvate sul file Excel.")
        if trigger_reload:
            self.refresh()
        else:
            self._refresh_stats()
            self.apply_filters()
        return True

    def open_authorization(self) -> None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un nominativo.")
            return
        path = find_authorization_doc_for_record(record, AUTH_DOCS_DIR)
        if path is None:
            QMessageBox.information(
                self,
                "Autorizzazione non trovata",
                f"Nessun file autorizzazione trovato in:\n{AUTH_DOCS_DIR}",
            )
            return
        try:
            os.startfile(str(path))
        except OSError as exc:
            QMessageBox.critical(self, "Apertura non riuscita", f"Impossibile aprire il file.\n\nDettagli:\n{exc}")

    def create_authorization(self) -> None:
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un nominativo.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma creazione autorizzazione",
            "Vuoi creare una nuova autorizzazione per il nominativo selezionato?\n\n"
            "Se il documento esiste gia, usa il pulsante Apri autorizzazione.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        template_path = resolve_authorization_template(AUTH_TEMPLATE_PATH, AUTH_DOCS_DIR)
        if template_path is None:
            QMessageBox.critical(
                self,
                "Template non trovato",
                f"Nessun template autorizzazione disponibile.\nControlla il percorso:\n{AUTH_TEMPLATE_PATH}",
            )
            return

        docs_dir = Path(AUTH_DOCS_DIR)
        if not docs_dir.exists():
            QMessageBox.critical(self, "Cartella non trovata", f"Percorso non disponibile:\n{AUTH_DOCS_DIR}")
            return

        dialog = PassInvalidiAuthorizationDialog(record, self)
        if dialog.exec() != QDialog.Accepted or dialog.payload_input is None:
            return
        try:
            payload = build_authorization_payload(record, **dialog.payload_input)
            output_path = build_authorization_output_path(
                docs_dir,
                template_path,
                cognome=str(payload["cognome"]),
                nome=str(payload["nome"]),
                numero=int(payload["auth_number"]),
                year=int(payload["year"]),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Dati non validi", str(exc))
            return

        if output_path.exists():
            answer = QMessageBox.question(
                self,
                "File gia esistente",
                f"Il file esiste gia:\n{output_path}\n\nVuoi sovrascriverlo?",
            )
            if answer != QMessageBox.Yes:
                return

        try:
            generate_authorization_doc_with_word(template_path, output_path, payload)
        except Exception as exc:
            logger.exception("Errore creazione autorizzazione pass invalidi Qt")
            log_audit_event(
                "pass_invalidi",
                "authorization_create",
                "document",
                str(payload.get("auth_number", "")),
                "Creazione autorizzazione Pass Invalidi Qt non riuscita",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Creazione non riuscita", f"Impossibile creare il file .doc.\n\nDettagli:\n{exc}")
            return

        log_audit_event(
            "pass_invalidi",
            "authorization_create",
            "document",
            str(payload.get("auth_number", "")),
            "Autorizzazione Pass Invalidi creata da Qt",
            extra={"path": str(output_path)},
        )
        QMessageBox.information(self, "Autorizzazione creata", f"File creato:\n{output_path}")
        try:
            os.startfile(str(output_path))
        except OSError:
            pass

    @staticmethod
    def _record_year(record: dict) -> str:
        source = str(record.get("source", ""))
        return PassInvalidiPage._year_from_text(source)

    @staticmethod
    def _file_year(path: str) -> str:
        return PassInvalidiPage._year_from_text(os.path.basename(path))

    @staticmethod
    def _year_from_text(text: str) -> str:
        import re

        years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", str(text or ""))]
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
