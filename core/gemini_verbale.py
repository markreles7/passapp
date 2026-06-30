from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app_config import load_config

DEFAULT_MODEL = "gemini-3-flash-preview"
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_OPENROUTER_MODEL = "openrouter/openrouter/free"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_BASE_PROMPT = (
    "Sei un assistente redazionale per un ufficio di Polizia Locale. "
    "Devi trasformare i dati inseriti dagli operatori in testi amministrativi chiari, formali e professionali. "
    "Usa solo i dati disponibili, non inventare norme, responsabilita, misure, nominativi, date o fatti. "
    "Se un dato non e presente, indica che non risulta agli atti. "
    "Mantieni un tono neutro e istituzionale, evitando frasi colloquiali o valutazioni personali."
)

SOPRALLUOGO_COPY_FIELDS = ("descrizione", "esito", "note")
SEGNALAZIONE_COPY_FIELDS = ("descrizione", "verifica", "agente", "riferimento", "note")
MIN_AI_TEXT_LENGTH = 180


@dataclass(frozen=True)
class AiConnectionTestResult:
    ok: bool
    provider: str
    model: str
    detail: str


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
        "Dati grezzi\n"
        f"{facts_text}\n\n"
        "Compito\n"
        "Agisci come assistente redazionale per un ufficio di Polizia Locale italiana. Trasforma gli appunti "
        "grezzi della segnalazione e del sopralluogo in una relazione tecnico-amministrativa professionale, "
        "chiara, istituzionale e pronta per essere inserita nel documento. Non limitarti a riordinare o "
        "riassumere i campi: devi riformulare in linguaggio d'ufficio, distinguendo quanto e stato segnalato "
        "da quanto e stato accertato sul posto.\n\n"
        "Regole anti-copia\n"
        "Non copiare frasi colloquiali dell'operatore o del cittadino. Non riprodurre espressioni come "
        "'sono andati sul luogo', 'brutto tempo', 'forse penzolante', 'probabilita che cada' o ripetizioni "
        "inutili del luogo. Trasforma le note operative in linguaggio tecnico. Preferisci formule come "
        "'si sono portati presso', 'e stata rilevata la presenza di', 'e stata accertata/verificata', "
        "'allo stato dei luoghi', 'al momento del sopralluogo', 'non sono emersi elementi tali da', "
        "'si ritiene opportuno interessare' e 'per quanto di competenza'.\n\n"
        "Struttura obbligatoria del testo\n"
        "Il testo deve essere discorsivo, senza titoli interni, ma deve contenere in ordine logico: premessa "
        "sulla segnalazione ricevuta; attivita svolta dagli operatori; stato dei luoghi accertato; valutazione "
        "operativa prudente; eventuale proposta o inoltro all'ufficio competente; chiusura istituzionale. "
        "Se non risultano foto, scrivi: 'Alla data di generazione del presente atto non risulta acquisita "
        "documentazione fotografica nel fascicolo digitale.' Se risultano allegati, richiamali in modo sintetico.\n\n"
        "Esempio di trasformazione\n"
        "Appunto grezzo: 'un cittadino segnala un elemento danneggiato forse pericoloso; gli operatori sono "
        "andati sul posto e hanno visto che non da fastidio; intervento quando passa il brutto tempo'. "
        "Forma attesa: 'Con riferimento alla segnalazione acquisita agli atti, relativa alla possibile presenza "
        "di un elemento danneggiato presso il luogo indicato, gli operatori si sono portati sul posto per gli "
        "accertamenti di competenza. Al momento del sopralluogo veniva rilevata una criticita da valutare, "
        "senza evidenza di interferenze immediate con la pubblica circolazione, ferma restando l'opportunita "
        "di intervento manutentivo da parte del servizio competente non appena le condizioni lo consentano.' "
        "L'esempio serve solo come stile: non copiarlo e non introdurre fatti non presenti nei dati grezzi.\n\n"
        "Divieti\n"
        "Non inventare norme, articoli di legge, responsabilita, misure, violazioni, pericoli, assenza assoluta "
        "di pericolo o fatti non indicati. Usa formule caute come 'verosimilmente', 'presumibilmente', "
        "'allo stato' o 'per quanto constatabile al momento del sopralluogo' solo se coerenti con i dati.\n\n"
        "Output richiesto\n"
        "Restituisci solo il corpo del verbale/relazione, senza markdown, elenchi puntati, titoli o formattazione "
        "speciale. Produci un testo tra 250 e 500 parole, salvo dati molto scarsi."
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
        "Ruolo\n"
        "Sei un assistente redazionale per la Polizia Locale italiana. Scrivi in linguaggio "
        "tecnico-amministrativo, istituzionale, prudente e leggibile.\n\n"
        "Compito\n"
        "Genera una relazione di segnalazione professionale e autonoma. Non devi fare un semplice riepilogo: "
        "devi riformulare i dati registrati in PassApp, distinguere quanto riferito dal segnalante da quanto "
        "eventualmente accertato dall'ufficio e trasformare note grezze o colloquiali in testo tecnico.\n\n"
        "Dati grezzi disponibili\n"
        f"{facts_text}\n\n"
        "Regole anti-copia\n"
        "Non copiare il testo dei campi grezzi. Non scrivere 'Il contenuto riferito dal segnalante e il seguente', "
        "'Il riscontro registrato e il seguente', 'Riscontro registrato in app', 'sono andati sul luogo', "
        "'brutto tempo', 'forse penzolante', 'probabilita che cada' o 'non provocando pericoli'. Trasforma "
        "'forse' in 'presumibilmente', 'secondo quanto riferito' o 'verosimilmente' solo se coerente; "
        "'penzolante' in 'parzialmente distaccata', 'sospesa' o 'instabile' solo se coerente; 'cada sulla strada' "
        "in 'possa interessare la sede stradale'; 'brutto tempo' in 'condizioni meteorologiche avverse/non "
        "favorevoli'; 'sono andati sul luogo' in 'si sono portati presso il luogo indicato'.\n\n"
        "Struttura obbligatoria\n"
        "A) Premessa di ricezione: indica data, modalita, numero e acquisizione agli atti. "
        "B) Oggetto della segnalazione: riformula il contenuto riferito e indica il luogo. "
        "C) Attivita successiva o accertamento: inseriscila solo se risulta dai dati. "
        "D) Esito tecnico-amministrativo: riformula l'esito o la verifica in linguaggio tecnico. "
        "E) Valutazione prudente: non affermare pericoli o assenza di pericoli in modo assoluto se i dati sono "
        "incerti; usa formule come 'per quanto constatabile' o 'allo stato'. "
        "F) Chiusura: indica che la relazione resta agli atti per la prosecuzione della pratica e per gli "
        "eventuali provvedimenti di competenza.\n\n"
        "Lessico tecnico consigliato\n"
        "Usa formule come 'veniva acquisita agli atti', 'relativa a', 'secondo quanto riferito', 'dagli atti "
        "risulta', 'in sede di accertamento veniva rilevato', 'per quanto registrato', 'ufficio competente', "
        "'valutazioni di competenza' e 'prosecuzione della pratica'.\n\n"
        "Divieti\n"
        "Non inventare norme, responsabilita, violazioni, misure, sopralluoghi, nominativi o fatti non presenti. "
        "Non usare markdown, elenchi puntati, titoli interni o formattazione speciale.\n\n"
        "Output richiesto\n"
        "Restituisci solo il corpo della relazione, pronto da inserire nel PDF, tra 250 e 500 parole salvo dati "
        "molto scarsi. Distingui quanto riferito da quanto accertato."
    )


def build_local_sopralluogo_verbale(payload: dict[str, Any]) -> str:
    seg_num = _value(payload.get("segnalazione_numero"))
    seg_date = _value(payload.get("segnalazione_data"))
    segnalante = _value(payload.get("segnalante"))
    indirizzo = _value(payload.get("indirizzo_segnalazione"))
    descrizione = _strip_terminal_punctuation(_technical_rewrite_hint(_value(payload.get("descrizione"))))
    data_ora = _value(payload.get("data_ora"))
    luogo = _value(payload.get("luogo"))
    operatori = _value(payload.get("operatori"))
    esito = _strip_terminal_punctuation(_technical_rewrite_hint(_value(payload.get("esito"))))
    note = _strip_terminal_punctuation(_technical_rewrite_hint(_value(payload.get("note"))))
    foto = _value(payload.get("foto"))
    foto_count = _value(payload.get("foto_count"), "0")
    documenti_count = _value(payload.get("documenti_count"), "0")
    atti = _value(payload.get("atti"))
    ufficio = _value(payload.get("ufficio"))

    allegati_text = _attachment_summary(foto, foto_count, documenti_count)
    return (
        f"Con riferimento alla segnalazione n. {seg_num}, ricevuta in data {seg_date} da {segnalante} e relativa "
        f"al luogo indicato in {indirizzo}, gli operatori di Polizia Locale {operatori} si sono portati in data/ora "
        f"{data_ora} presso {luogo} per procedere agli accertamenti di competenza.\n\n"
        f"La segnalazione riguardava la situazione descritta come segue: {descrizione}. "
        "Al momento del sopralluogo e stata verificata la situazione "
        f"presente sul posto, distinguendo quanto riferito in fase di ricezione da quanto direttamente riscontrato "
        f"allo stato dei luoghi.\n\n"
        f"In sede di accertamento veniva rilevato quanto segue: {esito}. Per quanto registrato dagli operatori, "
        f"le indicazioni operative successive sono ricondotte a quanto segue: {note}.\n\n"
        f"{allegati_text} Dagli atti risulta necessita di ulteriori atti: {atti}. "
        f"L'eventuale seguito della pratica viene rimesso all'ufficio competente indicato come {ufficio}, "
        "per le valutazioni e i provvedimenti di competenza.\n\n"
        "Tanto si riferisce per quanto di competenza."
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
    descrizione = _strip_terminal_punctuation(_technical_rewrite_hint(_value(payload.get("descrizione"))))
    agente = _value(payload.get("agente"))
    data_accertamento = _value(payload.get("data_accertamento"))
    verifica = _strip_terminal_punctuation(_technical_rewrite_hint(_value(payload.get("verifica"))))
    riferimento = _value(payload.get("riferimento"))

    return (
        f"In data/ora {ricezione} veniva acquisita agli atti dell'ufficio la segnalazione n. {numero}, riferimento "
        f"{riferimento}, pervenuta con modalita {modalita} da {nominativo}, residente/domiciliato in {residenza}, "
        f"recapito telefonico {telefono}. La pratica risulta riferita al luogo indicato in {indirizzo} ed e stata "
        f"registrata dall'operatore ricevente {ricevente}.\n\n"
        f"Da quanto riferito dal segnalante emergeva quanto segue: {descrizione}. "
        f"La segnalazione veniva classificata nella categoria {categoria}, con priorita {priorita}, e risulta "
        f"allo stato di lavorazione {stato}.\n\n"
        f"Dagli atti risulta eventuale attivita di verifica in data {data_accertamento}, con indicazione "
        f"dell'agente verificatore {agente}. In sede di accertamento o aggiornamento della pratica veniva "
        f"registrato quanto segue: {verifica}.\n\n"
        "Per quanto registrato, la situazione viene rimessa all'ufficio competente per le valutazioni e gli "
        "eventuali interventi di competenza. La presente relazione viene redatta sulla base dei dati presenti "
        "in PassApp e resta agli atti dell'ufficio per la prosecuzione e la definizione della pratica."
    )


def generate_sopralluogo_verbale_with_gemini(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    if not ai_config.get("gemini_enabled_for_sopralluogo", True):
        return ""

    prompt = build_sopralluogo_verbale_prompt(payload, base_prompt=ai_config.get("gemini_base_prompt"))
    generated = _generate_with_ai(prompt, ai_config, max_output_tokens=1800)
    validated = _validate_sopralluogo_ai_text(generated, payload)
    if validated:
        return validated

    retry_prompt = (
        f"{prompt}\n\n"
        "Il testo precedente era troppo simile agli appunti grezzi o non rispettava le regole. Riscrivi "
        "completamente in linguaggio tecnico-amministrativo da Polizia Locale, senza copiare le frasi originali. "
        "Distingui chiaramente segnalazione ricevuta, attivita svolta, stato dei luoghi accertato, valutazione "
        "operativa e chiusura istituzionale. Restituisci solo il corpo del verbale."
    )
    retry = _generate_with_ai(retry_prompt, ai_config, max_output_tokens=1800)
    return _validate_sopralluogo_ai_text(retry, payload)


def generate_segnalazione_text_with_gemini(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    if not ai_config.get("gemini_enabled_for_segnalazione_pdf", True):
        return ""

    prompt = build_segnalazione_pdf_prompt(payload, base_prompt=ai_config.get("gemini_base_prompt"))
    generated = _generate_with_ai(prompt, ai_config, max_output_tokens=1400)
    validated = _validate_segnalazione_ai_text(generated, payload)
    if validated:
        return validated

    retry_prompt = (
        f"{prompt}\n\n"
        "Il testo precedente era troppo simile agli appunti grezzi. Riscrivi completamente in linguaggio "
        "tecnico-amministrativo da Polizia Locale, senza copiare le frasi originali. Distingui quanto riferito "
        "dal segnalante da quanto accertato o registrato dall'ufficio. Restituisci solo il corpo della relazione."
    )
    retry = _generate_with_ai(retry_prompt, ai_config, max_output_tokens=1400)
    return _validate_segnalazione_ai_text(retry, payload)


def prepare_sopralluogo_verbale(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    generated = generate_sopralluogo_verbale_with_gemini(payload, config=config)
    if generated:
        return generated, _ai_provider_label(config)
    return build_local_sopralluogo_verbale(payload), "locale"


def prepare_sopralluogo_verbale_text(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    return prepare_sopralluogo_verbale(payload, config=config)[0]


def prepare_segnalazione_pdf(payload: dict[str, Any], config: dict[str, Any] | None = None) -> tuple[str, str]:
    generated = generate_segnalazione_text_with_gemini(payload, config=config)
    if generated:
        return generated, _ai_provider_label(config)
    return build_local_segnalazione_text(payload), "locale"


def prepare_segnalazione_pdf_text(payload: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    return prepare_segnalazione_pdf(payload, config=config)[0]


def check_openrouter_connection(ai_config: dict[str, Any]) -> AiConnectionTestResult:
    api_key = str(ai_config.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    model = str(ai_config.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    if not api_key:
        return AiConnectionTestResult(False, "openrouter", model, "Chiave API OpenRouter mancante.")

    timeout = _safe_timeout(ai_config.get("gemini_timeout_seconds"))
    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Rispondi solo con la parola OK."}],
        "temperature": 0,
        "max_tokens": 8,
    }
    request = _build_openrouter_request(request_payload, api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return AiConnectionTestResult(False, "openrouter", model, _openrouter_http_error_detail(exc))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return AiConnectionTestResult(False, "openrouter", model, f"Test non riuscito: {exc}")

    text = _sanitize_generated_text(_extract_openrouter_response_text(response_data))
    if text:
        return AiConnectionTestResult(True, "openrouter", model, "Connessione OpenRouter riuscita.")
    return AiConnectionTestResult(False, "openrouter", model, "Risposta OpenRouter ricevuta, ma senza testo utilizzabile.")


def _generate_with_ai(prompt: str, ai_config: dict[str, Any], *, max_output_tokens: int) -> str:
    provider = _clean_provider(ai_config.get("provider"))
    if provider == "openrouter":
        return _generate_with_openrouter(prompt, ai_config, max_output_tokens=max_output_tokens)
    return _generate_with_gemini(prompt, ai_config, max_output_tokens=max_output_tokens)


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


def _generate_with_openrouter(prompt: str, ai_config: dict[str, Any], *, max_output_tokens: int) -> str:
    api_key = str(ai_config.get("openrouter_api_key") or os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        return ""

    model = str(ai_config.get("openrouter_model") or DEFAULT_OPENROUTER_MODEL).strip() or DEFAULT_OPENROUTER_MODEL
    timeout = _safe_timeout(ai_config.get("gemini_timeout_seconds"))
    request_payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": max_output_tokens,
    }
    request = _build_openrouter_request(request_payload, api_key)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return ""

    text = _extract_openrouter_response_text(response_data)
    return _sanitize_generated_text(text)


def _build_openrouter_request(request_payload: dict[str, Any], api_key: str) -> urllib.request.Request:
    data = json.dumps(request_payload, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(
        OPENROUTER_API_URL,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://passapp.local",
            "X-OpenRouter-Title": "PassApp",
        },
    )


def _openrouter_http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    body = _sanitize_generated_text(body)
    if body:
        return f"OpenRouter ha risposto con errore HTTP {exc.code}: {body[:500]}"
    return f"OpenRouter ha risposto con errore HTTP {exc.code}."


def _extract_response_text(response_data: dict[str, Any]) -> str:
    candidates = response_data.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))


def _extract_openrouter_response_text(response_data: dict[str, Any]) -> str:
    choices = response_data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return ""


def _sanitize_generated_text(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text[:6000].strip()


def _looks_like_raw_copy(
    generated: str,
    payload: dict[str, Any],
    fields: tuple[str, ...] = SOPRALLUOGO_COPY_FIELDS,
) -> bool:
    generated_normalized = _normalize_for_copy(generated)
    if not generated_normalized:
        return False

    matches = 0
    for field in fields:
        raw_value = _raw_payload_text(payload, field)
        raw_normalized = _normalize_for_copy(raw_value)
        if len(raw_normalized) < 45:
            continue

        for segment in _raw_copy_segments(raw_normalized):
            if segment in generated_normalized:
                matches += 1
                if len(segment) >= 90 or matches >= 2:
                    return True
                break
    return False


def _validate_sopralluogo_ai_text(generated: str, payload: dict[str, Any]) -> str:
    text = _strip_document_noise(generated, titles=("verbale di sopralluogo", "relazione di sopralluogo"))
    if len(text) < MIN_AI_TEXT_LENGTH:
        return ""
    if _looks_like_raw_copy(text, payload, SOPRALLUOGO_COPY_FIELDS):
        return ""
    if _contains_forbidden_phrases(text, ("sono andati sul luogo", "brutto tempo", "forse penzolante")):
        return ""
    return text


def _validate_segnalazione_ai_text(generated: str, payload: dict[str, Any]) -> str:
    text = _strip_document_noise(generated, titles=("relazione di segnalazione", "segnalazione"))
    if len(text) < MIN_AI_TEXT_LENGTH:
        return ""
    if _looks_like_raw_copy(text, payload, SEGNALAZIONE_COPY_FIELDS):
        return ""
    if _contains_forbidden_phrases(
        text,
        (
            "Il contenuto riferito dal segnalante e il seguente",
            "Il riscontro registrato e il seguente",
            "Riscontro registrato in app",
            "sono andati sul luogo",
            "brutto tempo",
            "forse penzolante",
        ),
    ):
        return ""
    return text


def _strip_document_noise(text: str, *, titles: tuple[str, ...]) -> str:
    text = _sanitize_generated_text(text)
    if not text:
        return ""

    text = re.sub(r"```(?:\w+)?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"[*_`#]+", "", text)

    cleaned_lines: list[str] = []
    skipped_title = False
    for line in text.splitlines():
        clean = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        normalized = _normalize_for_copy(clean)
        if not skipped_title and normalized in {_normalize_for_copy(title) for title in titles}:
            skipped_title = True
            continue
        cleaned_lines.append(clean)

    text = "\n".join(cleaned_lines)
    return _sanitize_generated_text(text)


def _contains_forbidden_phrases(text: str, phrases: tuple[str, ...]) -> bool:
    normalized = _normalize_for_copy(text)
    return any(_normalize_for_copy(phrase) in normalized for phrase in phrases)


def _raw_payload_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field, "")
    if isinstance(value, (list, tuple, set)):
        return " ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value or "")


def _normalize_for_copy(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[^\w\sàèéìòù']", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _raw_copy_segments(text: str, *, min_length: int = 55, window: int = 90) -> list[str]:
    if len(text) <= window:
        return [text] if len(text) >= min_length else []

    segments: list[str] = []
    start = 0
    step = 35
    while start < len(text):
        segment = text[start : start + window].strip()
        if len(segment) >= min_length:
            segments.append(segment)
        start += step
    return segments


def _technical_rewrite_hint(text: str) -> str:
    result = str(text or "").strip()
    if not result:
        return "-"

    replacements = (
        (
            "non appena passa il brutto tempo",
            "non appena cessano le condizioni meteorologiche non favorevoli",
        ),
        (
            "quando passa il brutto tempo",
            "quando cessano le condizioni meteorologiche non favorevoli",
        ),
        ("probabilità che cada sulla strada", "possibile interessamento della sede stradale"),
        ("probabilita che cada sulla strada", "possibile interessamento della sede stradale"),
        ("cade sulla strada", "possa interessare la sede stradale"),
        ("brutto tempo", "condizioni meteorologiche non favorevoli"),
        ("forse penzolante", "presumibilmente parzialmente sospeso"),
        ("penzolante", "parzialmente sospeso"),
        ("forse", "presumibilmente"),
        ("sono andati sul luogo", "si sono portati presso il luogo indicato"),
        ("non provocando pericoli", "senza evidenziare, al momento dell'accertamento, elementi di pericolo immediato"),
        ("Un cittadino ha segnalato", "Secondo quanto riferito dal segnalante risulta"),
        ("un cittadino ha segnalato", "secondo quanto riferito dal segnalante risulta"),
    )
    for old, new in replacements:
        result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", result).strip()


def _strip_terminal_punctuation(text: str) -> str:
    return re.sub(r"[.;:\s]+$", "", str(text or "").strip())


def _clean_model_name(value: str) -> str:
    value = value.strip() or DEFAULT_MODEL
    return value.split("/")[-1]


def _clean_provider(value: Any) -> str:
    provider = str(value or "gemini").strip().lower()
    return provider if provider in {"gemini", "openrouter"} else "gemini"


def _ai_provider_label(config: dict[str, Any] | None = None) -> str:
    config = config or load_config()
    ai_config = config.get("ai", {}) if isinstance(config, dict) else {}
    return _clean_provider(ai_config.get("provider"))


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
        "Alla data di generazione del presente atto non risulta acquisita documentazione fotografica nel fascicolo "
        f"digitale. Nel fascicolo digitale risultano n. {documenti_count} documenti."
    )


def _value(value: Any, fallback: str = "-") -> str:
    text = str(value or "").strip()
    return text if text else fallback
