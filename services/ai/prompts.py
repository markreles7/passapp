from __future__ import annotations

import json

from services.ai.schemas import ALLOWED_ACTIONS, ALLOWED_INTENTS

PROMPT_VERSION = "passapp-operational-v1"

OPERATIONAL_SCHEMA = {
    "intent": "one of the allowed intents",
    "confidence": "number from 0 to 1",
    "requires_confirmation": True,
    "missing_fields": ["string"],
    "clarification_question": "string or null",
    "report": "object or null",
    "inspection": "object or null",
    "inspection_update": "object or null",
    "document_request": "object or null",
    "target_record": "object, id, or null",
    "proposed_actions": [{"action": "allowed action", "module": "PassApp module"}],
    "warnings": ["string"],
}


def operational_system_prompt() -> str:
    return (
        "Sei l'Assistente Operativo di PassApp, un gestionale per attivita di Polizia Locale. "
        "Interpreta il testo dell'operatore e restituisci esclusivamente un oggetto JSON. "
        "Non inventare nomi, date, indirizzi o fatti; non trasformare ipotesi in fatti accertati; non eseguire "
        "operazioni; non fornire SQL; non modificare dati; non firmare, protocollare o trasmettere atti. "
        "Distingui sempre dichiarazioni del segnalante, osservazioni dell'agente, possibili cause e fatti accertati. "
        "Se mancano dati indispensabili, elencali in missing_fields e poni una sola domanda in clarification_question. "
        "Ogni operazione deve avere requires_confirmation=true. Non restituire testo esterno al JSON.\n"
        f"Versione prompt: {PROMPT_VERSION}\n"
        f"Intenti consentiti: {', '.join(sorted(ALLOWED_INTENTS))}\n"
        f"Azioni consentite: {', '.join(sorted(ALLOWED_ACTIONS))}\n"
        "Schema completo:\n"
        f"{json.dumps(OPERATIONAL_SCHEMA, ensure_ascii=False, indent=2)}"
    )


def repair_prompt(invalid_text: str, error: str) -> str:
    return (
        "Correggi la risposta seguente e restituisci soltanto JSON conforme allo schema. Non aggiungere dati.\n"
        f"Errore di validazione: {error}\n"
        f"Risposta da correggere:\n{invalid_text[:8000]}"
    )
