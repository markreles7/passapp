from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
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
from core.fascicoli import (
    PHOTO_EXTENSIONS,
    add_attachment,
    delete_attachment,
    ensure_fascicolo,
    fascicolo_exists,
    generate_photo_sheet_html,
    get_fascicolo_path,
    list_attachments,
    open_path,
    relative_to_path,
    update_attachment_description,
)


class FascicoloDialog(QDialog):
    def __init__(self, segnalazione, parent=None):
        super().__init__(parent)
        self.segnalazione = segnalazione
        self.setWindowTitle(f"Fascicolo digitale - Segnalazione n. {segnalazione.numero_progressivo}")
        self.resize(1080, 640)
        self.setMinimumSize(860, 520)

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

        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(("Tipo", "Nome file", "Data aggiunta", "Origine", "Descrizione"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.itemSelectionChanged.connect(self.update_preview)
        self.table.doubleClicked.connect(lambda _index: self.open_selected())
        splitter.addWidget(self.table)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 0, 0, 0)
        preview_layout.setSpacing(10)
        preview_title = QLabel("Dettaglio foto/allegato")
        preview_title.setStyleSheet("font-weight: 700;")
        preview_layout.addWidget(preview_title)

        self.preview_image = QLabel("Seleziona una foto per vedere l'anteprima")
        self.preview_image.setObjectName("SubPanel")
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setMinimumSize(300, 220)
        self.preview_image.setWordWrap(True)
        preview_layout.addWidget(self.preview_image)

        self.preview_meta = QLabel("")
        self.preview_meta.setObjectName("Muted")
        self.preview_meta.setWordWrap(True)
        preview_layout.addWidget(self.preview_meta)

        preview_layout.addWidget(QLabel("Descrizione / didascalia"))
        self.description_edit = QTextEdit()
        self.description_edit.setMinimumHeight(110)
        preview_layout.addWidget(self.description_edit)

        description_actions = QHBoxLayout()
        save_desc_button = QPushButton("Salva descrizione")
        save_desc_button.clicked.connect(self.save_description)
        open_button = QPushButton("Apri file")
        open_button.setProperty("secondary", "true")
        open_button.clicked.connect(self.open_selected)
        description_actions.addWidget(save_desc_button)
        description_actions.addWidget(open_button)
        description_actions.addStretch(1)
        preview_layout.addLayout(description_actions)
        preview_layout.addStretch(1)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

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
            values = (item.tipo, item.nome_file, item.data_aggiunta, origin, item.descrizione)
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(str(value))
                if column == 0:
                    table_item.setData(Qt.UserRole, item.id_allegato)
                self.table.setItem(row, column, table_item)
        self.table.resizeColumnsToContents()
        self.update_preview()

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

    def update_preview(self) -> None:
        item = self.selected_attachment()
        if item is None:
            self.preview_image.setPixmap(QPixmap())
            self.preview_image.setText("Seleziona una foto per vedere l'anteprima")
            self.preview_meta.setText("")
            self.description_edit.clear()
            self.description_edit.setEnabled(False)
            return
        self.description_edit.setEnabled(True)
        self.description_edit.setPlainText(item.descrizione)
        path = relative_to_path(item.relative_path)
        origin = item.origine
        if item.sopralluogo_id:
            origin = f"{origin} #{item.sopralluogo_id}"
        self.preview_meta.setText(
            "\n".join(
                (
                    f"Tipo: {item.tipo}",
                    f"Origine: {origin}",
                    f"File: {item.nome_file}",
                    f"Percorso: {path}",
                )
            )
        )
        if item.tipo == "foto" and path.suffix.lower() in PHOTO_EXTENSIONS and path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.preview_image.setText("")
                self.preview_image.setPixmap(pixmap.scaled(340, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.preview_image.setPixmap(QPixmap())
        self.preview_image.setText("Anteprima non disponibile per questo file")

    def save_description(self) -> None:
        item = self.selected_attachment()
        if item is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona una foto o un allegato.")
            return
        try:
            updated = update_attachment_description(
                self.segnalazione.numero_progressivo,
                item.id_allegato,
                self.description_edit.toPlainText(),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Descrizione non salvata", f"Impossibile salvare la descrizione.\n\n{exc}")
            return
        self._audit(
            "update_attachment_description",
            "Aggiornata descrizione allegato/foto",
            extra={"tipo": updated.tipo, "nome_file": updated.nome_file},
        )
        self.refresh()

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
