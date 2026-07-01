import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from core.fascicoli import add_attachment
from core.sopralluoghi import Sopralluogo
from qt_app import sopralluoghi_pdf
from qt_app.sopralluoghi_pdf import (
    PHOTO_CAPTION_FALLBACK,
    build_pdf_payload,
    build_verbale_recipients,
    build_verbale_subject,
    enrich_photo_descriptions_with_ai,
    safe_pdf_filename,
)


@dataclass
class SegnalazioneStub:
    numero_progressivo: int = 42
    anno: str = "2026"
    mese: str = "05"
    giorno: str = "04"
    nominativo: str = "Mario Rossi"
    indirizzo: str = "Via Roma 1"
    descrizione_segnalazione: str = "Ramo pericolante"


class TestSopralluoghiPdf(unittest.TestCase):
    def test_safe_pdf_filename_falls_back(self):
        self.assertEqual(safe_pdf_filename(""), "sopralluogo")
        self.assertEqual(safe_pdf_filename("Via Roma / 1"), "Via_Roma_1")

    def test_payload_contains_professional_summary_and_attachment_counts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            registry = root / "fascicoli.json"
            base_dir = root / "fascicoli"
            photo = root / "foto.jpg"
            photo.write_bytes(b"image")
            document = root / "relazione.pdf"
            document.write_bytes(b"pdf")
            segnalazione = SegnalazioneStub()
            add_attachment(
                segnalazione,
                photo,
                "foto",
                descrizione="Dissesto lato nord",
                registry_path=registry,
                base_dir=base_dir,
            )
            add_attachment(segnalazione, document, "documento", registry_path=registry, base_dir=base_dir)
            sopralluogo = Sopralluogo(
                id_sopralluogo=7,
                segnalazione_id=42,
                data_sopralluogo="05/05/2026",
                ora_sopralluogo="10:30",
                operatori="Agente Verdi",
                luogo="Via Roma 1",
                esito="Area verificata",
                note_operative="Richiesto intervento tecnico",
                presenza_foto_allegati=True,
                ulteriori_atti=True,
                ufficio_destinatario="Ufficio tecnico",
                stato="effettuato",
            )

            payload = build_pdf_payload(segnalazione, sopralluogo, registry_path=registry)

            self.assertEqual(payload["foto_count"], "1")
            self.assertEqual(payload["documenti_count"], "1")
            self.assertEqual(payload["allegati_count"], "2")
            self.assertEqual(payload["firma_operatori"], "Agente Verdi")
            payload["oggetto_verbale"] = build_verbale_subject(payload)
            self.assertIn("Ramo pericolante", payload["oggetto_verbale"])
            self.assertIn("n. 42", payload["oggetto_verbale"])
            self.assertEqual(payload["foto_items"][0]["descrizione"], "Dissesto lato nord")

    def test_recipients_follow_destination_office(self):
        self.assertEqual(build_verbale_recipients("Polizia Locale"), ["AL COMANDANTE DEL SERVIZIO DI POLIZIA LOCALE", "Sede"])
        self.assertEqual(build_verbale_recipients("Ufficio Tecnico"), ["AL RESPONSABILE DEL SETTORE TECNICO", "Sede"])
        self.assertEqual(
            build_verbale_recipients("Polizia Locale e Ufficio Tecnico"),
            [
                "AL COMANDANTE DEL SERVIZIO DI POLIZIA LOCALE",
                "Sede",
                "AL RESPONSABILE DEL SETTORE TECNICO",
                "Sede",
            ],
        )

    def test_photo_descriptions_are_generated_only_when_missing(self):
        payload = {
            "luogo": "Str. Mantovana 62",
            "descrizione": "Vegetazione presente a bordo strada",
            "foto_items": [
                {"path": "foto_1.jpg", "descrizione": ""},
                {"path": "foto_2.jpg", "descrizione": "Descrizione gia presente"},
            ],
        }
        with patch(
            "qt_app.sopralluoghi_pdf.generate_photo_caption_with_ai",
            return_value="Veduta dell'area stradale con vegetazione ai margini.",
        ) as generator:
            enrich_photo_descriptions_with_ai(payload, config={"ai": {"provider": "openrouter"}})

        self.assertEqual(payload["foto_items"][0]["descrizione"], "Veduta dell'area stradale con vegetazione ai margini.")
        self.assertEqual(payload["foto_items"][1]["descrizione"], "Descrizione gia presente")
        generator.assert_called_once()

    def test_photo_description_falls_back_when_ai_is_unavailable(self):
        payload = {"foto_items": [{"path": "foto_1.jpg", "descrizione": ""}]}
        with patch("qt_app.sopralluoghi_pdf.generate_photo_caption_with_ai", return_value=""):
            enrich_photo_descriptions_with_ai(payload, config={"ai": {"provider": "openrouter"}})

        self.assertEqual(payload["foto_items"][0]["descrizione"], PHOTO_CAPTION_FALLBACK)

    def test_template_renderer_does_not_replace_long_ai_text_as_token(self):
        source = Path(sopralluoghi_pdf.__file__).read_text(encoding="utf-8")

        self.assertNotIn('"VERBALE_GENERATO" = $payload.verbale_generato', source)
        self.assertIn("$clearRange = $doc.Range()", source)
        self.assertIn("[void]$clearRange.Delete()", source)
        self.assertIn("OGGETTO: ", source)
        self.assertIn("foreach ($destinatario in @($payload.destinatari))", source)
        self.assertIn("Add-LongText -Selection $sel -Text ([string]$payload.verbale_generato)", source)
        self.assertIn("Add-Paragraph -Selection $Selection -Text $caption -Size 9 -Alignment 1", source)


if __name__ == "__main__":
    unittest.main()
