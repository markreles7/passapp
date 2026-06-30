import json
import unittest
from unittest.mock import patch

from core.gemini_verbale import (
    DEFAULT_BASE_PROMPT,
    _looks_like_raw_copy,
    _validate_segnalazione_ai_text,
    _validate_sopralluogo_ai_text,
    build_local_segnalazione_text,
    build_local_sopralluogo_verbale,
    build_segnalazione_pdf_prompt,
    build_sopralluogo_verbale_prompt,
    generate_segnalazione_text_with_gemini,
    generate_sopralluogo_verbale_with_gemini,
    prepare_sopralluogo_verbale,
    prepare_segnalazione_pdf_text,
    prepare_sopralluogo_verbale_text,
    check_openrouter_connection,
)


PAYLOAD = {
    "segnalazione_numero": "12",
    "segnalazione_data": "04/05/2026",
    "segnalante": "Mario Rossi",
    "indirizzo_segnalazione": "Via Roma 1",
    "descrizione": "Ramo pericolante",
    "id_sopralluogo": "3",
    "stato": "effettuato",
    "data_ora": "05/05/2026 - 10:30",
    "luogo": "Via Roma 1",
    "operatori": "Agente Verdi",
    "esito": "Area verificata",
    "note": "Richiesto intervento tecnico",
    "foto": "Si",
    "foto_count": "2",
    "documenti_count": "1",
    "atti": "Si",
    "ufficio": "Ufficio tecnico",
    "data_generazione": "06/05/2026",
}

RAW_SOPRALLUOGO_PAYLOAD = {
    **PAYLOAD,
    "descrizione": (
        "Un cittadino ha segnalato un ramo spezzato forse penzolante in Strada Argine Cantone, accanto al "
        "Caseificio, con probabilità che cada sulla strada."
    ),
    "esito": (
        "L'agente Muzzica Marco insieme all'Ufficio Tecnico - Manfredini Alice, sono andati sul luogo, constatando "
        "che la pianta ha la base intatta, a circa metà della base c'è una diramazione, dovuta forse al forte vento. "
        "La parte spezzata della diramazione è appoggiata ad altri rami dell'albero che la sorreggono, e comunque "
        "rivolta verso l'esterno della carreggiata non provocando pericoli."
    ),
    "note": "Programmata una potatura non appena passa il brutto tempo.",
    "foto": "No",
    "foto_count": "0",
}

SEGNALAZIONE_PAYLOAD = {
    "numero": "1",
    "anno": "2026",
    "stato": "In corso",
    "data_ora_ricezione": "08/05/2026 - 14:05",
    "nominativo": "Claudia Malavasi",
    "residenza": "San Lorenzo",
    "indirizzo": "Viale San Lorenzo 1",
    "telefono": "333",
    "modalita": "Telefonicamente",
    "categoria": "Animali",
    "priorita": "Media",
    "stato_lavorazione": "Sopralluogo da programmare",
    "ricevente": "Muzzica Marco",
    "descrizione": "Segnalata presenza di animale in area privata.",
    "agente": "Muzzica Marco",
    "data_accertamento": "08/05/2026",
    "verifica": "Da programmare sopralluogo.",
    "riferimento": "1/2026",
}

RAW_SEGNALAZIONE_PAYLOAD = {
    **SEGNALAZIONE_PAYLOAD,
    "categoria": "Verde pubblico",
    "indirizzo": "Strada Argine Cantone",
    "descrizione": (
        "Un cittadino ha segnalato un ramo spezzato forse penzolante in Strada Argine Cantone, accanto al "
        "Caseificio, con probabilità che cada sulla strada."
    ),
    "verifica": (
        "L'agente Muzzica Marco insieme all'Ufficio Tecnico - Manfredini Alice, sono andati sul luogo, constatando "
        "che la pianta ha la base intatta, a circa metà della base c'è una diramazione, dovuta forse al forte vento. "
        "La parte spezzata della diramazione è appoggiata ad altri rami dell'albero che la sorreggono, e comunque "
        "rivolta verso l'esterno della carreggiata non provocando pericoli. Programmata una potatura non appena "
        "passa il brutto tempo."
    ),
}

VALID_SOPRALLUOGO_TEXT = (
    "Con riferimento alla segnalazione acquisita agli atti, gli operatori di Polizia Locale si sono portati presso "
    "il luogo indicato per lo svolgimento degli accertamenti di competenza. Al momento del sopralluogo veniva "
    "verificata la situazione presente sul posto, distinguendo quanto riferito in fase di segnalazione da quanto "
    "direttamente constatato. Allo stato dei luoghi non venivano riportati elementi ulteriori rispetto alla verifica "
    "effettuata, ferma restando la possibilita di interessare l'ufficio competente per le valutazioni successive. "
    "Tanto si riferisce per quanto di competenza."
)

VALID_SEGNALAZIONE_TEXT = (
    "In data indicata veniva acquisita agli atti dell'ufficio una segnalazione relativa al luogo registrato in "
    "PassApp. Secondo quanto riferito dal segnalante, la pratica riguardava una possibile criticita da sottoporre "
    "alle valutazioni dell'ufficio competente. Dagli atti risulta successiva attivita di verifica, ove indicata, "
    "con registrazione dell'esito in forma tecnico-amministrativa. Per quanto registrato, la relazione resta agli "
    "atti dell'ufficio per la prosecuzione della pratica e per gli eventuali provvedimenti di competenza."
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class TestGeminiVerbale(unittest.TestCase):
    def test_sopralluogo_prompt_contains_anti_copy_and_technical_structure(self):
        prompt = build_sopralluogo_verbale_prompt(RAW_SOPRALLUOGO_PAYLOAD)
        prompt_lower = prompt.lower()

        self.assertIn("verbale/relazione", prompt)
        self.assertIn("regole anti-copia", prompt_lower)
        self.assertIn("struttura obbligatoria", prompt_lower)
        self.assertIn("non copiare", prompt_lower)
        self.assertIn("relazione tecnico-amministrativa", prompt_lower)
        self.assertIn(DEFAULT_BASE_PROMPT, prompt)
        self.assertIn("Dati grezzi", prompt)

    def test_segnalazione_prompt_contains_anti_copy_and_required_structure(self):
        prompt = build_segnalazione_pdf_prompt(RAW_SEGNALAZIONE_PAYLOAD)
        prompt_lower = prompt.lower()

        self.assertIn("non copiare", prompt_lower)
        self.assertIn("linguaggio tecnico-amministrativo", prompt_lower)
        self.assertIn("distingui quanto riferito da quanto accertato", prompt_lower)
        self.assertIn("struttura obbligatoria", prompt_lower)
        self.assertIn("dati grezzi disponibili", prompt_lower)

    def test_looks_like_raw_copy_detects_copied_sopralluogo_notes(self):
        generated = (
            "All'esito dell'accertamento risulta quanto segue: "
            + RAW_SOPRALLUOGO_PAYLOAD["esito"]
            + " "
            + RAW_SOPRALLUOGO_PAYLOAD["note"]
        )

        self.assertTrue(_looks_like_raw_copy(generated, RAW_SOPRALLUOGO_PAYLOAD))

    def test_validate_sopralluogo_ai_text_rejects_raw_copy(self):
        copied_text = (
            "Verbale di sopralluogo\n"
            "Con riferimento alla pratica, "
            + RAW_SOPRALLUOGO_PAYLOAD["esito"]
            + " "
            + RAW_SOPRALLUOGO_PAYLOAD["note"]
        )

        self.assertEqual(_validate_sopralluogo_ai_text(copied_text, RAW_SOPRALLUOGO_PAYLOAD), "")

    def test_validate_segnalazione_ai_text_rejects_raw_copy_and_forbidden_phrases(self):
        copied_text = (
            "Relazione di segnalazione\n"
            "Il contenuto riferito dal segnalante e il seguente: "
            + RAW_SEGNALAZIONE_PAYLOAD["descrizione"]
            + " Il riscontro registrato e il seguente: "
            + RAW_SEGNALAZIONE_PAYLOAD["verifica"]
        )

        self.assertEqual(_validate_segnalazione_ai_text(copied_text, RAW_SEGNALAZIONE_PAYLOAD), "")

    def test_local_sopralluogo_fallback_uses_technical_language(self):
        text = build_local_sopralluogo_verbale(RAW_SOPRALLUOGO_PAYLOAD)

        self.assertNotIn("sono andati sul luogo", text)
        self.assertNotIn("brutto tempo", text)
        self.assertNotIn("Le note operative riportate", text)
        self.assertIn("Al momento del sopralluogo", text)
        self.assertIn("per quanto di competenza", text)
        self.assertIn("condizioni meteorologiche", text)

    def test_local_segnalazione_fallback_uses_technical_language(self):
        text = build_local_segnalazione_text(RAW_SEGNALAZIONE_PAYLOAD)

        self.assertNotIn("Il contenuto riferito dal segnalante e il seguente", text)
        self.assertNotIn("Il riscontro registrato e il seguente", text)
        self.assertNotIn("sono andati sul luogo", text)
        self.assertNotIn("brutto tempo", text)
        self.assertNotIn("forse penzolante", text)
        self.assertIn("veniva acquisita", text)
        self.assertIn("agli atti", text)
        self.assertIn("Per quanto", text)
        self.assertIn("ufficio", text)
        self.assertIn("competenza", text)

    def test_missing_api_key_returns_empty_without_call(self):
        config = {"ai": {"gemini_api_key": "", "gemini_enabled_for_sopralluogo": True}}
        with patch("core.gemini_verbale.urllib.request.urlopen") as urlopen:
            self.assertEqual(generate_sopralluogo_verbale_with_gemini(PAYLOAD, config=config), "")
            urlopen.assert_not_called()

    def test_gemini_response_text_is_extracted_and_validated(self):
        config = {
            "ai": {
                "gemini_api_key": "test-key",
                "gemini_model": "gemini-3-flash-preview",
                "gemini_enabled_for_sopralluogo": True,
                "gemini_timeout_seconds": 10,
            }
        }
        response = {"candidates": [{"content": {"parts": [{"text": VALID_SOPRALLUOGO_TEXT}]}}]}
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            text = generate_sopralluogo_verbale_with_gemini(PAYLOAD, config=config)

        self.assertEqual(text, VALID_SOPRALLUOGO_TEXT)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    def test_segnalazione_gemini_response_text_is_extracted_and_validated(self):
        config = {
            "ai": {
                "gemini_api_key": "test-key",
                "gemini_model": "gemini-3-flash-preview",
                "gemini_enabled_for_segnalazione_pdf": True,
                "gemini_timeout_seconds": 10,
            }
        }
        response = {"candidates": [{"content": {"parts": [{"text": VALID_SEGNALAZIONE_TEXT}]}}]}
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)):
            text = generate_segnalazione_text_with_gemini(SEGNALAZIONE_PAYLOAD, config=config)

        self.assertEqual(text, VALID_SEGNALAZIONE_TEXT)

    def test_openrouter_response_text_is_extracted_and_validated(self):
        config = {
            "ai": {
                "provider": "openrouter",
                "openrouter_api_key": "or-test-key",
                "openrouter_model": "openrouter/openrouter/free",
                "gemini_enabled_for_sopralluogo": True,
                "gemini_timeout_seconds": 10,
            }
        }
        response = {"choices": [{"message": {"content": VALID_SOPRALLUOGO_TEXT}}]}
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            text = generate_sopralluogo_verbale_with_gemini(PAYLOAD, config=config)

        self.assertEqual(text, VALID_SOPRALLUOGO_TEXT)
        request = urlopen.call_args.args[0]
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request_body["model"], "openrouter/openrouter/free")
        self.assertEqual(request_body["messages"][0]["content"], build_sopralluogo_verbale_prompt(PAYLOAD))
        self.assertEqual(request.get_header("Authorization"), "Bearer or-test-key")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    def test_prepare_reports_openrouter_source_when_configured(self):
        config = {
            "ai": {
                "provider": "openrouter",
                "openrouter_api_key": "or-test-key",
                "openrouter_model": "openrouter/openrouter/free",
                "gemini_enabled_for_sopralluogo": True,
            }
        }
        response = {"choices": [{"message": {"content": VALID_SOPRALLUOGO_TEXT}}]}
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)):
            text, source = prepare_sopralluogo_verbale(PAYLOAD, config=config)

        self.assertEqual(text, VALID_SOPRALLUOGO_TEXT)
        self.assertEqual(source, "openrouter")

    def test_openrouter_connection_test_requires_key(self):
        with (
            patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}),
            patch("core.gemini_verbale.urllib.request.urlopen") as urlopen,
        ):
            result = check_openrouter_connection({"openrouter_api_key": "", "openrouter_model": "openrouter/openrouter/free"})

        self.assertFalse(result.ok)
        self.assertIn("mancante", result.detail)
        urlopen.assert_not_called()

    def test_openrouter_connection_test_uses_minimal_request(self):
        response = {"choices": [{"message": {"content": "OK"}}]}
        config = {
            "openrouter_api_key": "or-test-key",
            "openrouter_model": "openrouter/openrouter/free",
            "gemini_timeout_seconds": 10,
        }
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            result = check_openrouter_connection(config)

        self.assertTrue(result.ok)
        self.assertEqual(result.model, "openrouter/openrouter/free")
        request = urlopen.call_args.args[0]
        request_body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request.full_url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(request_body["max_tokens"], 8)
        self.assertEqual(request_body["model"], "openrouter/openrouter/free")
        self.assertEqual(request.get_header("Authorization"), "Bearer or-test-key")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    def test_prepare_falls_back_to_local_text(self):
        config = {"ai": {"gemini_api_key": "", "gemini_enabled_for_sopralluogo": True}}

        text = prepare_sopralluogo_verbale_text(PAYLOAD, config=config)

        self.assertEqual(text, build_local_sopralluogo_verbale(PAYLOAD))
        self.assertIn("segnalazione n. 12", text)

    def test_prepare_segnalazione_falls_back_to_local_text(self):
        config = {"ai": {"gemini_api_key": "", "gemini_enabled_for_segnalazione_pdf": True}}

        text = prepare_segnalazione_pdf_text(SEGNALAZIONE_PAYLOAD, config=config)

        self.assertEqual(text, build_local_segnalazione_text(SEGNALAZIONE_PAYLOAD))
        self.assertIn("segnalazione n. 1", text)


if __name__ == "__main__":
    unittest.main()
