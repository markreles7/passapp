import json
import unittest
from unittest.mock import patch

from core.gemini_verbale import (
    build_local_sopralluogo_verbale,
    build_sopralluogo_verbale_prompt,
    generate_sopralluogo_verbale_with_gemini,
    prepare_sopralluogo_verbale_text,
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
    def test_prompt_is_limited_to_verbale_and_available_facts(self):
        prompt = build_sopralluogo_verbale_prompt(PAYLOAD)

        self.assertIn("verbale di sopralluogo", prompt)
        self.assertIn("Usa esclusivamente i dati forniti", prompt)
        self.assertIn("Ramo pericolante", prompt)
        self.assertIn("Agente Verdi", prompt)

    def test_missing_api_key_returns_empty_without_call(self):
        config = {"ai": {"gemini_api_key": "", "gemini_enabled_for_sopralluogo": True}}
        with patch("core.gemini_verbale.urllib.request.urlopen") as urlopen:
            self.assertEqual(generate_sopralluogo_verbale_with_gemini(PAYLOAD, config=config), "")
            urlopen.assert_not_called()

    def test_gemini_response_text_is_extracted(self):
        config = {
            "ai": {
                "gemini_api_key": "test-key",
                "gemini_model": "gemini-3-flash-preview",
                "gemini_enabled_for_sopralluogo": True,
                "gemini_timeout_seconds": 10,
            }
        }
        response = {"candidates": [{"content": {"parts": [{"text": "Verbale generato da test."}]}}]}
        with patch("core.gemini_verbale.urllib.request.urlopen", return_value=FakeResponse(response)) as urlopen:
            text = generate_sopralluogo_verbale_with_gemini(PAYLOAD, config=config)

        self.assertEqual(text, "Verbale generato da test.")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    def test_prepare_falls_back_to_local_text(self):
        config = {"ai": {"gemini_api_key": "", "gemini_enabled_for_sopralluogo": True}}

        text = prepare_sopralluogo_verbale_text(PAYLOAD, config=config)

        self.assertEqual(text, build_local_sopralluogo_verbale(PAYLOAD))
        self.assertIn("segnalazione n. 12", text)


if __name__ == "__main__":
    unittest.main()
