from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from app_config import resolve_path
from core.audit import log_audit_event
from core.segnalazioni import (
    Segnalazione,
    load_segnalazioni,
    next_progressivo,
    normalize_categoria,
    normalize_priorita,
    save_segnalazioni,
)
from core.sopralluoghi import Sopralluogo, load_sopralluoghi, next_sopralluogo_id, save_sopralluoghi
from services.ai.exceptions import AIValidationError
from services.ai.schemas import ActionResult, OperationalCommand

Handler = Callable[[OperationalCommand, str], ActionResult]


class ActionEngine:
    """Executes only explicit PassApp handlers after an operator confirmation."""

    def __init__(self):
        self._created_report_id: int | None = None
        self.registry: dict[str, Handler] = {
            "create_report": self._create_report,
            "create_inspection": self._create_inspection,
            "update_report": self._update_report,
            "update_inspection": self._update_inspection,
            "link_records": self._link_records,
            "generate_inspection_document": self._document_draft,
            "request_photo_selection": self._photo_selection,
            "add_note": self._add_note,
            "create_reminder": self._create_reminder,
            "search_related_report": self._search_action,
            "search_case": self._search_action,
        }

    def preview(self, command: OperationalCommand) -> list[ActionResult]:
        results: list[ActionResult] = []
        for item in command.proposed_actions:
            if item.action not in self.registry:
                raise AIValidationError(f"Azione non autorizzata: {item.action}")
            results.append(ActionResult(item.action, True, f"Azione proposta: {item.action}"))
        return results

    def confirm(self, command: OperationalCommand, operator: str) -> list[ActionResult]:
        if not command.requires_confirmation:
            raise AIValidationError("Il comando non contiene la conferma obbligatoria.")
        if command.missing_fields:
            raise AIValidationError("Completa i campi mancanti prima della conferma: " + ", ".join(command.missing_fields))
        self._created_report_id = None
        before_reports = load_segnalazioni()[0]
        before_inspections = load_sopralluoghi()
        results: list[ActionResult] = []
        try:
            for proposed in command.proposed_actions:
                handler = self.registry.get(proposed.action)
                if handler is None:
                    raise AIValidationError(f"Azione non autorizzata: {proposed.action}")
                result = handler(command, operator)
                results.append(result)
                if not result.success and not result.requires_user_input:
                    raise AIValidationError(result.message)
        except Exception:
            save_segnalazioni(before_reports)
            save_sopralluoghi(before_inspections)
            log_audit_event("assistente_operativo", "rollback", description="Rollback azioni IA", result="error", operator=operator)
            raise
        for result in results:
            log_audit_event(
                "assistente_operativo",
                result.action,
                result.entity_type,
                result.entity_id,
                result.message,
                operator=operator,
            )
        return results

    def search_reports(self, criteria: dict[str, Any]) -> list[Segnalazione]:
        records = load_segnalazioni()[0]
        address = _normalize(criteria.get("address") or criteria.get("indirizzo"))
        category = _normalize(criteria.get("category") or criteria.get("categoria"))
        reporter = _normalize(criteria.get("reporter_name") or criteria.get("segnalante"))
        case_number = str(criteria.get("case_number") or criteria.get("numero_pratica") or "").strip()
        date_value = _normalize(criteria.get("date") or criteria.get("data"))
        matches: list[Segnalazione] = []
        for item in records:
            if case_number and str(item.numero_progressivo) != case_number:
                continue
            if address and address not in _normalize(item.indirizzo):
                continue
            if category and category not in _normalize(item.categoria):
                continue
            if reporter and reporter not in _normalize(item.nominativo):
                continue
            if date_value and date_value not in _normalize(f"{item.giorno}/{item.mese}/{item.anno}"):
                continue
            if item.stato_lavorazione in {"Chiusa", "Archiviata"} and not case_number:
                continue
            matches.append(item)
        return matches

    def search_inspections(self, report_id: int) -> list[Sopralluogo]:
        return [item for item in load_sopralluoghi() if item.segnalazione_id == int(report_id)]

    def _create_report(self, command: OperationalCommand, operator: str) -> ActionResult:
        data = command.report or {}
        records, _source = load_segnalazioni()
        now = dt.datetime.now()
        item = Segnalazione(
            numero_progressivo=next_progressivo(records),
            anno=str(now.year),
            mese=f"{now.month:02d}",
            giorno=f"{now.day:02d}",
            ora=now.strftime("%H:%M"),
            nominativo=str(data.get("reporter_name") or ""),
            indirizzo=str(data.get("address") or ""),
            telefono=str(data.get("reporter_contact") or ""),
            descrizione_segnalazione=str(data.get("description") or ""),
            ricevente=operator,
            categoria=normalize_categoria(str(data.get("category") or "Altro").replace("_", " ")),
            priorita=normalize_priorita(str(data.get("priority") or "Media")),
            stato_lavorazione="Aperta",
        )
        if not item.indirizzo.strip() or not item.descrizione_segnalazione.strip():
            return ActionResult("create_report", False, "Indirizzo e descrizione sono obbligatori.")
        duplicates = self.search_reports({"address": item.indirizzo, "reporter_name": item.nominativo})
        if duplicates:
            return ActionResult("create_report", False, "Possibile segnalazione duplicata: selezionare il record corretto.")
        records.append(item)
        save_segnalazioni(records)
        self._created_report_id = item.numero_progressivo
        return ActionResult("create_report", True, "Segnalazione creata.", "segnalazione", str(item.numero_progressivo))

    def _create_inspection(self, command: OperationalCommand, operator: str) -> ActionResult:
        data = command.inspection or {}
        report_id = self._target_report_id(command, data)
        if report_id is None:
            return ActionResult("create_inspection", False, "Nessuna segnalazione univoca selezionata per il sopralluogo.")
        records = load_sopralluoghi()
        now = dt.datetime.now()
        item = Sopralluogo(
            id_sopralluogo=next_sopralluogo_id(records),
            segnalazione_id=report_id,
            data_sopralluogo=str(data.get("scheduled_at") or now.strftime("%d/%m/%Y")),
            operatori=operator,
            luogo=str(data.get("address") or ""),
            note_operative=str(data.get("reason") or ""),
            stato="da programmare",
            data_creazione=now.strftime("%Y-%m-%d %H:%M:%S"),
            data_ultima_modifica=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
        records.append(item)
        save_sopralluoghi(records)
        return ActionResult("create_inspection", True, "Sopralluogo creato.", "sopralluogo", str(item.id_sopralluogo))

    def _update_report(self, command: OperationalCommand, _operator: str) -> ActionResult:
        criteria = _target_criteria(command)
        matches = self.search_reports(criteria)
        if len(matches) != 1:
            return ActionResult("update_report", False, _selection_message(len(matches)))
        current = matches[0]
        data = command.report or {}
        updated = replace(
            current,
            descrizione_segnalazione=str(data.get("description") or current.descrizione_segnalazione),
            indirizzo=str(data.get("address") or current.indirizzo),
            nominativo=str(data.get("reporter_name") or current.nominativo),
        )
        records = load_segnalazioni()[0]
        save_segnalazioni([updated if item.numero_progressivo == current.numero_progressivo else item for item in records])
        return ActionResult("update_report", True, "Segnalazione aggiornata.", "segnalazione", str(current.numero_progressivo))

    def _update_inspection(self, command: OperationalCommand, _operator: str) -> ActionResult:
        target = command.target_record
        inspection_id = int(target.get("inspection_id", 0)) if isinstance(target, dict) else 0
        if not inspection_id and isinstance(target, dict) and target.get("case_number"):
            candidates = self.search_inspections(int(target["case_number"]))
            inspection_id = candidates[0].id_sopralluogo if len(candidates) == 1 else 0
        records = load_sopralluoghi()
        matches = [item for item in records if item.id_sopralluogo == inspection_id]
        if len(matches) != 1:
            return ActionResult("update_inspection", False, "Sopralluogo non individuato in modo univoco.")
        current = matches[0]
        data = command.inspection_update or command.inspection or {}
        facts = data.get("observed_facts")
        fact_text = "; ".join(str(item) for item in facts) if isinstance(facts, list) else ""
        cause = str(data.get("reported_or_inferred_cause") or "")
        note = ". ".join(part for part in (fact_text, cause) if part)
        updated = replace(current, esito=fact_text or current.esito, note_operative=note or current.note_operative)
        save_sopralluoghi([updated if item.id_sopralluogo == current.id_sopralluogo else item for item in records])
        return ActionResult("update_inspection", True, "Sopralluogo aggiornato.", "sopralluogo", str(current.id_sopralluogo))

    def _link_records(self, _command: OperationalCommand, _operator: str) -> ActionResult:
        if self._created_report_id is None:
            return ActionResult("link_records", False, "Nessuna nuova segnalazione da collegare.")
        return ActionResult("link_records", True, "Collegamento garantito dall'identificativo della segnalazione.", "segnalazione", str(self._created_report_id))

    def _document_draft(self, _command: OperationalCommand, _operator: str) -> ActionResult:
        report_id = self._created_report_id
        if report_id is None:
            matches = self.search_reports(_target_criteria(_command))
            report_id = matches[0].numero_progressivo if len(matches) == 1 else None
        if report_id is None:
            return ActionResult(
                "generate_inspection_document",
                False,
                "Selezionare una segnalazione univoca prima di preparare il verbale.",
                requires_user_input=True,
            )
        return ActionResult(
            "generate_inspection_document",
            True,
            "Apertura del sopralluogo richiesta: il template produrra una bozza IA da revisionare prima dell'esportazione.",
            "segnalazione",
            str(report_id),
            requires_user_input=True,
        )

    def _photo_selection(self, _command: OperationalCommand, _operator: str) -> ActionResult:
        report_id = self._created_report_id
        if report_id is None:
            matches = self.search_reports(_target_criteria(_command))
            report_id = matches[0].numero_progressivo if len(matches) == 1 else None
        if report_id is None:
            return ActionResult("request_photo_selection", False, "Selezionare prima una segnalazione univoca.", requires_user_input=True)
        return ActionResult(
            "request_photo_selection",
            True,
            "Selezione manuale delle fotografie richiesta.",
            "segnalazione",
            str(report_id),
            True,
        )

    def _add_note(self, command: OperationalCommand, operator: str) -> ActionResult:
        return self._update_report(command, operator)

    def _create_reminder(self, command: OperationalCommand, operator: str) -> ActionResult:
        path = resolve_path("data/reminders.json")
        values = []
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                values = raw if isinstance(raw, list) else []
            except (OSError, json.JSONDecodeError):
                values = []
        values.append({"created_at": dt.datetime.now().isoformat(), "operator": operator, "data": command.report or command.inspection or {}})
        _atomic_json_write(path, values)
        return ActionResult("create_reminder", True, "Promemoria creato.", "promemoria", str(len(values)))

    def _search_action(self, command: OperationalCommand, _operator: str) -> ActionResult:
        matches = self.search_reports(_target_criteria(command))
        if len(matches) == 1:
            return ActionResult("search_case", True, f"Trovata la segnalazione n. {matches[0].numero_progressivo}.", "segnalazione", str(matches[0].numero_progressivo))
        return ActionResult("search_case", False, _selection_message(len(matches)), requires_user_input=len(matches) > 1)

    def _target_report_id(self, command: OperationalCommand, data: dict[str, Any]) -> int | None:
        if self._created_report_id is not None:
            return self._created_report_id
        matches = self.search_reports({**_target_criteria(command), **data})
        return matches[0].numero_progressivo if len(matches) == 1 else None


def _target_criteria(command: OperationalCommand) -> dict[str, Any]:
    if isinstance(command.target_record, dict):
        return command.target_record
    if isinstance(command.target_record, (str, int)):
        return {"case_number": command.target_record}
    return command.report or command.inspection or command.inspection_update or {}


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _selection_message(count: int) -> str:
    if count == 0:
        return "Nessun record compatibile trovato; nessun record e stato creato automaticamente."
    return f"Trovati {count} record compatibili; selezionare il record corretto."


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.stem, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
