from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app_config import load_config
from services.ai.exceptions import AIServiceError
from services.ai.chatgpt_client import ChatGPTClient, ChatGPTConfig

BASE_PROMPT = (
    "Sei l'assistente redazionale di PassApp per la Polizia Locale. Usa esclusivamente i dati forniti. "
    "Distingui fatti riferiti e fatti accertati, non inventare norme, responsabilita, nomi, date o circostanze. "
    "Restituisci solo il testo amministrativo richiesto, senza markdown."
)


def prepare_sopralluogo_verbale(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    prompt = (
        "Redigi il corpo di un verbale di sopralluogo in italiano, in stato di bozza IA. "
        "Includi premessa, attivita svolta, stato dei luoghi, valutazione prudente e chiusura istituzionale.\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    generated = _generate(prompt, config)
    return (generated, "chatgpt") if generated else (build_local_sopralluogo_verbale(payload), "locale")


def prepare_segnalazione_pdf(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    prompt = (
        "Redigi una relazione di segnalazione in italiano, in stato di bozza IA. Distingui quanto riferito dal "
        "segnalante da quanto eventualmente accertato dall'ufficio.\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    generated = _generate(prompt, config)
    return (generated, "chatgpt") if generated else (build_local_segnalazione_text(payload), "locale")


def generate_photo_caption_with_ai(
    image_path: str | Path, payload: dict[str, Any], config: dict[str, Any] | None = None
) -> str:
    # Il modello predefinito e testuale: PassApp non inventa contenuti visivi.
    return ""


def _generate(prompt: str, config: dict[str, Any] | None) -> str:
    app_config = config or load_config(force_reload=True)
    ai_config = app_config.get("ai", {})
    if not ai_config.get("documents_enabled", True):
        return ""
    try:
        client = ChatGPTClient(ChatGPTConfig.from_mapping(ai_config))
        payload = client.chat_sync(str(ai_config.get("base_prompt") or BASE_PROMPT), prompt)
        text = client.response_text(payload).strip()
    except (AIServiceError, OSError, ValueError) as exc:
        raise AIServiceError(str(exc)) from None
    if len(text) < 80:
        raise AIServiceError("ChatGPT ha restituito una bozza troppo breve. Riprova o disattiva le bozze IA per usare il testo standard.")
    return text


def build_local_sopralluogo_verbale(payload: dict[str, Any]) -> str:
    return (
        f"Con riferimento alla segnalazione n. {_v(payload, 'segnalazione_numero')}, relativa al luogo "
        f"{_v(payload, 'indirizzo_segnalazione')}, gli operatori {_v(payload, 'operatori')} hanno svolto il "
        f"sopralluogo in data/ora {_v(payload, 'data_ora')}. Secondo quanto registrato nella segnalazione: "
        f"{_v(payload, 'descrizione')}. In sede di accertamento e stato riportato: {_v(payload, 'esito')}. "
        f"Note operative: {_v(payload, 'note')}. Il presente testo e una bozza da revisionare e confermare "
        "prima di ogni utilizzo amministrativo. Tanto si riferisce per quanto di competenza."
    )


def build_local_segnalazione_text(payload: dict[str, Any]) -> str:
    return (
        f"In data/ora {_v(payload, 'data_ora_ricezione')} e stata acquisita la segnalazione n. "
        f"{_v(payload, 'numero')}, presentata da {_v(payload, 'nominativo')} e riferita a "
        f"{_v(payload, 'indirizzo')}. Secondo quanto riferito dal segnalante: {_v(payload, 'descrizione')}. "
        f"La pratica e classificata come {_v(payload, 'categoria')}, priorita {_v(payload, 'priorita')}, stato "
        f"{_v(payload, 'stato_lavorazione')}. Eventuali accertamenti registrati: {_v(payload, 'verifica')}. "
        "La relazione resta agli atti per la prosecuzione della pratica."
    )


def _v(payload: dict[str, Any], name: str) -> str:
    return str(payload.get(name) or "-").strip()
