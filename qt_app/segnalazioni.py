from __future__ import annotations

from dataclasses import asdict
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.fascicoli import (
    add_attachment,
    ensure_fascicolo,
    fascicolo_exists,
    generate_photo_sheet_html,
    get_fascicolo_path,
    list_attachments,
    open_path,
)
import segnalazioni as segn_mod
from segnalazioni import (
    CATEGORIA_DEFAULT,
    CATEGORIA_OPZIONI,
    MODALITA_OPZIONI,
    PRIORITA_DEFAULT,
    PRIORITA_OPZIONI,
    STATO_LAVORAZIONE_DEFAULT,
    STATO_LAVORAZIONE_OPZIONI,
    Segnalazione,
    normalize_categoria,
    normalize_priorita,
    normalize_stato_lavorazione,
    segnalazione_matches_filters,
    segnalazione_sort_key,
)
from qt_app.fascicolo import FascicoloDialog
from qt_app.segnalazioni_pdf import build_pdf_payload, safe_pdf_filename
from qt_app.widgets import page_header
from qt_app.workers import SegnalazionePdfWorker


class SegnalazioniPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.segnalazioni: list[Segnalazione] = []
        self.next_progressivo = 1
        self.selected_numero: int | None = None
        self.selected_stato: str | None = None
        self.fields: dict[str, QLineEdit] = {}
        self.pdf_thread: QThread | None = None
        self.pdf_worker: SegnalazionePdfWorker | None = None
        self.pending_pdf_seg: Segnalazione | None = None
        self.pending_pdf_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header("Segnalazioni", "Gestione segnalazioni, verifiche e stato lavorazione."))

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        self.load_from_disk()
        self.refresh_tables()
        self.clear_detail()

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        filters = QGridLayout()
        filters.setHorizontalSpacing(10)
        filters.setVerticalSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca segnalazione")
        self.search.textChanged.connect(self.refresh_tables)
        filters.addWidget(self.search, 0, 0, 1, 3)

        self.category_filter = QComboBox()
        self.category_filter.addItems(("Tutte",) + CATEGORIA_OPZIONI)
        self.category_filter.currentTextChanged.connect(self.refresh_tables)
        filters.addWidget(self.category_filter, 1, 0)

        self.priority_filter = QComboBox()
        self.priority_filter.addItems(("Tutte",) + PRIORITA_OPZIONI)
        self.priority_filter.currentTextChanged.connect(self.refresh_tables)
        filters.addWidget(self.priority_filter, 1, 1)

        self.status_filter = QComboBox()
        self.status_filter.addItems(("Tutti",) + STATO_LAVORAZIONE_OPZIONI)
        self.status_filter.currentTextChanged.connect(self.refresh_tables)
        filters.addWidget(self.status_filter, 1, 2)

        self.only_urgent = QCheckBox("Solo urgenti")
        self.only_urgent.stateChanged.connect(self.refresh_tables)
        self.only_open = QCheckBox("Solo aperte")
        self.only_open.stateChanged.connect(self.refresh_tables)
        flags = QHBoxLayout()
        flags.addWidget(self.only_urgent)
        flags.addWidget(self.only_open)
        flags.addStretch(1)
        filters.addLayout(flags, 2, 0, 1, 3)
        layout.addLayout(filters)

        actions = QHBoxLayout()
        new_button = QPushButton("Nuova segnalazione")
        new_button.clicked.connect(self.new_report)
        delete_button = QPushButton("Elimina")
        delete_button.setProperty("secondary", "true")
        delete_button.clicked.connect(self.delete_selected)
        actions.addWidget(new_button)
        actions.addWidget(delete_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.tabs = QTabWidget()
        self.open_table = self._build_table("in_corso")
        self.closed_table = self._build_table("archiviata")
        self.tabs.addTab(self.open_table, "In corso")
        self.tabs.addTab(self.closed_table, "Archiviate")
        layout.addWidget(self.tabs, 1)
        return panel

    def _build_table(self, stato: str) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(("N.", "Data", "Priorita", "Categoria", "Stato", "Nominativo"))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.itemSelectionChanged.connect(lambda table=table, stato=stato: self.on_select(table, stato))
        return table

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Dettaglio segnalazione")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        for key, label in (
            ("numero", "Numero"),
            ("anno", "Anno"),
            ("mese", "Mese"),
            ("giorno", "Giorno"),
            ("ora", "Ora"),
            ("nominativo", "Nominativo"),
            ("residenza", "Residenza"),
            ("indirizzo", "Indirizzo"),
            ("telefono", "Telefono"),
            ("ricevente", "Ricevente"),
            ("agente", "Agente verificatore"),
            ("data_verifica", "Data verifica"),
            ("stato", "Stato record"),
        ):
            field = QLineEdit()
            self.fields[key] = field
            form.addRow(label, field)

        self.fields["numero"].setReadOnly(True)
        self.fields["stato"].setReadOnly(True)

        self.modalita = QComboBox()
        self.modalita.addItems(MODALITA_OPZIONI)
        form.addRow("Modalita", self.modalita)

        self.categoria = QComboBox()
        self.categoria.addItems(CATEGORIA_OPZIONI)
        form.addRow("Categoria", self.categoria)

        self.priorita = QComboBox()
        self.priorita.addItems(PRIORITA_OPZIONI)
        form.addRow("Priorita", self.priorita)

        self.stato_lavorazione = QComboBox()
        self.stato_lavorazione.addItems(STATO_LAVORAZIONE_OPZIONI)
        form.addRow("Stato lavorazione", self.stato_lavorazione)
        layout.addLayout(form)

        layout.addWidget(QLabel("Descrizione segnalazione"))
        self.descrizione = QTextEdit()
        self.descrizione.setFixedHeight(100)
        layout.addWidget(self.descrizione)

        layout.addWidget(QLabel("Verifica effettuata"))
        self.verifica = QTextEdit()
        self.verifica.setFixedHeight(100)
        layout.addWidget(self.verifica)

        fascicolo_box = QFrame()
        fascicolo_box.setObjectName("SubPanel")
        fascicolo_layout = QVBoxLayout(fascicolo_box)
        fascicolo_layout.setContentsMargins(12, 12, 12, 12)
        fascicolo_layout.setSpacing(8)
        self.fascicolo_status = QLabel("Fascicolo: non creato")
        self.fascicolo_status.setObjectName("Muted")
        fascicolo_layout.addWidget(self.fascicolo_status)
        fascicolo_actions = QHBoxLayout()
        for label, slot, secondary in (
            ("Crea/Verifica", self.create_fascicolo, False),
            ("Apri", self.open_fascicolo, True),
            ("Aggiungi foto", lambda: self.add_fascicolo_files("foto"), True),
            ("Aggiungi allegato", lambda: self.add_fascicolo_files("allegato"), True),
            ("Scheda foto", self.generate_photo_sheet, True),
            ("Gestisci", self.show_fascicolo_dialog, True),
        ):
            button = QPushButton(label)
            if secondary:
                button.setProperty("secondary", "true")
            button.clicked.connect(slot)
            fascicolo_actions.addWidget(button)
        fascicolo_actions.addStretch(1)
        fascicolo_layout.addLayout(fascicolo_actions)
        layout.addWidget(fascicolo_box)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Salva")
        self.save_button.clicked.connect(self.save_current)
        self.close_button = QPushButton("Archivia")
        self.close_button.clicked.connect(self.close_current)
        self.close_button.setProperty("danger", "true")
        self.pdf_button = QPushButton("Esporta PDF")
        self.pdf_button.clicked.connect(self.export_selected_pdf)
        clear_button = QPushButton("Annulla")
        clear_button.setProperty("secondary", "true")
        clear_button.clicked.connect(self.clear_detail)
        self.pdf_progress = QProgressBar()
        self.pdf_progress.setRange(0, 0)
        self.pdf_progress.setFixedWidth(120)
        self.pdf_progress.hide()
        actions.addWidget(self.save_button)
        actions.addWidget(self.close_button)
        actions.addWidget(self.pdf_button)
        actions.addWidget(clear_button)
        actions.addStretch(1)
        actions.addWidget(self.pdf_progress)
        layout.addLayout(actions)
        layout.addStretch(1)
        return panel

    def load_from_disk(self) -> None:
        self.segnalazioni = []
        self.next_progressivo = 1
        payload = self._read_payload_file(segn_mod.SEGNALAZIONI_FILE)
        if payload is None:
            payload = self._read_payload_file(segn_mod.SEGNALAZIONI_BACKUP_FILE)
        if payload is None:
            return
        items = payload.get("segnalazioni", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            return
        max_progressivo = 0
        for raw in items:
            if not isinstance(raw, dict):
                continue
            seg = Segnalazione.from_dict(raw)
            if seg is None:
                continue
            self.segnalazioni.append(seg)
            max_progressivo = max(max_progressivo, seg.numero_progressivo)
        self.segnalazioni.sort(key=lambda item: item.numero_progressivo)
        self.next_progressivo = max_progressivo + 1 if max_progressivo > 0 else 1

    def _read_payload_file(self, path: Path):
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, (dict, list)) else None

    def save_to_disk(self) -> bool:
        tmp_path: Path | None = None
        try:
            target = segn_mod.SEGNALAZIONI_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = {"segnalazioni": [asdict(seg) for seg in self.segnalazioni]}
            tmp_fd, tmp_name = tempfile.mkstemp(prefix="segnalazioni_", suffix=".tmp", dir=str(target.parent))
            tmp_path = Path(tmp_name)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            if target.exists():
                try:
                    shutil.copyfile(target, segn_mod.SEGNALAZIONI_BACKUP_FILE)
                except OSError:
                    pass
            os.replace(tmp_path, target)
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Salvataggio non riuscito", f"Impossibile salvare il file segnalazioni.\n\n{exc}")
            return False
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def refresh_tables(self) -> None:
        self._fill_table(self.open_table, "in_corso")
        self._fill_table(self.closed_table, "archiviata")
        open_count = sum(1 for item in self.segnalazioni if item.stato == "in_corso")
        closed_count = sum(1 for item in self.segnalazioni if item.stato == "archiviata")
        self.tabs.setTabText(0, f"In corso ({open_count})")
        self.tabs.setTabText(1, f"Archiviate ({closed_count})")
        self.status.setText(f"Segnalazioni: {open_count} in corso, {closed_count} archiviate")

    def _fill_table(self, table: QTableWidget, stato: str) -> None:
        query = self.search.text().strip().lower()
        table.blockSignals(True)
        table.setRowCount(0)
        for seg in sorted(self.segnalazioni, key=segnalazione_sort_key):
            if seg.stato != stato:
                continue
            if not segnalazione_matches_filters(
                seg,
                query=query,
                categoria=self.category_filter.currentText(),
                priorita=self.priority_filter.currentText(),
                stato_lavorazione=self.status_filter.currentText(),
                solo_urgenti=self.only_urgent.isChecked(),
                solo_aperte=self.only_open.isChecked(),
            ):
                continue
            row = table.rowCount()
            table.insertRow(row)
            values = (
                str(seg.numero_progressivo),
                f"{seg.giorno}/{seg.mese}/{seg.anno}",
                seg.priorita,
                seg.categoria,
                seg.stato_lavorazione,
                seg.nominativo or "-",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, seg.numero_progressivo)
                table.setItem(row, column, item)
        table.blockSignals(False)
        table.resizeColumnsToContents()

    def on_select(self, table: QTableWidget, stato: str) -> None:
        row = table.currentRow()
        if row < 0:
            return
        item = table.item(row, 0)
        if item is None:
            return
        numero = item.data(Qt.UserRole)
        self.select_report(int(numero), stato)

    def select_report(self, numero: int, stato: str) -> None:
        seg = self.find_report(numero, stato)
        if seg is None:
            return
        self.selected_numero = numero
        self.selected_stato = stato
        self.load_detail(seg)

    def find_report(self, numero: int, stato: str) -> Segnalazione | None:
        for seg in self.segnalazioni:
            if seg.numero_progressivo == numero and seg.stato == stato:
                return seg
        return None

    def selected_report(self) -> Segnalazione | None:
        if self.selected_numero is None or self.selected_stato is None:
            return None
        return self.find_report(self.selected_numero, self.selected_stato)

    def load_detail(self, seg: Segnalazione) -> None:
        self.fields["numero"].setText(str(seg.numero_progressivo))
        self.fields["anno"].setText(seg.anno)
        self.fields["mese"].setText(seg.mese)
        self.fields["giorno"].setText(seg.giorno)
        self.fields["ora"].setText(seg.ora)
        self.fields["nominativo"].setText(seg.nominativo)
        self.fields["residenza"].setText(seg.residenza)
        self.fields["indirizzo"].setText(seg.indirizzo)
        self.fields["telefono"].setText(seg.telefono)
        self.fields["ricevente"].setText(seg.ricevente)
        self.fields["agente"].setText(seg.agente_verificatore)
        self.fields["data_verifica"].setText(seg.data_verifica)
        self.fields["stato"].setText(seg.stato)
        self.modalita.setCurrentText(seg.modalita_segnalazione or MODALITA_OPZIONI[0])
        self.categoria.setCurrentText(normalize_categoria(seg.categoria))
        self.priorita.setCurrentText(normalize_priorita(seg.priorita))
        self.stato_lavorazione.setCurrentText(normalize_stato_lavorazione(seg.stato_lavorazione, seg.stato))
        self.descrizione.setPlainText(seg.descrizione_segnalazione)
        self.verifica.setPlainText(seg.verifica_effettuata)
        self._set_form_editable(seg.stato == "in_corso")
        self.update_fascicolo_status()

    def clear_detail(self) -> None:
        self.selected_numero = None
        self.selected_stato = None
        for field in self.fields.values():
            field.clear()
        self.modalita.setCurrentText(MODALITA_OPZIONI[0])
        self.categoria.setCurrentText(CATEGORIA_DEFAULT)
        self.priorita.setCurrentText(PRIORITA_DEFAULT)
        self.stato_lavorazione.setCurrentText(STATO_LAVORAZIONE_DEFAULT)
        self.descrizione.clear()
        self.verifica.clear()
        self.open_table.clearSelection()
        self.closed_table.clearSelection()
        self._set_form_editable(False)
        self.fascicolo_status.setText("Fascicolo: non creato")

    def _set_form_editable(self, editable: bool) -> None:
        for key, field in self.fields.items():
            if key not in {"numero", "stato"}:
                field.setReadOnly(not editable)
        for widget in (self.modalita, self.categoria, self.priorita, self.stato_lavorazione, self.descrizione, self.verifica):
            widget.setEnabled(editable)
        self.save_button.setEnabled(editable)
        self.close_button.setEnabled(editable)
        self.pdf_button.setEnabled(self.selected_report() is not None and self.pdf_thread is None)

    def new_report(self) -> None:
        now = dt.datetime.now()
        seg = Segnalazione(
            numero_progressivo=self.next_progressivo,
            anno=f"{now.year}",
            mese=f"{now.month:02d}",
            giorno=f"{now.day:02d}",
            ora=f"{now.hour:02d}:{now.minute:02d}",
            stato="in_corso",
        )
        self.next_progressivo += 1
        self.segnalazioni.append(seg)
        if self.save_to_disk():
            log_audit_event(
                "segnalazioni",
                "create",
                "segnalazione",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Creata nuova segnalazione",
            )
        self.refresh_tables()
        self.tabs.setCurrentWidget(self.open_table)
        self.select_report(seg.numero_progressivo, "in_corso")

    def validate_form(self) -> tuple[bool, str]:
        anno = self.fields["anno"].text().strip()
        mese = self.fields["mese"].text().strip()
        giorno = self.fields["giorno"].text().strip()
        ora = self.fields["ora"].text().strip()
        nominativo = self.fields["nominativo"].text().strip()
        descrizione = self.descrizione.toPlainText().strip()
        ricevente = self.fields["ricevente"].text().strip()
        if not anno or not mese or not giorno:
            return False, "Compila Anno, Mese e Giorno."
        try:
            dt.date(int(anno), int(mese), int(giorno))
        except (TypeError, ValueError):
            return False, "La data non e valida."
        try:
            dt.datetime.strptime(ora, "%H:%M")
        except ValueError:
            return False, "L'ora non e valida. Usa il formato HH:MM."
        if not nominativo:
            return False, "Il campo Nominativo e obbligatorio."
        if not descrizione:
            return False, "Il campo Segnala e obbligatorio."
        if not ricevente:
            return False, "Il campo Ricevente e obbligatorio."
        return True, ""

    def save_current(self) -> bool:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione da modificare.")
            return False
        if seg.stato != "in_corso":
            QMessageBox.information(self, "Archivio", "Le segnalazioni archiviate sono in sola lettura.")
            return False
        valid, reason = self.validate_form()
        if not valid:
            QMessageBox.warning(self, "Dati non validi", reason)
            return False

        old_status = seg.stato_lavorazione
        old_priority = seg.priorita
        old_category = seg.categoria

        seg.anno = self.fields["anno"].text().strip()
        seg.mese = self.fields["mese"].text().strip()
        seg.giorno = self.fields["giorno"].text().strip()
        seg.ora = self.fields["ora"].text().strip()
        seg.nominativo = self.fields["nominativo"].text().strip()
        seg.residenza = self.fields["residenza"].text().strip()
        seg.indirizzo = self.fields["indirizzo"].text().strip()
        seg.telefono = self.fields["telefono"].text().strip()
        seg.modalita_segnalazione = self.modalita.currentText()
        seg.ricevente = self.fields["ricevente"].text().strip()
        seg.agente_verificatore = self.fields["agente"].text().strip()
        seg.data_verifica = self.fields["data_verifica"].text().strip()
        seg.descrizione_segnalazione = self.descrizione.toPlainText().strip()
        seg.verifica_effettuata = self.verifica.toPlainText().strip()
        seg.categoria = normalize_categoria(self.categoria.currentText())
        seg.priorita = normalize_priorita(self.priorita.currentText())
        seg.stato_lavorazione = normalize_stato_lavorazione(self.stato_lavorazione.currentText(), seg.stato)

        if not self.save_to_disk():
            return False
        log_audit_event(
            "segnalazioni",
            "update",
            "segnalazione",
            f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
            "Modificata segnalazione",
            extra={
                "categoria": f"{old_category} -> {seg.categoria}" if old_category != seg.categoria else seg.categoria,
                "priorita": f"{old_priority} -> {seg.priorita}" if old_priority != seg.priorita else seg.priorita,
            },
        )
        if old_status != seg.stato_lavorazione:
            log_audit_event(
                "segnalazioni",
                "status_change",
                "segnalazione",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Cambio stato lavorazione segnalazione",
                extra={"from": old_status, "to": seg.stato_lavorazione},
            )
        self.refresh_tables()
        self.select_report(seg.numero_progressivo, seg.stato)
        return True

    def close_current(self) -> None:
        seg = self.selected_report()
        if seg is None or seg.stato != "in_corso":
            return
        if not self.save_current():
            return
        if not seg.agente_verificatore.strip():
            QMessageBox.warning(self, "Dati incompleti", "Compila il campo Agente verificatore prima di archiviare.")
            return
        if not seg.verifica_effettuata.strip():
            QMessageBox.warning(self, "Dati incompleti", "Compila il campo Verifica effettuata prima di archiviare.")
            return
        if not seg.data_verifica.strip():
            seg.data_verifica = dt.date.today().strftime("%d/%m/%Y")
        seg.stato = "archiviata"
        seg.stato_lavorazione = "Archiviata"
        if not self.save_to_disk():
            return
        log_audit_event(
            "segnalazioni",
            "close",
            "segnalazione",
            f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
            "Chiusa/archiviata segnalazione",
        )
        self.refresh_tables()
        self.tabs.setCurrentWidget(self.closed_table)
        self.select_report(seg.numero_progressivo, "archiviata")

    def delete_selected(self) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione da eliminare.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Eliminare la segnalazione n. {seg.numero_progressivo}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.segnalazioni = [item for item in self.segnalazioni if item.numero_progressivo != seg.numero_progressivo]
        if self.save_to_disk():
            log_audit_event(
                "segnalazioni",
                "delete",
                "segnalazione",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Eliminata segnalazione",
            )
        self.refresh_tables()
        self.clear_detail()

    def update_fascicolo_status(self) -> None:
        seg = self.selected_report()
        if seg is None:
            self.fascicolo_status.setText("Fascicolo: non creato")
            return
        try:
            path = get_fascicolo_path(seg.numero_progressivo)
            attachments = list_attachments(seg.numero_progressivo)
            if fascicolo_exists(seg.numero_progressivo):
                self.fascicolo_status.setText(f"Fascicolo: presente - {path} - Allegati: {len(attachments)}")
            elif path:
                self.fascicolo_status.setText(f"Fascicolo: registrato, cartella mancante - {path} - Allegati: {len(attachments)}")
            else:
                self.fascicolo_status.setText(f"Fascicolo: non creato - Allegati: {len(attachments)}")
        except Exception:
            self.fascicolo_status.setText("Fascicolo: errore lettura")

    def create_fascicolo(self) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            folder = ensure_fascicolo(seg)
        except Exception as exc:
            log_audit_event(
                "segnalazioni",
                "create_fascicolo",
                "fascicolo",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Creazione fascicolo non riuscita",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Fascicolo non creato", f"Impossibile creare il fascicolo.\n\n{exc}")
            return
        log_audit_event(
            "segnalazioni",
            "create_fascicolo",
            "fascicolo",
            f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
            "Creato/aperto fascicolo digitale",
        )
        self.update_fascicolo_status()
        QMessageBox.information(self, "Fascicolo creato", f"Fascicolo disponibile in:\n{folder}")

    def open_fascicolo(self) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            folder = ensure_fascicolo(seg)
            open_path(folder)
        except Exception as exc:
            QMessageBox.critical(self, "Apertura non riuscita", f"Impossibile aprire il fascicolo.\n\n{exc}")
            return
        self.update_fascicolo_status()

    def add_fascicolo_files(self, tipo: str) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione.")
            return
        if tipo == "foto":
            title = "Aggiungi foto al fascicolo"
            file_filter = "Immagini (*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp);;Tutti i file (*.*)"
        else:
            title = "Aggiungi allegato al fascicolo"
            file_filter = "Tutti i file (*.*)"
        files, _filter = QFileDialog.getOpenFileNames(self, title, "", file_filter)
        if not files:
            return
        added = 0
        for filename in files:
            try:
                add_attachment(seg, Path(filename), tipo, origine="segnalazione")
                added += 1
            except Exception as exc:
                log_audit_event(
                    "segnalazioni",
                    "add_attachment",
                    "fascicolo",
                    f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                    "Aggiunta allegato/foto non riuscita",
                    result="error",
                    error=str(exc),
                )
        if added:
            log_audit_event(
                "segnalazioni",
                "add_attachment",
                "fascicolo",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Aggiunti allegati/foto al fascicolo",
                extra={"count": added, "tipo": tipo},
            )
        self.update_fascicolo_status()
        QMessageBox.information(self, "Fascicolo aggiornato", f"File aggiunti: {added}")

    def generate_photo_sheet(self) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            output = generate_photo_sheet_html(seg)
            open_path(output)
        except Exception as exc:
            QMessageBox.critical(self, "Scheda non creata", f"Impossibile generare la scheda fotografica.\n\n{exc}")
            return
        self.update_fascicolo_status()

    def show_fascicolo_dialog(self) -> None:
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione.")
            return
        dialog = FascicoloDialog(seg, self)
        dialog.exec()
        self.update_fascicolo_status()

    def snapshot_current_form(self, seg: Segnalazione) -> Segnalazione:
        return Segnalazione(
            numero_progressivo=seg.numero_progressivo,
            anno=self.fields["anno"].text().strip() or seg.anno,
            mese=self.fields["mese"].text().strip() or seg.mese,
            giorno=self.fields["giorno"].text().strip() or seg.giorno,
            ora=self.fields["ora"].text().strip() or seg.ora,
            nominativo=self.fields["nominativo"].text().strip() or seg.nominativo,
            residenza=self.fields["residenza"].text().strip() or seg.residenza,
            indirizzo=self.fields["indirizzo"].text().strip() or seg.indirizzo,
            telefono=self.fields["telefono"].text().strip() or seg.telefono,
            modalita_segnalazione=self.modalita.currentText().strip() or seg.modalita_segnalazione,
            descrizione_segnalazione=self.descrizione.toPlainText().strip() or seg.descrizione_segnalazione,
            ricevente=self.fields["ricevente"].text().strip() or seg.ricevente,
            agente_verificatore=self.fields["agente"].text().strip() or seg.agente_verificatore,
            verifica_effettuata=self.verifica.toPlainText().strip() or seg.verifica_effettuata,
            data_verifica=self.fields["data_verifica"].text().strip() or seg.data_verifica,
            categoria=normalize_categoria(self.categoria.currentText() or seg.categoria),
            priorita=normalize_priorita(self.priorita.currentText() or seg.priorita),
            stato_lavorazione=normalize_stato_lavorazione(self.stato_lavorazione.currentText() or seg.stato_lavorazione, seg.stato),
            stato=seg.stato,
        )

    def export_selected_pdf(self) -> None:
        if self.pdf_thread is not None:
            return
        seg = self.selected_report()
        if seg is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una segnalazione da esportare in PDF.")
            return

        try:
            segn_mod.SEGNALAZIONI_PDF_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        default_name = f"SEGNALAZIONE_{seg.numero_progressivo}_{safe_pdf_filename(seg.nominativo)}.pdf"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Salva segnalazione in PDF",
            str(segn_mod.SEGNALAZIONI_PDF_DIR / default_name),
            "PDF (*.pdf)",
        )
        if not path:
            return
        out_path = Path(path)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")

        snapshot = self.snapshot_current_form(seg)
        payload = build_pdf_payload(snapshot)
        self.pending_pdf_seg = seg
        self.pending_pdf_path = out_path
        self._set_pdf_working(True)

        self.pdf_thread = QThread(self)
        self.pdf_worker = SegnalazionePdfWorker(payload, out_path)
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
        seg = self.pending_pdf_seg
        if seg is not None:
            try:
                add_attachment(seg, Path(path), "documento", origine="segnalazione")
                self.update_fascicolo_status()
            except Exception:
                pass
            log_audit_event(
                "segnalazioni",
                "export_pdf",
                "segnalazione",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Generato PDF segnalazione",
            )
        QMessageBox.information(self, "PDF creato", f"Segnalazione esportata in:\n{path}")

    def _pdf_failed(self, detail: str) -> None:
        seg = self.pending_pdf_seg
        if seg is not None:
            log_audit_event(
                "segnalazioni",
                "export_pdf",
                "segnalazione",
                f"SEG-{seg.anno}-{seg.numero_progressivo:04d}",
                "Generazione PDF segnalazione non riuscita",
                result="error",
                error=detail,
            )
        QMessageBox.critical(self, "Esportazione non riuscita", f"Impossibile creare il PDF.\n\nDettagli:\n{detail}")

    def _pdf_thread_finished(self) -> None:
        self._set_pdf_working(False)
        self.pdf_thread = None
        self.pdf_worker = None
        self.pending_pdf_seg = None
        self.pending_pdf_path = None

    def _set_pdf_working(self, working: bool) -> None:
        self.pdf_button.setEnabled(not working and self.selected_report() is not None)
        self.pdf_button.setText("PDF in corso..." if working else "Esporta PDF")
        self.pdf_progress.setVisible(working)
        self.setCursor(Qt.WaitCursor if working else Qt.ArrowCursor)
