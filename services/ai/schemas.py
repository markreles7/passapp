from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from services.ai.exceptions import AIValidationError

ALLOWED_INTENTS = {
    "create_report",
    "create_inspection",
    "create_report_and_inspection",
    "update_report",
    "update_inspection",
    "generate_inspection_document",
    "attach_photos",
    "add_note",
    "create_reminder",
    "search_case",
    "unknown",
}

ALLOWED_ACTIONS = {
    "create_report",
    "create_inspection",
    "update_report",
    "update_inspection",
    "link_records",
    "generate_inspection_document",
    "request_photo_selection",
    "add_note",
    "create_reminder",
    "search_related_report",
    "search_case",
}


@dataclass(frozen=True)
class ProposedAction:
    action: str
    module: str


@dataclass
class OperationalCommand:
    intent: str
    confidence: float
    requires_confirmation: bool
    missing_fields: list[str] = field(default_factory=list)
    clarification_question: str | None = None
    report: dict[str, Any] | None = None
    inspection: dict[str, Any] | None = None
    inspection_update: dict[str, Any] | None = None
    document_request: dict[str, Any] | None = None
    target_record: dict[str, Any] | str | int | None = None
    proposed_actions: list[ProposedAction] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "OperationalCommand":
        required = {"intent", "confidence", "requires_confirmation", "missing_fields", "proposed_actions", "warnings"}
        missing = required - raw.keys()
        if missing:
            raise AIValidationError(f"Campi JSON obbligatori mancanti: {', '.join(sorted(missing))}")
        intent = raw.get("intent")
        if intent not in ALLOWED_INTENTS:
            raise AIValidationError(f"Intento non consentito: {intent}")
        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError) as exc:
            raise AIValidationError("confidence deve essere un numero.") from exc
        if not 0 <= confidence <= 1:
            raise AIValidationError("confidence deve essere compreso tra 0 e 1.")
        if raw.get("requires_confirmation") is not True:
            raise AIValidationError("Ogni comando operativo deve richiedere conferma.")
        missing_fields = _string_list(raw.get("missing_fields"), "missing_fields")
        warnings = _string_list(raw.get("warnings"), "warnings")
        actions_raw = raw.get("proposed_actions")
        if not isinstance(actions_raw, list):
            raise AIValidationError("proposed_actions deve essere un elenco.")
        actions: list[ProposedAction] = []
        for item in actions_raw:
            if not isinstance(item, dict) or not isinstance(item.get("action"), str) or not isinstance(item.get("module"), str):
                raise AIValidationError("Ogni azione deve contenere action e module.")
            if item["action"] not in ALLOWED_ACTIONS:
                raise AIValidationError(f"Azione non autorizzata: {item['action']}")
            actions.append(ProposedAction(item["action"], item["module"]))
        if intent == "unknown" and actions:
            raise AIValidationError("L'intento unknown non puo proporre azioni.")
        for name in ("report", "inspection", "inspection_update", "document_request"):
            value = raw.get(name)
            if value is not None and not isinstance(value, dict):
                raise AIValidationError(f"{name} deve essere un oggetto o null.")
        clarification = raw.get("clarification_question")
        if clarification is not None and not isinstance(clarification, str):
            raise AIValidationError("clarification_question deve essere testo o null.")
        command = cls(
            intent=intent,
            confidence=confidence,
            requires_confirmation=True,
            missing_fields=missing_fields,
            clarification_question=clarification,
            report=raw.get("report"),
            inspection=raw.get("inspection"),
            inspection_update=raw.get("inspection_update"),
            document_request=raw.get("document_request"),
            target_record=raw.get("target_record"),
            proposed_actions=actions,
            warnings=warnings,
        )
        command._validate_intent_payload()
        return command

    def _validate_intent_payload(self) -> None:
        if self.intent in {"create_report", "create_report_and_inspection"} and not self.report:
            raise AIValidationError("L'intento richiede l'oggetto report.")
        if self.intent in {"create_inspection", "create_report_and_inspection"} and not self.inspection:
            raise AIValidationError("L'intento richiede l'oggetto inspection.")
        if self.intent == "generate_inspection_document" and not self.document_request:
            raise AIValidationError("L'intento richiede document_request.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionResult:
    action: str
    success: bool
    message: str
    entity_type: str | None = None
    entity_id: str | None = None
    requires_user_input: bool = False


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise AIValidationError(f"{name} deve essere un elenco di stringhe.")
    return value
