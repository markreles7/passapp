import tempfile
import unittest
from pathlib import Path

from core.contatti import (
    Contatto,
    available_tags,
    build_seed_contacts,
    delete_contatto,
    filter_contatti,
    is_valid_email,
    load_contatti,
    save_contatti,
    upsert_contatto,
    validate_contatto,
)


class TestContatti(unittest.TestCase):
    def test_load_missing_file_imports_seed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "contatti.json"
            contatti, warning = load_contatti(path)
            file_created = path.exists()

        self.assertEqual(len(contatti), 30)
        self.assertEqual(warning, "Importati 30 contatti iniziali.")
        self.assertTrue(file_created)

    def test_save_and_load_contatti(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "contatti.json"
            save_contatti([Contatto(id="ufficio-tecnico", nome="Ufficio Tecnico", telefono="0376 123")], path)

            contatti, warning = load_contatti(path)

        self.assertIsNone(warning)
        self.assertEqual(len(contatti), 1)
        self.assertEqual(contatti[0].nome, "Ufficio Tecnico")

    def test_malformed_json_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "contatti.json"
            path.write_text("{invalid json", encoding="utf-8")

            contatti, warning = load_contatti(path)
            backups = list((Path(tmp_dir) / "backups" / "contatti").glob("contatti_malformed_*.json"))

        self.assertEqual(contatti, [])
        self.assertIsNotNone(warning)
        self.assertEqual(len(backups), 1)

    def test_upsert_and_delete_contact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "contatti.json"
            save_contatti([Contatto(id="base", nome="Base", telefono="0376 000")], path)
            saved = upsert_contatto(Contatto(id="", nome="Comune", email="info@example.it"), path)
            saved.telefono = "0376-123456"
            upsert_contatto(saved, path)

            contatti, _warning = load_contatti(path)
            self.assertEqual(len(contatti), 2)
            self.assertIn("0376 123456", [item.telefono for item in contatti])

            self.assertTrue(delete_contatto(saved.id, path))
            contatti, _warning = load_contatti(path)
            self.assertEqual(len(contatti), 1)

    def test_email_validation(self):
        self.assertTrue(is_valid_email("info@example.it"))
        self.assertFalse(is_valid_email("not-an-email"))

        invalid = Contatto(id="1", nome="Comune", email="not-an-email")
        valid, warning, soft_warning = validate_contatto(invalid)
        self.assertTrue(valid)
        self.assertTrue(soft_warning)
        self.assertIn("formato", warning)

        soft = Contatto(id="1", nome="Comune")
        valid, _warning, soft_warning = validate_contatto(soft)
        self.assertTrue(valid)
        self.assertTrue(soft_warning)

    def test_seed_has_unique_ids(self):
        seed = build_seed_contacts()
        ids = [item.id for item in seed]

        self.assertEqual(len(seed), 30)
        self.assertEqual(len(ids), len(set(ids)))

    def test_filter_by_tag_and_category(self):
        contacts = [
            Contatto(id="a", nome="Comune", categoria="Comune", tags=["protocollo"]),
            Contatto(id="b", nome="Ambiente", categoria="Ambiente e rifiuti", tags=["rifiuti"]),
        ]

        filtered = filter_contatti(contacts, categoria="Comune", tag="protocollo")

        self.assertEqual([item.id for item in filtered], ["a"])
        self.assertEqual(available_tags(contacts), ("protocollo", "rifiuti"))


if __name__ == "__main__":
    unittest.main()
