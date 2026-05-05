import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.fascicoli import add_attachment
from core.sopralluoghi import Sopralluogo
from qt_app.sopralluoghi_pdf import build_pdf_payload, safe_pdf_filename


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
            self.assertIn("segnalazione n. 42", payload["oggetto_verbale"])
            self.assertEqual(payload["foto_items"][0]["descrizione"], "Dissesto lato nord")


if __name__ == "__main__":
    unittest.main()
