from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.fascicoli import add_attachment, ensure_fascicolo, list_attachments, open_path
from core.powershell import check_office_com
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
import segnalazioni as segn_mod
from segnalazioni import Segnalazione
from qt_app.sopralluoghi_pdf import SEGNALAZIONI_PDF_DIR, safe_pdf_filename
from qt_app.widgets import page_header
from qt_app.workers import SopralluogoPdfWorker


class SopralluoghiPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.items: list[Sopralluogo] = []
        self.editing_id: int | None = None
        self.fields: dict[str, QLineEdit] = {}
        self.word_available: bool | None = None
        self.pdf_thread: QThread | None = None
        self.pdf_worker: SopralluogoPdfWorker | None = None
        self.pending_pdf_item: Sopralluogo | None = None
        self.pending_pdf_seg: Segnalazione | None = None

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
        toolbar.addWidget(QLabel("Segnalazione"))
        self.segnalazione_filter = QLineEdit()
        self.segnalazione_filter.setPlaceholderText("N.")
        self.segnalazione_filter.setFixedWidth(80)
        self.segnalazione_filter.textChanged.connect(self.refresh_table)
        toolbar.addWidget(self.segnalazione_filter)
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

        fascicolo_box = QFrame()
        fascicolo_box.setObjectName("SoftCard")
        fascicolo_layout = QVBoxLayout(fascicolo_box)
        fascicolo_layout.setContentsMargins(12, 10, 12, 10)
        fascicolo_layout.setSpacing(8)
        self.attachment_status = QLabel("Fascicolo: seleziona o salva un sopralluogo")
        self.attachment_status.setObjectName("Muted")
        fascicolo_layout.addWidget(self.attachment_status)
        fascicolo_actions = QHBoxLayout()
        self.open_folder_button = QPushButton("Apri fascicolo")
        self.open_folder_button.setProperty("secondary", "true")
        self.open_folder_button.clicked.connect(self.open_fascicolo)
        photo_button = QPushButton("Aggiungi foto")
        photo_button.setProperty("secondary", "true")
        photo_button.clicked.connect(lambda: self.add_selected_attachment("foto"))
        doc_button = QPushButton("Aggiungi allegato")
        doc_button.setProperty("secondary", "true")
        doc_button.clicked.connect(lambda: self.add_selected_attachment("documento"))
        self.pdf_button = QPushButton("Genera verbale PDF")
        self.pdf_button.clicked.connect(self.export_selected_pdf)
        fascicolo_actions.addWidget(self.open_folder_button)
        fascicolo_actions.addWidget(photo_button)
        fascicolo_actions.addWidget(doc_button)
        fascicolo_actions.addWidget(self.pdf_button)
        fascicolo_actions.addStretch(1)
        fascicolo_layout.addLayout(fascicolo_actions)
        layout.addWidget(fascicolo_box)

        actions = QHBoxLayout()
        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.save_form)
        clear_button = QPushButton("Annulla")
        clear_button.setProperty("secondary", "true")
        clear_button.clicked.connect(self.start_new)
        self.pdf_progress = QProgressBar()
        self.pdf_progress.setRange(0, 0)
        self.pdf_progress.setFixedWidth(120)
        self.pdf_progress.hide()
        actions.addWidget(save_button)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        actions.addWidget(self.pdf_progress)
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
        seg_filter = self.segnalazione_filter.text().strip()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        shown = 0
        for item in self.items:
            if selected_filter != "Tutti" and item.stato != selected_filter:
                continue
            if seg_filter and str(item.segnalazione_id) != seg_filter:
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
        suffix = f" per segnalazione {seg_filter}" if seg_filter else ""
        self.status.setText(f"Sopralluoghi visualizzati: {shown}{suffix}")

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
        self.update_fascicolo_status(item)

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
        self.attachment_status.setText("Fascicolo: seleziona o salva un sopralluogo")

    def open_for_segnalazione(self, segnalazione_id: int, *, create_new: bool = False, luogo: str = "") -> None:
        self.load_items()
        self.segnalazione_filter.setText(str(segnalazione_id))
        linked = [item for item in self.items if item.segnalazione_id == segnalazione_id]
        if create_new or not linked:
            self.start_new()
            self.segnalazione_filter.setText(str(segnalazione_id))
            self.fields["segnalazione_id"].setText(str(segnalazione_id))
            self.fields["data"].setText(dt.date.today().strftime("%d/%m/%Y"))
            if luogo:
                self.fields["luogo"].setText(luogo)
            self.status.setText(f"Nuovo sopralluogo per segnalazione {segnalazione_id}")
            return
        self.select_item(linked[0].id_sopralluogo)
        self.status.setText(f"Sopralluoghi della segnalazione {segnalazione_id}")

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

    def update_fascicolo_status(self, item: Sopralluogo | None = None) -> None:
        current = item or self.find_current_edit() or self.selected_item()
        if current is None:
            self.attachment_status.setText("Fascicolo: seleziona o salva un sopralluogo")
            return
        try:
            attachments = list_attachments(current.segnalazione_id, sopralluogo_id=current.id_sopralluogo)
            all_attachments = list_attachments(current.segnalazione_id)
            self.attachment_status.setText(
                f"Fascicolo segnalazione {current.segnalazione_id}: "
                f"{len(attachments)} allegati del sopralluogo, {len(all_attachments)} totali"
            )
        except Exception:
            self.attachment_status.setText(f"Fascicolo segnalazione {current.segnalazione_id}: stato non disponibile")

    def _load_segnalazione(self, segnalazione_id: int) -> Segnalazione | None:
        for path in (segn_mod.SEGNALAZIONI_FILE, segn_mod.SEGNALAZIONI_BACKUP_FILE):
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                continue
            items = payload.get("segnalazioni", []) if isinstance(payload, dict) else payload
            if not isinstance(items, list):
                continue
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                seg = Segnalazione.from_dict(raw)
                if seg is not None and seg.numero_progressivo == segnalazione_id:
                    return seg
        return None

    def _selected_existing_item(self) -> Sopralluogo | None:
        return self.find_current_edit() or self.selected_item()

    def add_selected_attachment(self, tipo: str) -> None:
        item = self._selected_existing_item()
        if item is None:
            QMessageBox.information(self, "Sopralluogo richiesto", "Salva o seleziona un sopralluogo prima di allegare file.")
            return
        seg = self._load_segnalazione(item.segnalazione_id)
        if seg is None:
            QMessageBox.warning(self, "Segnalazione non trovata", "Non trovo la segnalazione collegata a questo sopralluogo.")
            return
        title = "Scegli foto" if tipo == "foto" else "Scegli allegati"
        if tipo == "foto":
            file_filter = "Immagini (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp);;Tutti i file (*.*)"
        else:
            file_filter = "Documenti e file (*.*)"
        paths, _filter = QFileDialog.getOpenFileNames(self, title, "", file_filter)
        if not paths:
            return
        added = 0
        for filename in paths:
            try:
                add_attachment(seg, Path(filename), tipo, origine="sopralluogo", sopralluogo_id=item.id_sopralluogo)
                added += 1
            except Exception as exc:
                QMessageBox.warning(self, "Allegato non aggiunto", f"Impossibile aggiungere:\n{filename}\n\n{exc}")
        if added:
            item.presenza_foto_allegati = True
            try:
                upsert_sopralluogo(item)
            except Exception:
                pass
            log_audit_event(
                "sopralluoghi",
                "add_attachment",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Aggiunti allegati al sopralluogo",
                extra={"segnalazione_id": item.segnalazione_id, "tipo": tipo, "count": added},
            )
            self.load_items()
            self.select_item(item.id_sopralluogo)
            self.update_fascicolo_status(item)
            QMessageBox.information(self, "Allegati aggiunti", f"File aggiunti al fascicolo: {added}")

    def open_fascicolo(self) -> None:
        item = self._selected_existing_item()
        if item is None:
            QMessageBox.information(self, "Sopralluogo richiesto", "Salva o seleziona un sopralluogo prima di aprire il fascicolo.")
            return
        seg = self._load_segnalazione(item.segnalazione_id)
        if seg is None:
            QMessageBox.warning(self, "Segnalazione non trovata", "Non trovo la segnalazione collegata a questo sopralluogo.")
            return
        try:
            folder = ensure_fascicolo(seg)
            open_path(folder)
        except Exception as exc:
            QMessageBox.warning(self, "Fascicolo non aperto", f"Impossibile aprire il fascicolo.\n\n{exc}")

    def export_selected_pdf(self) -> None:
        if self.pdf_thread is not None:
            return
        item = self._selected_existing_item()
        if item is None:
            QMessageBox.information(self, "Sopralluogo richiesto", "Salva o seleziona un sopralluogo da esportare.")
            return
        seg = self._load_segnalazione(item.segnalazione_id)
        if seg is None:
            QMessageBox.warning(self, "Segnalazione non trovata", "Non trovo la segnalazione collegata a questo sopralluogo.")
            return
        if not self._is_word_available():
            QMessageBox.warning(
                self,
                "Microsoft Word non disponibile",
                "Per generare il verbale PDF e necessario Microsoft Word Desktop installato su questo PC.",
            )
            return
        try:
            SEGNALAZIONI_PDF_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        default_name = f"SOPRALLUOGO_{seg.numero_progressivo}_{item.id_sopralluogo}_{safe_pdf_filename(item.luogo)}.pdf"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Genera verbale sopralluogo",
            str(SEGNALAZIONI_PDF_DIR / default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        out_path = Path(path)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")

        self.pending_pdf_item = item
        self.pending_pdf_seg = seg
        self._set_pdf_working(True)
        self.pdf_thread = QThread(self)
        self.pdf_worker = SopralluogoPdfWorker(seg, item, out_path)
        self.pdf_worker.moveToThread(self.pdf_thread)
        self.pdf_thread.started.connect(self.pdf_worker.run)
        self.pdf_worker.finished.connect(self._pdf_done)
        self.pdf_worker.failed.connect(self._pdf_failed)
        self.pdf_worker.finished.connect(self.pdf_thread.quit)
        self.pdf_worker.failed.connect(self.pdf_thread.quit)
        self.pdf_thread.finished.connect(self.pdf_worker.deleteLater)
        self.pdf_thread.finished.connect(self._pdf_thread_finished)
        self.pdf_thread.start()

    def _pdf_done(self, path) -> None:
        item = self.pending_pdf_item
        seg = self.pending_pdf_seg
        if item is not None and seg is not None:
            try:
                add_attachment(seg, Path(path), "scheda_sopralluogo", origine="sopralluogo", sopralluogo_id=item.id_sopralluogo)
                item.presenza_foto_allegati = True
                upsert_sopralluogo(item)
                self.load_items()
                self.select_item(item.id_sopralluogo)
                self.update_fascicolo_status(item)
            except Exception:
                pass
            log_audit_event(
                "sopralluoghi",
                "export_pdf",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Generato verbale sopralluogo",
                extra={"segnalazione_id": item.segnalazione_id},
            )
        QMessageBox.information(self, "PDF creato", f"Verbale sopralluogo esportato in:\n{path}")

    def _pdf_failed(self, detail: str) -> None:
        item = self.pending_pdf_item
        if item is not None:
            log_audit_event(
                "sopralluoghi",
                "export_pdf",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Generazione verbale sopralluogo non riuscita",
                result="error",
                error=detail,
            )
        QMessageBox.critical(self, "Generazione non riuscita", f"Impossibile creare il PDF.\n\nDettagli:\n{detail}")

    def _pdf_thread_finished(self) -> None:
        self._set_pdf_working(False)
        self.pdf_thread = None
        self.pdf_worker = None
        self.pending_pdf_item = None
        self.pending_pdf_seg = None

    def _set_pdf_working(self, working: bool) -> None:
        self.pdf_button.setEnabled(not working)
        self.pdf_button.setText("PDF in corso..." if working else "Genera verbale PDF")
        self.pdf_progress.setVisible(working)

    def _is_word_available(self) -> bool:
        if self.word_available is None:
            self.word_available = check_office_com("Word.Application")[0]
        return self.word_available

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
