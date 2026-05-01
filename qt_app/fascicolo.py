from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.audit import log_audit_event
from core.fascicoli import (
    add_attachment,
    delete_attachment,
    ensure_fascicolo,
    fascicolo_exists,
    generate_photo_sheet_html,
    get_fascicolo_path,
    list_attachments,
    open_path,
    relative_to_path,
)


class FascicoloDialog(QDialog):
    def __init__(self, segnalazione, parent=None):
        super().__init__(parent)
        self.segnalazione = segnalazione
        self.setWindowTitle(f"Fascicolo digitale - Segnalazione n. {segnalazione.numero_progressivo}")
        self.resize(920, 560)
        self.setMinimumSize(760, 460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(f"Fascicolo digitale - Segnalazione n. {segnalazione.numero_progressivo}")
        title.setStyleSheet("font-size: 15pt; font-weight: 700;")
        layout.addWidget(title)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        actions = QHBoxLayout()
        for label, slot, secondary in (
            ("Crea/Verifica fascicolo", self.create_fascicolo, False),
            ("Apri fascicolo", self.open_fascicolo, True),
            ("Aggiungi foto", lambda: self.add_files("foto"), True),
            ("Aggiungi allegato", lambda: self.add_files("allegato"), True),
            ("Apri file", self.open_selected, True),
            ("Elimina allegato", self.delete_selected, True),
            ("Scheda foto", self.generate_photo_sheet, True),
        ):
            button = QPushButton(label)
            if secondary:
                button.setProperty("secondary", "true")
            button.clicked.connect(slot)
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Tipo", "Nome file", "Data aggiunta", "Origine"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.doubleClicked.connect(lambda _index: self.open_selected())
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        close_button = QPushButton("Chiudi")
        close_button.setProperty("secondary", "true")
        close_button.clicked.connect(self.accept)
        footer.addStretch(1)
        footer.addWidget(close_button)
        layout.addLayout(footer)

        self.refresh()

    def refresh(self) -> None:
        folder = get_fascicolo_path(self.segnalazione.numero_progressivo)
        exists = bool(folder and folder.exists())
        attachments = list_attachments(self.segnalazione.numero_progressivo)
        if exists:
            self.status.setText(f"Fascicolo: presente - {folder} - Allegati: {len(attachments)}")
        elif folder:
            self.status.setText(f"Fascicolo: registrato, cartella mancante - {folder} - Allegati: {len(attachments)}")
        else:
            self.status.setText(f"Fascicolo: non creato - Allegati: {len(attachments)}")

        self.table.setRowCount(0)
        for item in attachments:
            row = self.table.rowCount()
            self.table.insertRow(row)
            origin = item.origine
            if item.sopralluogo_id:
                origin = f"{origin} #{item.sopralluogo_id}"
            values = (item.tipo, item.nome_file, item.data_aggiunta, origin)
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                if column == 0:
                    table_item.setData(Qt.UserRole, item.id_allegato)
                self.table.setItem(row, column, table_item)
        self.table.resizeColumnsToContents()

    def selected_attachment(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        selected_id = int(item.data(Qt.UserRole))
        for attachment in list_attachments(self.segnalazione.numero_progressivo):
            if attachment.id_allegato == selected_id:
                return attachment
        return None

    def create_fascicolo(self) -> None:
        try:
            folder = ensure_fascicolo(self.segnalazione)
        except Exception as exc:
            self._audit("create_fascicolo", "Creazione fascicolo non riuscita", result="error", error=str(exc))
            QMessageBox.critical(self, "Fascicolo non creato", f"Impossibile creare il fascicolo.\n\n{exc}")
            return
        self._audit("create_fascicolo", "Creato/aperto fascicolo digitale")
        self.refresh()
        QMessageBox.information(self, "Fascicolo creato", f"Fascicolo disponibile in:\n{folder}")

    def open_fascicolo(self) -> None:
        try:
            folder = ensure_fascicolo(self.segnalazione)
            open_path(folder)
        except Exception as exc:
            QMessageBox.critical(self, "Apertura non riuscita", f"Impossibile aprire il fascicolo.\n\n{exc}")
            return
        self.refresh()

    def add_files(self, tipo: str) -> None:
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
                add_attachment(self.segnalazione, Path(filename), tipo, origine="segnalazione")
                added += 1
            except Exception as exc:
                self._audit("add_attachment", "Aggiunta allegato/foto non riuscita", result="error", error=str(exc))
        if added:
            self._audit("add_attachment", "Aggiunti allegati/foto al fascicolo", extra={"count": added, "tipo": tipo})
        self.refresh()
        QMessageBox.information(self, "Fascicolo aggiornato", f"File aggiunti: {added}")

    def open_selected(self) -> None:
        item = self.selected_attachment()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un file da aprire.")
            return
        try:
            open_path(relative_to_path(item.relative_path))
        except Exception as exc:
            QMessageBox.critical(self, "Apertura non riuscita", f"Impossibile aprire il file.\n\n{exc}")

    def delete_selected(self) -> None:
        item = self.selected_attachment()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un allegato da eliminare.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Eliminare dal fascicolo il file:\n{item.nome_file}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            removed = delete_attachment(self.segnalazione.numero_progressivo, item.id_allegato)
        except Exception as exc:
            self._audit("delete_attachment", "Eliminazione allegato/foto non riuscita", result="error", error=str(exc))
            QMessageBox.critical(self, "Eliminazione non riuscita", f"Impossibile eliminare l'allegato.\n\n{exc}")
            return
        self._audit(
            "delete_attachment",
            "Eliminato allegato/foto dal fascicolo",
            extra={"tipo": removed.tipo, "nome_file": removed.nome_file},
        )
        self.refresh()

    def generate_photo_sheet(self) -> None:
        try:
            output = generate_photo_sheet_html(self.segnalazione)
            open_path(output)
        except Exception as exc:
            QMessageBox.critical(self, "Scheda non creata", f"Impossibile generare la scheda fotografica.\n\n{exc}")
            return
        self.refresh()

    def _audit(self, action: str, description: str, **kwargs) -> None:
        log_audit_event(
            "segnalazioni",
            action,
            "fascicolo",
            f"SEG-{self.segnalazione.anno}-{self.segnalazione.numero_progressivo:04d}",
            description,
            **kwargs,
        )
