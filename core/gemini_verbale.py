from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app_config import load_config

DEFAULT_MODEL = "gemini-3-flash-preview"
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def build_sopralluogo_verbale_prompt(payload: dict[str, Any]) -> str:
    facts = {
        "numero_segnalazione": payload.get("segnalazione_numero", "-"),
        "data_segnalazione": payload.get("segnalazione_data", "-"),
        "segnalante": payload.get("segnalante", "-"),
        "luogo_segnalato": payload.get("indirizzo_segnalazione", "-"),
        "descrizione_segnalazione": payload.get("descrizione", "-"),
        "id_sopralluogo": payload.get("id_sopralluogo", "-"),
        "stato_sopralluogo": payload.get("stato", "-"),
        "data_ora_sopralluogo": payload.get("data_ora", "-"),
        "luogo_sopralluogo": payload.get("luogo", "-"),
        "operatori": payload.get("operatori", "-"),
        "esito": payload.get("esito", "-"),
        "note_operative": payload.get("note", "-"),
        "foto_presenti": payload.get("foto", "-"),
        "numero_foto": payload.get("foto_count", "0"),
        "numero_documenti": payload.get("documenti_count", "0"),
        "ulteriori_atti": payload.get("atti", "-"),
        "ufficio_destinatario": payload.get("ufficio", "-"),
        "data_generazione": payload.get("data_generazione", "-"),
    }
    facts_text = json.dumps(facts, ensure_ascii=False, indent=2)
    return (
        "Scrivi il corpo narrativo di un verbale di sopralluogo per la Polizia Locale.\n"
        "Usa esclusivamente i dati forniti nel JSON. Non inventare nomi, norme, articoli di legge, misure, violazioni, "
        "date, orari o fatti non presenti. Se un dato manca, scrivi che non risulta indicato.\n"
        "Stile richiesto: formale, amministrativo, chiaro, adatto a essere inserito in un modello Word di verbale.\n"
        "Non usare markdown, elenchi puntati, titoli iniziali o formule di fantasia. Restituisci solo il testo del verbale.\n"
        "Mantieni il testo tra 180 e 450 parole.\n\n"
        f"Dati disponibili:\n{facts_text}"
    )


def build_local_sopralluogo_verbale(payload: dict[str, Any]) -> str:
    seg_num = _value(payload.get("segnalazione_numero"))
    seg_date = _value(payload.get("segnalazione_data"))
    segnalante = _value(payload.get("segnalante"))
    indirizzo = _value(payload.get("indirizzo_segnalazione"))
    descrizione = _value(payload.get("descrizione"))
    data_ora = _value(payload.get("data_ora"))
    luogo = _value(payload.get("luogo"))
    operatori = _value(payload.get("operatori"))
    esito = _value(payload.get("esito"))
    note = _value(payload.get("note"))
    foto = _value(payload.get("foto"))
    foto_count = _value(payload.get("foto_count"), "0")
    documenti_count = _value(payload.get("documenti_count"), "0")
    atti = _value(payload.get("atti"))
    ufficio = _value(payload.get("ufficio"))

    return (
        f"In relazione alla segnalazione n. {seg_num}, ricevuta in data {seg_date} da {segnalante}, "
        f"avente ad oggetto quanto riferito per il luogo indicato in {indirizzo}, si da atto che il sopralluogo "
        f"e stato effettuato in data/ora {data_ora} presso {luogo} dagli operatori {operatori}.\n\n"
        f"La segnalazione riportava quanto segue: {descrizione}.\n\n"
        f"All'esito dell'accertamento svolto sul posto risulta quanto segue: {esito}. "
        f"Le note operative annotate sono le seguenti: {note}.\n\n"
        f"Per la pratica risulta indicata presenza di foto/allegati: {foto}. "
        f"Nel fascicolo digitale risultano richiamate {foto_count} foto e {documenti_count} documenti. "
        f"Necessita di ulteriori atti: {atti}. Ufficio destinatario o competente: {ufficio}.\n\n"
        "Il presente verbale viene redatto sulla base dei dati inseriti nella segnalazione e nel sopralluogo collegato."
    )


def generate_sopralluogo_verbale_with_gemini(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    if not ai_config.get("gemini_enabled_for_sopralluogo", True):
        return ""

    api_key = str(ai_config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return ""

    model = _clean_model_name(str(ai_config.get("gemini_model") or DEFAULT_MODEL))
    timeout = _safe_timeout(ai_config.get("gemini_timeout_seconds"))
    prompt = build_sopralluogo_verbale_prompt(payload)
    request_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": 1200,
        },
    }
    data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API_URL_TEMPLATE.format(model=model),
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return ""

    text = _extract_response_text(response_data)
    return _sanitize_generated_text(text)


def prepare_sopralluogo_verbale_text(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    generated = generate_sopralluogo_verbale_with_gemini(payload, config=config)
    return generated or build_local_sopralluogo_verbale(payload)


def _extract_response_text(response_data: dict[str, Any]) -> str:
    candidates = response_data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))


def _sanitize_generated_text(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:6000].strip()


def _clean_model_name(value: str) -> str:
    value = value.strip() or DEFAULT_MODEL
    return value.split("/")[-1]


def _safe_timeout(value: Any) -> int:
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        timeout = 45
    return max(10, min(timeout, 120))


def _value(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback
