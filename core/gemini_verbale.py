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
DEFAULT_BASE_PROMPT = (
    "Sei un assistente redazionale per un ufficio di Polizia Locale. "
    "Devi trasformare i dati inseriti dagli operatori in testi amministrativi chiari, formali e professionali. "
    "Usa solo i dati disponibili, non inventare norme, responsabilita, misure, nominativi, date o fatti. "
    "Se un dato non e presente, indica che non risulta agli atti. "
    "Mantieni un tono neutro e istituzionale, evitando frasi colloquiali o valutazioni personali."
)


def build_sopralluogo_verbale_prompt(payload: dict[str, Any], base_prompt: str | None = None) -> str:
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
    base = _base_prompt_text(base_prompt)
    return (
        f"{base}\n\n"
        "Scrivi il corpo narrativo di un verbale di sopralluogo per la Polizia Locale.\n"
        "Usa esclusivamente i dati forniti nel JSON. Non inventare nomi, norme, articoli di legge, misure, violazioni, "
        "date, orari o fatti non presenti. Se un dato manca, scrivi che non risulta indicato.\n"
        "Stile richiesto: verbale amministrativo discorsivo, simile a una relazione di servizio: "
        "inizia con una formula del tipo 'I sottoscritti Operatori di Polizia Locale...', descrivi il sopralluogo, "
        "richiama la segnalazione, riporta quanto accertato, indica eventuali allegati e chiudi con una formula "
        "del tipo 'Tanto si riferisce per i provvedimenti di competenza'.\n"
        "Riformula in modo istituzionale eventuali frasi colloquiali o operative inserite dagli utenti, mantenendo pero "
        "il contenuto sostanziale. Distingui il fatto segnalato da quanto accertato durante il sopralluogo.\n"
        "Non usare markdown, elenchi puntati, titoli iniziali o formule di fantasia. Restituisci solo il corpo del verbale.\n"
        "Mantieni il testo tra 350 e 800 parole, con 3-6 paragrafi.\n\n"
        f"Dati disponibili:\n{facts_text}"
    )


def build_segnalazione_pdf_prompt(payload: dict[str, Any], base_prompt: str | None = None) -> str:
    facts = {
        "numero": payload.get("numero", "-"),
        "anno": payload.get("anno", "-"),
        "stato": payload.get("stato", "-"),
        "data_ora_ricezione": payload.get("data_ora_ricezione", "-"),
        "nominativo": payload.get("nominativo", "-"),
        "residenza": payload.get("residenza", "-"),
        "indirizzo": payload.get("indirizzo", "-"),
        "telefono": payload.get("telefono", "-"),
        "modalita": payload.get("modalita", "-"),
        "categoria": payload.get("categoria", "-"),
        "priorita": payload.get("priorita", "-"),
        "stato_lavorazione": payload.get("stato_lavorazione", "-"),
        "ricevente": payload.get("ricevente", "-"),
        "descrizione": payload.get("descrizione", "-"),
        "agente": payload.get("agente", "-"),
        "data_accertamento": payload.get("data_accertamento", "-"),
        "verifica": payload.get("verifica", "-"),
        "riferimento": payload.get("riferimento", "-"),
    }
    facts_text = json.dumps(facts, ensure_ascii=False, indent=2)
    base = _base_prompt_text(base_prompt)
    return (
        f"{base}\n\n"
        "Scrivi una relazione descrittiva di segnalazione per la Polizia Locale.\n"
        "Deve essere piu corposa di un riepilogo telegrafico, ma deve usare solo i dati forniti. "
        "Non inventare norme, responsabilita, accertamenti non svolti, nominativi o fatti non presenti.\n"
        "Stile richiesto: amministrativo, chiaro, adatto a un documento PDF di segnalazione collegato a un eventuale sopralluogo. "
        "Descrivi chi segnala, quando e con quale modalita, il luogo indicato, il contenuto della segnalazione, "
        "la ricezione da parte dell'ufficio e l'eventuale stato di lavorazione o verifica registrata.\n"
        "Conserva il senso della descrizione originale, ma rendila leggibile come relazione d'ufficio. "
        "Se il sopralluogo non e ancora concluso, non scrivere che e stato accertato un fatto.\n"
        "Non usare markdown, titoli o elenchi puntati. Restituisci solo il testo della relazione.\n"
        "Mantieni il testo tra 250 e 550 parole, con 2-5 paragrafi.\n\n"
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

    allegati_text = _attachment_summary(foto, foto_count, documenti_count)
    return (
        f"I sottoscritti Operatori di Polizia Locale, {operatori}, in relazione alla segnalazione n. {seg_num}, "
        f"ricevuta in data {seg_date} da {segnalante}, si sono portati in data/ora {data_ora} presso {luogo}, "
        f"al fine di procedere agli accertamenti di competenza sul luogo indicato in {indirizzo}.\n\n"
        f"La segnalazione aveva ad oggetto quanto segue: {descrizione}. Durante il sopralluogo e stata verificata "
        f"la situazione presente sul posto e sono state raccolte le annotazioni operative utili alla prosecuzione "
        f"della pratica.\n\n"
        f"All'esito dell'accertamento risulta quanto segue: {esito}. Le note operative riportate dagli operatori "
        f"sono le seguenti: {note}.\n\n"
        f"{allegati_text} Necessita di ulteriori atti: {atti}. "
        f"Ufficio destinatario o competente: {ufficio}.\n\n"
        "Tanto si riferisce per i provvedimenti di competenza."
    )


def build_local_segnalazione_text(payload: dict[str, Any]) -> str:
    numero = _value(payload.get("numero"))
    ricezione = _value(payload.get("data_ora_ricezione"))
    nominativo = _value(payload.get("nominativo"))
    modalita = _value(payload.get("modalita"))
    indirizzo = _value(payload.get("indirizzo"))
    residenza = _value(payload.get("residenza"))
    telefono = _value(payload.get("telefono"))
    categoria = _value(payload.get("categoria"))
    priorita = _value(payload.get("priorita"))
    stato = _value(payload.get("stato_lavorazione"))
    ricevente = _value(payload.get("ricevente"))
    descrizione = _value(payload.get("descrizione"))
    agente = _value(payload.get("agente"))
    data_accertamento = _value(payload.get("data_accertamento"))
    verifica = _value(payload.get("verifica"))

    return (
        f"In data/ora {ricezione} e stata registrata la segnalazione n. {numero}, pervenuta con modalita {modalita} "
        f"da {nominativo}, residente/domiciliato in {residenza}, recapito telefonico {telefono}. La segnalazione "
        f"e riferita al luogo indicato in {indirizzo} ed e stata presa in carico dall'operatore ricevente {ricevente}.\n\n"
        f"Il contenuto riferito dal segnalante e il seguente: {descrizione}. La pratica e classificata nella categoria "
        f"{categoria}, con priorita {priorita}, e risulta nello stato di lavorazione {stato}.\n\n"
        f"Per quanto riguarda l'attivita successiva dell'ufficio, risulta indicato come agente verificatore {agente}, "
        f"con data accertamento {data_accertamento}. Il riscontro registrato e il seguente: {verifica}.\n\n"
        "La presente relazione viene generata sulla base dei dati inseriti in PassApp e costituisce riepilogo operativo "
        "della segnalazione, utile alla prosecuzione della pratica e all'eventuale collegamento con richiesta di sopralluogo."
    )


def generate_sopralluogo_verbale_with_gemini(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    if not ai_config.get("gemini_enabled_for_sopralluogo", True):
        return ""

    prompt = build_sopralluogo_verbale_prompt(payload, base_prompt=ai_config.get("gemini_base_prompt"))
    return _generate_with_gemini(prompt, ai_config, max_output_tokens=1800)


def generate_segnalazione_text_with_gemini(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    if not ai_config.get("gemini_enabled_for_segnalazione_pdf", True):
        return ""

    prompt = build_segnalazione_pdf_prompt(payload, base_prompt=ai_config.get("gemini_base_prompt"))
    return _generate_with_gemini(prompt, ai_config, max_output_tokens=1400)


def prepare_sopralluogo_verbale(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    generated = generate_sopralluogo_verbale_with_gemini(payload, config=config)
    if generated:
        return generated, "gemini"
    return build_local_sopralluogo_verbale(payload), "locale"


def prepare_sopralluogo_verbale_text(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    return prepare_sopralluogo_verbale(payload, config=config)[0]


def prepare_segnalazione_pdf(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    generated = generate_segnalazione_text_with_gemini(payload, config=config)
    if generated:
        return generated, "gemini"
    return build_local_segnalazione_text(payload), "locale"


def prepare_segnalazione_pdf_text(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    return prepare_segnalazione_pdf(payload, config=config)[0]


def _generate_with_gemini(prompt: str, ai_config: dict[str, Any], *, max_output_tokens: int) -> str:
    api_key = str(ai_config.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return ""

    model = _clean_model_name(str(ai_config.get("gemini_model") or DEFAULT_MODEL))
    timeout = _safe_timeout(ai_config.get("gemini_timeout_seconds"))
    request_payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.8,
            "maxOutputTokens": max_output_tokens,
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


def _base_prompt_text(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else DEFAULT_BASE_PROMPT


def _attachment_summary(foto: str, foto_count: str, documenti_count: str) -> str:
    if str(foto).lower().startswith("s") or foto_count not in ("0", "-"):
        return (
            f"Si richiama la documentazione allegata al fascicolo digitale, composta da n. {foto_count} foto "
            f"e n. {documenti_count} documenti alla data di generazione del verbale."
        )
    return (
        f"Non risulta allegata documentazione fotografica alla data di generazione del verbale; "
        f"nel fascicolo digitale risultano n. {documenti_count} documenti."
    )


def _value(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback
