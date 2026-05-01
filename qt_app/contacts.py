from __future__ import annotations

import os
from pathlib import Path
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
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
from core.audit import log_audit_event
from core.contatti import (
    CONTATTI_CATEGORIE,
    Contatto,
    available_tags,
    delete_contatto,
    export_contatti_csv,
    export_contatti_txt,
    filter_contatti,
    load_contatti,
    upsert_contatto,
    validate_contatto,
)
from qt_app.widgets import page_header


class ContactsPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.contatti: list[Contatto] = []
        self.filtered: list[Contatto] = []
        self.selected_id: str | None = None
        self.fields: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(
            page_header(
                "Contatti utili",
                "Rubrica operativa per uffici, enti e riferimenti comunali.",
            )
        )

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_list_panel())
        splitter.addWidget(self._build_form_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

        self._load()

    def _build_list_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Cerca contatto")
        self.search.textChanged.connect(self.refresh_table)
        filters.addWidget(self.search, 2)

        self.category_filter = QComboBox()
        self.category_filter.addItems(("Tutte",) + CONTATTI_CATEGORIE)
        self.category_filter.currentTextChanged.connect(self.refresh_table)
        filters.addWidget(self.category_filter, 1)

        self.tag_filter = QComboBox()
        self.tag_filter.addItem("Tutti")
        self.tag_filter.currentTextChanged.connect(self.refresh_table)
        filters.addWidget(self.tag_filter, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(("Nome", "Categoria", "Telefono", "Email", "PEC", "Indirizzo"))
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 6):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.load_selected)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        for label, slot, secondary in (
            ("Nuovo", self.new_contact, False),
            ("Elimina", self.delete_selected, True),
            ("Copia telefono", lambda: self.copy_field("telefono"), True),
            ("Copia email", lambda: self.copy_field("email"), True),
            ("Copia PEC", lambda: self.copy_field("pec"), True),
        ):
            button = QPushButton(label)
            if secondary:
                button.setProperty("secondary", "true")
            button.clicked.connect(slot)
            actions.addWidget(button)

        actions.addStretch(1)
        layout.addLayout(actions)

        export_actions = QHBoxLayout()
        txt_button = QPushButton("Esporta TXT")
        csv_button = QPushButton("Esporta CSV")
        txt_button.clicked.connect(lambda: self.export_contacts(".txt"))
        csv_button.clicked.connect(lambda: self.export_contacts(".csv"))
        export_actions.addWidget(txt_button)
        export_actions.addWidget(csv_button)
        export_actions.addStretch(1)
        layout.addLayout(export_actions)

        return panel

    def _build_form_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Card")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Scheda contatto")
        title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)

        self._add_line_field(form, "nome", "Nome ente/ufficio/ditta")
        self.category = QComboBox()
        self.category.addItems(CONTATTI_CATEGORIE)
        form.addRow("Categoria", self.category)
        for key, label in (
            ("referente", "Referente"),
            ("telefono", "Telefono"),
            ("cellulare", "Cellulare"),
            ("email", "Email"),
            ("pec", "PEC"),
            ("indirizzo", "Indirizzo"),
            ("orari", "Orari"),
            ("tags", "Tags"),
            ("fonte", "Fonte"),
        ):
            self._add_line_field(form, key, label)
        layout.addLayout(form)

        layout.addWidget(QLabel("Note"))
        self.notes = QTextEdit()
        self.notes.setFixedHeight(110)
        layout.addWidget(self.notes)

        actions = QHBoxLayout()
        save_button = QPushButton("Salva")
        save_button.clicked.connect(self.save_form)
        email_button = QPushButton("Apri email")
        email_button.clicked.connect(self.open_email)
        cancel_button = QPushButton("Annulla")
        cancel_button.setProperty("secondary", "true")
        cancel_button.clicked.connect(self.new_contact)
        actions.addWidget(save_button)
        actions.addWidget(email_button)
        actions.addWidget(cancel_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addStretch(1)
        return panel

    def _add_line_field(self, form: QFormLayout, key: str, label: str) -> None:
        field = QLineEdit()
        self.fields[key] = field
        form.addRow(label, field)

    def _load(self) -> None:
        self.contatti, warning = load_contatti()
        if warning:
            if warning.startswith("Importati "):
                log_audit_event("contatti", "seed", "contatti", None, warning)
                self.status.setText(warning)
            else:
                QMessageBox.warning(self, "Archivio contatti", warning)
        self._refresh_tags()
        self.refresh_table()
        self.new_contact()

    def _refresh_tags(self) -> None:
        current = self.tag_filter.currentText() if hasattr(self, "tag_filter") else "Tutti"
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItems(("Tutti",) + available_tags(self.contatti))
        if current:
            index = self.tag_filter.findText(current)
            self.tag_filter.setCurrentIndex(index if index >= 0 else 0)
        self.tag_filter.blockSignals(False)

    def refresh_table(self) -> None:
        self.filtered = filter_contatti(
            self.contatti,
            self.search.text(),
            self.category_filter.currentText(),
            self.tag_filter.currentText(),
        )
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for contact in self.filtered:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = (contact.nome, contact.categoria, contact.telefono, contact.email, contact.pec, contact.indirizzo)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, contact.id)
                self.table.setItem(row, column, item)
        self.table.blockSignals(False)
        self.status.setText(f"Contatti visualizzati: {len(self.filtered)}")

    def new_contact(self) -> None:
        self.selected_id = None
        for field in self.fields.values():
            field.clear()
        self.category.setCurrentText("Altro")
        self.notes.clear()
        self.table.clearSelection()

    def selected_contact(self) -> Contatto | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        first_item = self.table.item(row, 0)
        if first_item is None:
            return None
        contact_id = first_item.data(Qt.UserRole)
        for contact in self.contatti:
            if contact.id == contact_id:
                return contact
        return None

    def load_selected(self) -> None:
        contact = self.selected_contact()
        if contact is None:
            return
        self.selected_id = contact.id
        self.fields["nome"].setText(contact.nome)
        self.category.setCurrentText(contact.categoria)
        self.fields["referente"].setText(contact.referente)
        self.fields["telefono"].setText(contact.telefono)
        self.fields["cellulare"].setText(contact.cellulare)
        self.fields["email"].setText(contact.email)
        self.fields["pec"].setText(contact.pec)
        self.fields["indirizzo"].setText(contact.indirizzo)
        self.fields["orari"].setText(contact.orari)
        self.fields["tags"].setText(", ".join(contact.tags or []))
        self.fields["fonte"].setText(contact.fonte)
        self.notes.setPlainText(contact.note)

    def save_form(self) -> None:
        contact = Contatto(
            id=self.selected_id or "",
            nome=self.fields["nome"].text().strip(),
            categoria=self.category.currentText().strip() or "Altro",
            referente=self.fields["referente"].text().strip(),
            telefono=self.fields["telefono"].text().strip(),
            cellulare=self.fields["cellulare"].text().strip(),
            email=self.fields["email"].text().strip(),
            pec=self.fields["pec"].text().strip(),
            indirizzo=self.fields["indirizzo"].text().strip(),
            orari=self.fields["orari"].text().strip(),
            note=self.notes.toPlainText().strip(),
            tags=[item.strip() for item in self.fields["tags"].text().split(",") if item.strip()],
            fonte=self.fields["fonte"].text().strip(),
        )
        valid, warning, soft_warning = validate_contatto(contact)
        if not valid:
            QMessageBox.warning(self, "Dati non validi", warning)
            return
        if soft_warning:
            answer = QMessageBox.question(
                self,
                "Dati da verificare",
                f"{warning}\n\nSalvare comunque?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        action = "update" if contact.id else "create"
        try:
            saved = upsert_contatto(contact)
        except Exception as exc:
            QMessageBox.critical(self, "Salvataggio non riuscito", f"Impossibile salvare il contatto.\n\n{exc}")
            return

        log_audit_event(
            "contatti",
            action,
            "contatto",
            str(saved.id),
            "Creato contatto" if action == "create" else "Modificato contatto",
        )
        self._load()
        self._select_contact(saved.id)

    def _select_contact(self, contact_id: str) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None and item.data(Qt.UserRole) == contact_id:
                self.table.selectRow(row)
                self.table.setCurrentCell(row, 0)
                return

    def delete_selected(self) -> None:
        contact = self.selected_contact()
        if contact is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un contatto da eliminare.")
            return
        answer = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Eliminare il contatto '{contact.nome}'?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if delete_contatto(contact.id):
            log_audit_event("contatti", "delete", "contatto", str(contact.id), "Eliminato contatto")
        self._load()

    def copy_field(self, field: str) -> None:
        contact = self.selected_contact()
        if contact is None:
            QMessageBox.information(self, "Selezione richiesta", "Seleziona un contatto.")
            return
        value = getattr(contact, field, "")
        if not value:
            QMessageBox.information(self, "Dato mancante", f"Il campo {field} e vuoto.")
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(value)
        self.status.setText(f"{field} copiato negli appunti")

    def open_email(self) -> None:
        email = self.fields["email"].text().strip() or self.fields["pec"].text().strip()
        if not email:
            QMessageBox.information(self, "Email mancante", "Inserisci o seleziona un indirizzo email/PEC.")
            return
        webbrowser.open(f"mailto:{email}")

    def export_contacts(self, extension: str) -> None:
        if not self.contatti:
            QMessageBox.information(self, "Nessun dato", "Non ci sono contatti da esportare.")
            return
        default_dir = resolve_path("documenti")
        default_dir.mkdir(parents=True, exist_ok=True)
        file_filter = "File TXT (*.txt)" if extension == ".txt" else "File CSV (*.csv)"
        path, _filter = QFileDialog.getSaveFileName(
            self,
            "Esporta contatti",
            str(default_dir / f"contatti_utili{extension}"),
            file_filter,
        )
        if not path:
            return
        out_path = Path(path)
        if out_path.suffix.lower() != extension:
            out_path = out_path.with_suffix(extension)
        try:
            if extension == ".txt":
                export_contatti_txt(self.contatti, out_path)
            else:
                export_contatti_csv(self.contatti, out_path)
        except Exception as exc:
            QMessageBox.critical(self, "Esportazione non riuscita", f"Impossibile esportare i contatti.\n\n{exc}")
            return
        log_audit_event(
            "contatti",
            "export",
            "contatti",
            None,
            "Esportata lista contatti",
            extra={"format": out_path.suffix.lower()},
        )
        if os.name == "nt":
            try:
                os.startfile(out_path)  # type: ignore[attr-defined]
            except OSError:
                pass
        QMessageBox.information(self, "Esportazione completata", f"Contatti esportati in:\n{out_path}")
