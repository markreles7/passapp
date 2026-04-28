import tempfile
import unittest
from pathlib import Path

from core.sopralluoghi import (
    STATI_SOPRALLUOGO,
    Sopralluogo,
    delete_sopralluogo,
    list_for_segnalazione,
    load_sopralluoghi,
    next_sopralluogo_id,
    save_sopralluoghi,
    upsert_sopralluogo,
    validate_sopralluogo,
)


class TestSopralluoghi(unittest.TestCase):
    def test_save_load_and_filter_by_segnalazione(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sopralluoghi.json"
            records = [
                Sopralluogo(1, 10, "28/04/2026", operatori="Agente A"),
                Sopralluogo(2, 11, "29/04/2026", operatori="Agente B"),
            ]

            save_sopralluoghi(records, path)

            self.assertEqual(len(load_sopralluoghi(path)), 2)
            linked = list_for_segnalazione(10, path)
            self.assertEqual(len(linked), 1)
            self.assertEqual(linked[0].id_sopralluogo, 1)

    def test_upsert_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "sopralluoghi.json"
            item = Sopralluogo(1, 10, "28/04/2026", operatori="Agente A")

            upsert_sopralluogo(item, path)
            item.esito = "Verificato"
            upsert_sopralluogo(item, path)

            records = load_sopralluoghi(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].esito, "Verificato")

            delete_sopralluogo(1, path)
            self.assertEqual(load_sopralluoghi(path), [])

    def test_next_id_and_validation(self):
        records = [
            Sopralluogo(1, 10, "28/04/2026", operatori="Agente A"),
            Sopralluogo(7, 10, "29/04/2026", operatori="Agente B"),
        ]
        self.assertEqual(next_sopralluogo_id(records), 8)

        invalid = Sopralluogo(1, 10, "data errata", operatori="Agente A")
        self.assertFalse(validate_sopralluogo(invalid)[0])

        missing_operator = Sopralluogo(1, 10, "28/04/2026", operatori="")
        self.assertFalse(validate_sopralluogo(missing_operator)[0])

        closed_without_result = Sopralluogo(1, 10, "28/04/2026", operatori="Agente A", stato="chiuso")
        self.assertFalse(validate_sopralluogo(closed_without_result)[0])

        valid = Sopralluogo(
            1,
            10,
            "28/04/2026",
            operatori="Agente A",
            stato=STATI_SOPRALLUOGO[-1],
            esito="Nessuna criticita",
        )
        self.assertTrue(validate_sopralluogo(valid)[0])


if __name__ == "__main__":
    unittest.main()
