import unittest
from unittest.mock import patch

from core.fascicoli import FascicoloAttachment
from core.sopralluoghi import Sopralluogo
from qt_app.segnalazioni import SegnalazioniPage
from segnalazioni import Segnalazione


class TestPassAppQtEndToEnd(unittest.TestCase):
    def test_complete_signal_to_inspection_workflow_reaches_100_percent(self):
        seg = Segnalazione(
            numero_progressivo=77,
            anno="2026",
            mese="05",
            giorno="05",
            ora="09:15",
            nominativo="Mario Rossi",
            indirizzo="Via Roma 1",
            telefono="0376",
            descrizione_segnalazione="Verifica area pubblica",
            categoria="Altro",
            priorita="Media",
            stato_lavorazione="Aperta",
            stato="in_corso",
        )
        attachments = [
            FascicoloAttachment(1, 77, "foto/foto.jpg", "foto.jpg", "foto", "segnalazione", "2026-05-05 09:20"),
            FascicoloAttachment(
                2,
                77,
                "documenti/SEGNALAZIONE_77.pdf",
                "SEGNALAZIONE_77.pdf",
                "documento",
                "segnalazione",
                "2026-05-05 09:30",
            ),
            FascicoloAttachment(
                3,
                77,
                "sopralluoghi/SOPRALLUOGO_77_1.pdf",
                "SOPRALLUOGO_77_1.pdf",
                "scheda_sopralluogo",
                "sopralluogo",
                "2026-05-05 10:30",
                sopralluogo_id=1,
            ),
        ]
        sopralluoghi = [
            Sopralluogo(
                id_sopralluogo=1,
                segnalazione_id=77,
                data_sopralluogo="05/05/2026",
                ora_sopralluogo="10:00",
                operatori="Agente Verdi",
                luogo="Via Roma 1",
                esito="Sopralluogo effettuato",
                note_operative="Nessuna ulteriore criticita",
                presenza_foto_allegati=True,
                stato="effettuato",
            )
        ]
        page = SegnalazioniPage.__new__(SegnalazioniPage)

        with patch("qt_app.segnalazioni.fascicolo_exists", return_value=True), patch(
            "qt_app.segnalazioni.list_attachments", return_value=attachments
        ), patch("qt_app.segnalazioni.list_for_segnalazione", return_value=sopralluoghi):
            state = page.workflow_state(seg)

        self.assertEqual(state["percent"], 100)
        self.assertEqual(state["done"], state["total"])
        self.assertIsNone(state["next_step"])
        self.assertEqual(state["missing"], [])


if __name__ == "__main__":
    unittest.main()
