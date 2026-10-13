from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QInputDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.auth import AuthenticatedUser
from core.fascicoli import add_attachment
from core.segnalazioni import load_segnalazioni
from services.ai.action_engine import ActionEngine
from services.ai.audit import log_ai_interaction
from services.ai.exceptions import AIServiceError
from services.ai.schemas import OperationalCommand
from services.ai.prompts import PROMPT_VERSION
from services.ai.validators import extract_json_object
from qt_app.widgets import page_header
from qt_app.workers import OperationalAssistantWorker


INTENT_LABELS = {
    "create_report": "Crea segnalazione",
    "create_inspection": "Crea sopralluogo",
    "create_report_and_inspection": "Crea segnalazione e sopralluogo",
    "update_report": "Aggiorna segnalazione",
    "update_inspection": "Aggiorna sopralluogo",
    "generate_inspection_document": "Prepara verbale di sopralluogo",
    "attach_photos": "Allega fotografie",
    "add_note": "Aggiungi nota",
    "create_reminder": "Crea promemoria",
    "search_case": "Cerca pratica",
    "unknown": "Comando non riconosciuto",
}


class OperationalAssistantPage(QWidget):
    open_sopralluogo_requested = Signal(int)

    def __init__(self, config: dict, current_user: AuthenticatedUser | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.current_user = current_user
        self.analysis = None
        self.thread: QThread | None = None
        self.worker: OperationalAssistantWorker | None = None
        self.engine = ActionEngine()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(page_header("Assistente Operativo", "Descrivi cio che e accaduto o l'attivita da eseguire."))

        input_card = QFrame()
        input_card.setObjectName("Card")
        input_layout = QVBoxLayout(input_card)
        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("Es.: La signora Rossi segnala una buca in via Roma 11 da controllare...")
        self.input_text.setMinimumHeight(100)
        input_layout.addWidget(self.input_text)
        input_buttons = QHBoxLayout()
        self.status = QLabel(f"ChatGPT: {config.get('ai', {}).get('model', 'automatico dal tuo account')}")
        self.status.setObjectName("Muted")
        self.analyze_button = QPushButton("Analizza con ChatGPT")
        self.analyze_button.clicked.connect(self.analyze)
        input_buttons.addWidget(self.status)
        input_buttons.addStretch(1)
        input_buttons.addWidget(self.analyze_button)
        input_layout.addLayout(input_buttons)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        input_layout.addWidget(self.progress)
        layout.addWidget(input_card)

        result_card = QFrame()
        result_card.setObjectName("Card")
        result_layout = QVBoxLayout(result_card)
        self.result_title = QLabel("Nessuna analisi disponibile")
        self.result_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
        result_layout.addWidget(self.result_title)
        self.actions = QListWidget()
        self.actions.setMinimumHeight(90)
        result_layout.addWidget(QLabel("Azioni proposte"))
        result_layout.addWidget(self.actions)
        result_layout.addWidget(QLabel("Dati estratti (JSON validato)"))
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        result_layout.addWidget(self.result_text, 1)
        controls = QHBoxLayout()
        self.modify_button = QPushButton("Modifica")
        self.cancel_button = QPushButton("Annulla")
        self.confirm_button = QPushButton("Conferma operazioni")
        self.modify_button.clicked.connect(self.enable_edit)
        self.cancel_button.clicked.connect(self.cancel)
        self.confirm_button.clicked.connect(self.confirm)
        for button in (self.modify_button, self.cancel_button, self.confirm_button):
            button.setEnabled(False)
            controls.addWidget(button)
        controls.insertStretch(0, 1)
        result_layout.addLayout(controls)
        layout.addWidget(result_card, 1)

    def process_user_command(self, text: str) -> None:
        """Shared entry point for typed text and future speech transcription."""
        self.input_text.setPlainText(text)
        self.analyze()

    def analyze(self) -> None:
        text = self.input_text.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Comando mancante", "Inserisci il testo da analizzare.")
            return
        if self.thread is not None:
            return
        from app_config import load_config
        self.config = load_config(force_reload=True)
        self._set_busy(True, "Analisi ChatGPT in corso...")
        thread = QThread(self)
        worker = OperationalAssistantWorker(text, self.config)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._analysis_ready)
        worker.failed.connect(self._analysis_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(lambda _result: worker.deleteLater())
        worker.failed.connect(lambda _message: worker.deleteLater())
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)
        self.thread = thread
        self.worker = worker
        thread.start()

    def _analysis_ready(self, analysis) -> None:
        self.analysis = analysis
        command = analysis.command
        self.result_title.setText(
            f"{INTENT_LABELS.get(command.intent, command.intent)} - attendibilita {command.confidence:.0%}"
        )
        self.actions.clear()
        for action in command.proposed_actions:
            self.actions.addItem(f"[ ] {INTENT_LABELS.get(action.action, action.action)} ({action.module})")
        if command.missing_fields:
            self.actions.addItem("Campi mancanti: " + ", ".join(command.missing_fields))
        for warning in command.warnings:
            self.actions.addItem("Attenzione: " + warning)
        self.result_text.setPlainText(json.dumps(command.to_dict(), ensure_ascii=False, indent=2))
        self.result_text.setReadOnly(True)
        self.modify_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
        self.confirm_button.setEnabled(bool(command.proposed_actions) and not command.missing_fields)
        self.status.setText("Analisi completata. Nessun dato e stato modificato.")

    def _analysis_failed(self, message: str) -> None:
        self.status.setText("ChatGPT non disponibile. I moduli manuali restano utilizzabili.")
        QMessageBox.warning(self, "Assistente Operativo", message)

    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self._set_busy(False)

    def enable_edit(self) -> None:
        self.result_text.setReadOnly(False)
        self.result_text.setFocus()
        self.status.setText("Modifica il JSON e conferma: verra validato nuovamente.")

    def cancel(self) -> None:
        self.analysis = None
        self.actions.clear()
        self.result_text.clear()
        self.result_title.setText("Operazione annullata. Nessun dato e stato modificato.")
        self.result_text.setReadOnly(True)
        for button in (self.modify_button, self.cancel_button, self.confirm_button):
            button.setEnabled(False)

    def confirm(self) -> None:
        try:
            command = OperationalCommand.from_dict(extract_json_object(self.result_text.toPlainText()))
            if not self._select_target_record_if_needed(command):
                return
            operator = self.current_user.username if self.current_user else "Operatore PassApp"
            results = self.engine.confirm(command, operator)
        except (AIServiceError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Operazioni non eseguite", str(exc))
            return
        self._attach_requested_photos(results, operator)
        document_request = next(
            (item for item in results if item.action == "generate_inspection_document" and item.entity_id),
            None,
        )
        if document_request is not None:
            self.open_sopralluogo_requested.emit(int(document_request.entity_id))
        if self.analysis is not None:
            log_ai_interaction(
                original_text=self.input_text.toPlainText().strip(),
                raw_response=self.analysis.raw_response,
                validated_response=command.to_dict(),
                model=self.config.get("ai", {}).get("model", "automatico"),
                endpoint="https://api.openai.com/v1/responses",
                prompt_version=PROMPT_VERSION,
                proposed_actions=[item.__dict__ for item in self.analysis.command.proposed_actions],
                modified_actions=[item.__dict__ for item in command.proposed_actions],
                confirmed_actions=[result.__dict__ for result in results],
                records=[f"{result.entity_type}:{result.entity_id}" for result in results if result.entity_id],
                operator=operator,
            )
        messages = "\n".join(f"- {result.message}" for result in results)
        self.status.setText("Operazioni confermate e registrate nell'audit.")
        QMessageBox.information(self, "Operazioni completate", messages or "Nessuna operazione eseguita.")
        self.confirm_button.setEnabled(False)
        self.modify_button.setEnabled(False)
        self.result_text.setReadOnly(True)

    def _select_target_record_if_needed(self, command: OperationalCommand) -> bool:
        actions_requiring_target = {
            "update_report",
            "update_inspection",
            "generate_inspection_document",
            "request_photo_selection",
            "add_note",
            "search_related_report",
            "search_case",
        }
        if command.target_record is not None or not any(
            item.action in actions_requiring_target for item in command.proposed_actions
        ):
            return True
        criteria = command.report or command.inspection or command.inspection_update or {}
        matches = self.engine.search_reports(criteria)
        if not matches:
            QMessageBox.warning(
                self,
                "Nessun record compatibile",
                "Nessun record compatibile trovato. Non e stato creato automaticamente alcun record.",
            )
            return False
        if len(matches) == 1:
            command.target_record = {"case_number": matches[0].numero_progressivo}
        else:
            labels = [
                f"n. {item.numero_progressivo} - {item.indirizzo or '-'} - {item.nominativo or '-'}"
                for item in matches
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                "Seleziona la pratica corretta",
                "Sono stati trovati piu record compatibili:",
                labels,
                0,
                False,
            )
            if not accepted:
                return False
            command.target_record = {"case_number": matches[labels.index(selected)].numero_progressivo}
        if any(item.action == "update_inspection" for item in command.proposed_actions):
            inspections = self.engine.search_inspections(int(command.target_record["case_number"]))
            if not inspections:
                QMessageBox.warning(self, "Nessun sopralluogo", "La pratica selezionata non contiene sopralluoghi.")
                return False
            if len(inspections) == 1:
                command.target_record["inspection_id"] = inspections[0].id_sopralluogo
            else:
                inspection_labels = [
                    f"Sopralluogo #{item.id_sopralluogo} - {item.data_sopralluogo} - {item.stato}"
                    for item in inspections
                ]
                selected, accepted = QInputDialog.getItem(
                    self,
                    "Seleziona il sopralluogo",
                    "Sono stati trovati piu sopralluoghi:",
                    inspection_labels,
                    0,
                    False,
                )
                if not accepted:
                    return False
                command.target_record["inspection_id"] = inspections[inspection_labels.index(selected)].id_sopralluogo
        return True

    def _attach_requested_photos(self, results, operator: str) -> None:
        request = next((item for item in results if item.action == "request_photo_selection" and item.entity_id), None)
        if request is None:
            return
        filenames, _filter = QFileDialog.getOpenFileNames(
            self,
            "Seleziona fotografie",
            "",
            "Immagini (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)",
        )
        if not filenames:
            return
        report = next(
            (item for item in load_segnalazioni()[0] if item.numero_progressivo == int(request.entity_id)),
            None,
        )
        if report is None:
            QMessageBox.warning(self, "Fotografie non allegate", "Segnalazione collegata non trovata.")
            return
        for order, filename in enumerate(filenames, start=1):
            caption, accepted = QInputDialog.getText(self, "Didascalia fotografia", f"Didascalia per {filename}:")
            if not accepted:
                caption = ""
            add_attachment(
                report,
                Path(filename),
                "foto",
                origine="assistente_operativo",
                descrizione=caption,
                autore=operator,
                ordine=order,
            )

    def _set_busy(self, busy: bool, text: str | None = None) -> None:
        self.progress.setVisible(busy)
        self.analyze_button.setEnabled(not busy)
        if text:
            self.status.setText(text)
