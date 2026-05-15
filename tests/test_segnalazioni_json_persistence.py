import json
import tempfile
import unittest
from pathlib import Path

from core.segnalazioni import (
    Segnalazione,
    load_segnalazioni,
    next_progressivo,
    normalize_priorita,
    save_segnalazioni,
    segnalazione_matches_filters,
)


class TestSegnalazioniJsonPersistence(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "segnalazioni.json"
            backup = Path(tmp_dir) / "segnalazioni.json.bak"
            save_segnalazioni(
                [
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
                ],
                path,
                backup,
            )

            loaded, source = load_segnalazioni(path, backup)
            self.assertEqual(source, path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].nominativo, "Mario Rossi")
            self.assertEqual(next_progressivo(loaded), 2)

    def test_load_invalid_json_is_graceful(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "segnalazioni.json"
            backup = Path(tmp_dir) / "segnalazioni.json.bak"
            path.write_text("{invalid json", encoding="utf-8")

            loaded, source = load_segnalazioni(path, backup)

            self.assertEqual(loaded, [])
            self.assertIsNone(source)
            self.assertEqual(next_progressivo(loaded), 1)

    def test_load_uses_backup_when_primary_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "segnalazioni.json"
            backup = Path(tmp_dir) / "segnalazioni.json.bak"
            path.write_text("{invalid json", encoding="utf-8")
            backup.write_text(
                json.dumps(
                    {
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
                ),
                encoding="utf-8",
            )

            loaded, source = load_segnalazioni(path, backup)

            self.assertEqual(source, backup)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].numero_progressivo, 9)
            self.assertEqual(next_progressivo(loaded), 10)

    def test_load_legacy_list_payload(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "segnalazioni.json"
            backup = Path(tmp_dir) / "segnalazioni.json.bak"
            path.write_text(
                json.dumps(
                    [
                        {
                            "numero_progressivo": 7,
                            "anno": "2026",
                            "mese": "03",
                            "giorno": "10",
                            "ora": "11:00",
                            "nominativo": "Legacy User",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            loaded, _source = load_segnalazioni(path, backup)

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].numero_progressivo, 7)
            self.assertEqual(next_progressivo(loaded), 8)

    def test_load_old_record_without_category_priority_uses_defaults(self):
        seg = Segnalazione.from_dict(
            {
                "numero_progressivo": 3,
                "anno": "2026",
                "mese": "04",
                "giorno": "28",
                "ora": "10:00",
                "nominativo": "Vecchio Record",
                "stato": "in_corso",
            }
        )

        self.assertIsNotNone(seg)
        assert seg is not None
        self.assertEqual(seg.categoria, "Altro")
        self.assertEqual(seg.priorita, "Media")
        self.assertEqual(seg.stato_lavorazione, "Aperta")

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
