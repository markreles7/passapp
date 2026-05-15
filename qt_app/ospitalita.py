from __future__ import annotations

import os
import shutil
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
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.backups import create_excel_backup
from core.dates import parse_date
from core.file_state import FileSnapshot, file_matches_snapshot
from core.ospitalita_excel import (
    compact_values,
    extract_year_from_text,
    find_record_by_progressivo,
    reserve_progressivo_slot,
    split_display_name_address,
    upsert_pending_record,
    write_pending_with_excel_com,
)
from core.workcopies import create_working_copy
from core.ospitalita_service import FOLDER_OSPITALITA, WORK_COPY_DIR, logger
from qt_app.widgets import page_header
from qt_app.workers import OspitalitaLoadWorker


MOTIVI = ("OSPITA", "CESSIONE IMMOBILE")


class OspitalitaEditDialog(QDialog):
    def __init__(self, record: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Modifica nominativo ospitalita" if record else "Nuovo nominativo ospitalita")
        self.setModal(True)
        self.resize(620, 360)
        self.result_record: dict[str, str] | None = None

        edit = record or {}
        den_nome = str(edit.get("denunciante_nome", "")).strip()
        den_indirizzo = str(edit.get("denunciante_indirizzo", "")).strip()
        if record and not den_nome and not den_indirizzo:
            den_nome, den_indirizzo = split_display_name_address(edit.get("denunciante_dichiarante", ""))
        straniero_nome = str(edit.get("straniero_nome", "")).strip()
        straniero_indirizzo = str(edit.get("straniero_indirizzo", "")).strip()
        if record and not straniero_nome and not straniero_indirizzo:
            straniero_nome, straniero_indirizzo = split_display_name_address(edit.get("cittadino_ospitato", ""))
        motivo = str(edit.get("tipo_comunicazione", "")).strip().upper() or "OSPITA"
        if motivo not in MOTIVI:
            motivo = "OSPITA"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.protocollo = QLineEdit(str(edit.get("protocollo", "")).strip())
        self.denunciante_nome = QLineEdit(den_nome)
        self.denunciante_indirizzo = QLineEdit(den_indirizzo)
        self.straniero_nome = QLineEdit(straniero_nome)
        self.straniero_indirizzo = QLineEdit(straniero_indirizzo)
        self.data = QLineEdit(str(edit.get("data_presentazione", "")).strip())
        self.data.setPlaceholderText("GG/MM/AAAA")
        self.motivo = QComboBox()
        self.motivo.addItems(MOTIVI)
        self.motivo.setCurrentText(motivo)
        self.indirizzo_ospitalita = QLineEdit(str(edit.get("indirizzo", "")).strip())

        form.addRow("Numero protocollo", self.protocollo)
        form.addRow("Cognome e Nome del denunciante", self.denunciante_nome)
        form.addRow("Indirizzo del denunciante", self.denunciante_indirizzo)
        form.addRow("Cognome e Nome dello straniero", self.straniero_nome)
        form.addRow("Indirizzo dello straniero", self.straniero_indirizzo)
        form.addRow("Data", self.data)
        form.addRow("Ospita o Cessione immobile", self.motivo)
        form.addRow("Indirizzo ospitalita/immobile", self.indirizzo_ospitalita)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salva")
        buttons.button(QDialogButtonBox.Cancel).setText("Annulla")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self) -> None:
        protocollo = self.protocollo.text().strip()
        denunciante_nome = self.denunciante_nome.text().strip()
        denunciante_indirizzo = self.denunciante_indirizzo.text().strip()
        straniero_nome = self.straniero_nome.text().strip()
        straniero_indirizzo = self.straniero_indirizzo.text().strip()
        data = self.data.text().strip()
        motivo = self.motivo.currentText().strip().upper()
        indirizzo_ospitalita = self.indirizzo_ospitalita.text().strip()

        if not protocollo:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci il protocollo.")
            return
        if not denunciante_nome:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci il cognome e nome del denunciante.")
            return
        if not denunciante_indirizzo:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci l'indirizzo del denunciante.")
            return
        if not straniero_nome:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci il cognome e nome dello straniero.")
            return
        if not straniero_indirizzo:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci l'indirizzo dello straniero.")
            return
        if parse_date(data) is None:
            QMessageBox.warning(self, "Data non valida", "Data non valida. Usa GG/MM/AAAA.")
            return
        if motivo not in MOTIVI:
            QMessageBox.warning(self, "Valore non valido", "Seleziona OSPITA o CESSIONE IMMOBILE.")
            return
        if not indirizzo_ospitalita:
            QMessageBox.warning(self, "Dati incompleti", "Inserisci l'indirizzo nel dettaglio ospitalita.")
            return

        self.result_record = {
            "protocollo": protocollo,
            "data": data,
            "denunciante_nome": denunciante_nome,
            "denunciante_indirizzo": denunciante_indirizzo,
            "straniero_nome": straniero_nome,
            "straniero_indirizzo": straniero_indirizzo,
            "motivo": motivo,
            "indirizzo_ospitalita": indirizzo_ospitalita,
        }
        self.accept()


class OspitalitaPage(QWidget):
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
        self.new_button = QPushButton("Nuovo")
        self.new_button.clicked.connect(self.new_record)
        self.edit_button = QPushButton("Modifica")
        self.edit_button.clicked.connect(self.edit_record)
        self.delete_button = QPushButton("Elimina")
        self.delete_button.setProperty("danger", "true")
        self.delete_button.clicked.connect(self.delete_record)
        self.save_button = QPushButton("Salva modifiche")
        self.save_button.clicked.connect(lambda _checked=False: self.save_changes())
        top.addWidget(self.refresh_button)
        top.addWidget(self.new_button)
        top.addWidget(self.edit_button)
        top.addWidget(self.delete_button)
        top.addWidget(self.save_button)
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
        self.year_filter.currentTextChanged.connect(self._on_year_changed)
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
        self.all_records_loaded = list(records)
        self.files = list(files)
        self.pending_records = []
        self.insights = list(insights)
        self._refresh_years()
        self._apply_year_context()
        self.apply_filters()
        self.total_label.setText(f"Totale: {len(self.records)}")
        self.file_label.setText(f"File: {len(self.source_files)}")
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
        self.total_label.setText(f"Totale: {len([r for r in self.records if not r.get('_deleted')])}")
        self.file_label.setText(f"File: {len(self.source_files)}")
        self.apply_filters()

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
        record = self._selected_record()
        if record is None:
            return
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

    def _prepare_working_copy(self) -> None:
        self.working_copy_file = None
        self.source_file_snapshot = None
        if not self.primary_source_file:
            return
        try:
            result = create_working_copy(self.primary_source_file, WORK_COPY_DIR, prefix="ospitalita_")
            if result.removed_old_copies:
                logger.info("Rimosse %s copie di lavoro vecchie ospitalita", result.removed_old_copies)
            self.working_copy_file = result.path
            self.source_file_snapshot = result.snapshot
        except OSError:
            logger.exception("Impossibile creare copia di lavoro ospitalita")
            QMessageBox.warning(self, "Copia di lavoro non disponibile", "Non e stato possibile creare la copia di lavoro del registro.")

    def _refresh_edit_buttons(self) -> None:
        can_edit = self.working_copy_file is not None
        has_selection = self.table.currentRow() >= 0
        self.new_button.setEnabled(can_edit)
        self.edit_button.setEnabled(can_edit and has_selection)
        self.delete_button.setEnabled(can_edit and has_selection)
        self.save_button.setEnabled(bool(self.pending_records))

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
            progressivo = str(pending.get("progressivo", "")).strip()
            source = str(pending.get("source", "")).strip()
            if mode in {"update_slot", "update_existing", "delete_existing"}:
                target = find_record_by_progressivo(self.records, progressivo, source)
                original = pending.get("original_snapshot")
                if target is not None and isinstance(original, dict):
                    target.clear()
                    target.update(original)
            elif mode == "append":
                self.records = [
                    record for record in self.records
                    if not (
                        record.get("_pending")
                        and str(record.get("progressivo", "")).strip() == progressivo
                        and str(record.get("source", "")).strip() == source
                    )
                ]
        self.pending_records = []
        self._refresh_edit_buttons()
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
        dialog = OspitalitaEditDialog(parent=self)
        if dialog.exec() != QDialog.Accepted or dialog.result_record is None:
            return
        source_name = self._current_source_name()
        progressivo, target_record, original_snapshot, mode = reserve_progressivo_slot(self.records, source_name)
        self._apply_dialog_result(progressivo, target_record, original_snapshot, mode, source_name, dialog.result_record, is_edit=False)
        QMessageBox.information(self, "Inserimento registrato", "Nominativo aggiunto. Usa Salva modifiche per aggiornare il file Excel.")

    def edit_record(self) -> None:
        if not self.working_copy_file:
            QMessageBox.warning(self, "Modifica non disponibile", "Seleziona un anno specifico per modificare il registro.")
            return
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un nominativo da modificare.")
            return
        progressivo = str(record.get("progressivo", "")).strip()
        if not progressivo:
            QMessageBox.warning(self, "Record non valido", "Progressivo non valido.")
            return
        dialog = OspitalitaEditDialog(record, self)
        if dialog.exec() != QDialog.Accepted or dialog.result_record is None:
            return
        source_name = str(record.get("source", "")).strip() or self._current_source_name()
        self._apply_dialog_result(progressivo, record, dict(record), "update_existing", source_name, dialog.result_record, is_edit=True)
        QMessageBox.information(self, "Modifica registrata", "Record aggiornato. Usa Salva modifiche per aggiornare il file Excel.")

    def _apply_dialog_result(
        self,
        progressivo: str,
        target_record: dict | None,
        original_snapshot: dict | None,
        mode: str,
        source_name: str,
        data: dict[str, str],
        *,
        is_edit: bool,
    ) -> None:
        denunciante_display = compact_values(data["denunciante_nome"], data["denunciante_indirizzo"])
        straniero_display = compact_values(data["straniero_nome"], data["straniero_indirizzo"])
        if target_record is None:
            target_record = {"progressivo": progressivo, "source": source_name, "sheet": "", "_pending": True}
            self.records.append(target_record)
        else:
            target_record["_pending"] = True

        target_record.update(
            {
                "progressivo": progressivo,
                "source": source_name,
                "protocollo": data["protocollo"],
                "denunciante_dichiarante": denunciante_display,
                "cittadino_ospitato": straniero_display,
                "data_presentazione": data["data"],
                "indirizzo": data["indirizzo_ospitalita"],
                "tipo_comunicazione": data["motivo"],
                "denunciante_nome": data["denunciante_nome"],
                "denunciante_indirizzo": data["denunciante_indirizzo"],
                "straniero_nome": data["straniero_nome"],
                "straniero_indirizzo": data["straniero_indirizzo"],
                "dettaglio_motivo": data["motivo"],
                "dettaglio_indirizzo": data["indirizzo_ospitalita"],
            }
        )
        upsert_pending_record(
            self.pending_records,
            {
                "mode": mode,
                "progressivo": progressivo,
                "source": source_name,
                **data,
                "original_snapshot": original_snapshot,
            },
        )
        log_audit_event(
            "ospitalita",
            "update" if is_edit else "create",
            "ospitalita",
            str(progressivo),
            "Modifica ospitalita registrata nella copia di lavoro Qt"
            if is_edit
            else "Nuovo inserimento ospitalita registrato nella copia di lavoro Qt",
            extra={"source": source_name},
        )
        self.total_label.setText(f"Totale: {len([r for r in self.records if not r.get('_deleted')])}")
        self._refresh_edit_buttons()
        self.apply_filters()

    def delete_record(self) -> None:
        if not self.working_copy_file:
            QMessageBox.warning(self, "Eliminazione non disponibile", "Seleziona un anno specifico per modificare il registro.")
            return
        record = self._selected_record()
        if record is None:
            QMessageBox.information(self, "Nessuna selezione", "Seleziona un'ospitalita da eliminare.")
            return
        progressivo = str(record.get("progressivo", "")).strip()
        if not progressivo:
            QMessageBox.warning(self, "Record non valido", "Progressivo non valido.")
            return
        nome = str(record.get("cittadino_ospitato", "")).strip() or f"progressivo {progressivo}"
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Vuoi eliminare l'ospitalita di {nome}?\n\nL'eliminazione sara applicata al file Excel solo con Salva modifiche.",
        )
        if answer != QMessageBox.Yes:
            return
        source_name = str(record.get("source", "")).strip() or self._current_source_name()
        original_snapshot = dict(record)
        record["_pending"] = True
        record["_deleted"] = True
        upsert_pending_record(
            self.pending_records,
            {"mode": "delete_existing", "progressivo": progressivo, "source": source_name, "original_snapshot": original_snapshot},
        )
        log_audit_event(
            "ospitalita",
            "delete_pending",
            "ospitalita",
            progressivo,
            "Eliminazione ospitalita registrata nella copia di lavoro Qt",
            extra={"source": source_name},
        )
        self.total_label.setText(f"Totale: {len([r for r in self.records if not r.get('_deleted')])}")
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
        if self.working_copy_file.suffix.lower() not in (".xlsx", ".xls"):
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
            write_pending_with_excel_com(self.working_copy_file, self.pending_records)
            create_excel_backup(self.primary_source_file, "ospitalita")
            log_audit_event("ospitalita", "backup", "excel", None, "Backup file originale Ospitalita creato da Qt")
            shutil.copy2(self.working_copy_file, self.primary_source_file)
        except Exception as exc:
            logger.exception("Errore salvataggio modifiche ospitalita Qt")
            log_audit_event(
                "ospitalita",
                "save",
                "excel",
                None,
                "Salvataggio modifiche Ospitalita Qt non riuscito",
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
            "ospitalita",
            "save",
            "excel",
            None,
            "Salvate modifiche Ospitalita sul file originale da Qt",
            extra={"count": saved_count},
        )
        QMessageBox.information(self, "Salvataggio completato", "Le modifiche sono state salvate sul file Excel.")
        if trigger_reload:
            self.refresh()
        else:
            self.apply_filters()
        return True

    @staticmethod
    def _record_year(record: dict) -> str:
        return OspitalitaPage._year_from_text(str(record.get("source", "")))

    @staticmethod
    def _file_year(path: str) -> str:
        return OspitalitaPage._year_from_text(os.path.basename(path))

    @staticmethod
    def _year_from_text(text: str) -> str:
        year = extract_year_from_text(text)
        return str(year) if year > 0 else ""

    @staticmethod
    def _value(value) -> str:
        text = str(value or "").strip()
        return text if text else "-"

    @classmethod
    def _compact(cls, *values) -> str:
        return compact_values(*values)
