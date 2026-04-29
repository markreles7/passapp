import json
import tempfile
import unittest
from pathlib import Path

import segnalazioni as seg_mod
from segnalazioni import (
    Segnalazione,
    SegnalazioniFrame,
    normalize_priorita,
    segnalazione_matches_filters,
)


class TestSegnalazioniJsonPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.old_data_dir = seg_mod.DATA_DIR
        self.old_file = seg_mod.SEGNALAZIONI_FILE
        self.old_backup = seg_mod.SEGNALAZIONI_BACKUP_FILE
        seg_mod.DATA_DIR = self.tmp_path
        seg_mod.SEGNALAZIONI_FILE = self.tmp_path / "segnalazioni.json"
        seg_mod.SEGNALAZIONI_BACKUP_FILE = self.tmp_path / "segnalazioni.json.bak"

    def tearDown(self):
        seg_mod.DATA_DIR = self.old_data_dir
        seg_mod.SEGNALAZIONI_FILE = self.old_file
        seg_mod.SEGNALAZIONI_BACKUP_FILE = self.old_backup
        self.tmpdir.cleanup()

    def _frame_stub(self):
        frame = SegnalazioniFrame.__new__(SegnalazioniFrame)
        frame.segnalazioni = []
        frame._next_progressivo = 1
        frame._save_error_notified = False
        return frame

    def test_save_and_load_roundtrip(self):
        frame = self._frame_stub()
        frame.segnalazioni = [
            Segnalazione(
                numero_progressivo=1,
                anno="2026",
                mese="03",
                giorno="10",
                ora="09:15",
                nominativo="Mario Rossi",
                descrizione_segnalazione="Test segnalazione",
                ricevente="Ufficio",
                stato="in_corso",
            )
        ]

        self.assertTrue(frame._save_to_disk())
        self.assertTrue(seg_mod.SEGNALAZIONI_FILE.exists())

        loaded = self._frame_stub()
        loaded._load_from_disk()
        self.assertEqual(len(loaded.segnalazioni), 1)
        self.assertEqual(loaded.segnalazioni[0].nominativo, "Mario Rossi")
        self.assertEqual(loaded._next_progressivo, 2)

    def test_load_invalid_json_is_graceful(self):
        seg_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        seg_mod.SEGNALAZIONI_FILE.write_text("{invalid json", encoding="utf-8")

        frame = self._frame_stub()
        frame._load_from_disk()

        self.assertEqual(frame.segnalazioni, [])
        self.assertEqual(frame._next_progressivo, 1)

    def test_load_uses_backup_when_primary_is_invalid(self):
        seg_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        seg_mod.SEGNALAZIONI_FILE.write_text("{invalid json", encoding="utf-8")
        backup_payload = {
            "segnalazioni": [
                {
                    "numero_progressivo": 9,
                    "anno": "2026",
                    "mese": "03",
                    "giorno": "11",
                    "ora": "09:00",
                    "nominativo": "Backup User",
                    "stato": "in_corso",
                }
            ]
        }
        seg_mod.SEGNALAZIONI_BACKUP_FILE.write_text(json.dumps(backup_payload), encoding="utf-8")

        frame = self._frame_stub()
        frame._load_from_disk()

        self.assertEqual(len(frame.segnalazioni), 1)
        self.assertEqual(frame.segnalazioni[0].numero_progressivo, 9)
        self.assertEqual(frame._next_progressivo, 10)

    def test_load_legacy_list_payload(self):
        seg_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        legacy_payload = [
            {
                "numero_progressivo": 7,
                "anno": "2026",
                "mese": "03",
                "giorno": "10",
                "ora": "11:00",
                "nominativo": "Legacy User",
            }
        ]
        seg_mod.SEGNALAZIONI_FILE.write_text(json.dumps(legacy_payload), encoding="utf-8")

        frame = self._frame_stub()
        frame._load_from_disk()

        self.assertEqual(len(frame.segnalazioni), 1)
        self.assertEqual(frame.segnalazioni[0].numero_progressivo, 7)
        self.assertEqual(frame._next_progressivo, 8)

    def test_load_old_record_without_category_priority_uses_defaults(self):
        seg_mod.DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "segnalazioni": [
                {
                    "numero_progressivo": 3,
                    "anno": "2026",
                    "mese": "04",
                    "giorno": "28",
                    "ora": "10:00",
                    "nominativo": "Vecchio Record",
                    "stato": "in_corso",
                }
            ]
        }
        seg_mod.SEGNALAZIONI_FILE.write_text(json.dumps(payload), encoding="utf-8")

        frame = self._frame_stub()
        frame._load_from_disk()

        self.assertEqual(frame.segnalazioni[0].categoria, "Altro")
        self.assertEqual(frame.segnalazioni[0].priorita, "Media")
        self.assertEqual(frame.segnalazioni[0].stato_lavorazione, "Aperta")

    def test_normalize_priorita(self):
        self.assertEqual(normalize_priorita("alta priorita"), "Alta")
        self.assertEqual(normalize_priorita("urgent"), "Urgente")
        self.assertEqual(normalize_priorita(""), "Media")

    def test_filter_priority_and_category(self):
        seg = Segnalazione(
            numero_progressivo=4,
            anno="2026",
            mese="04",
            giorno="28",
            ora="10:00",
            nominativo="Mario Rossi",
            categoria="Viabilita",
            priorita="Urgente",
            stato_lavorazione="In lavorazione",
        )

        self.assertTrue(segnalazione_matches_filters(seg, categoria="Viabilita", priorita="Urgente"))
        self.assertTrue(segnalazione_matches_filters(seg, solo_urgenti=True))
        self.assertFalse(segnalazione_matches_filters(seg, categoria="Sosta"))
        self.assertFalse(segnalazione_matches_filters(seg, priorita="Bassa"))


if __name__ == "__main__":
    unittest.main()
