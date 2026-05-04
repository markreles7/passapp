import datetime
import tempfile
import unittest
from pathlib import Path

from core.pass_invalidi_authorizations import (
    authorization_year_for_record,
    build_authorization_output_path,
    build_authorization_payload,
    find_authorization_doc_for_record,
    resolve_authorization_template,
)


class TestPassInvalidiAuthorizations(unittest.TestCase):
    def test_find_authorization_doc_matches_name_number_and_year(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "ROSSI Mario Autoriz. disabili n. 12 2026.doc"
            target.write_text("placeholder", encoding="utf-8")
            (root / "Autoriz. disabili n. 12 2025.doc").write_text("old", encoding="utf-8")

            record = {
                "numero": 12,
                "nome": "ROSSI MARIO",
                "source": "REGISTRO INVALIDI COMUNE 2026.xlsx",
            }

            self.assertEqual(find_authorization_doc_for_record(record, root), target)

    def test_template_resolution_prefers_configured_template(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            template = root / "Tesserino Disabili Guida.doc"
            template.write_text("template", encoding="utf-8")

            self.assertEqual(resolve_authorization_template(template, root), template)

    def test_payload_and_output_path_are_built_from_record(self):
        record = {"numero": "7", "source": "registro 2026.xlsx"}
        payload = build_authorization_payload(
            record,
            protocol_number="123",
            protocol_date=datetime.date(2026, 3, 10),
            sesso="F",
            cognome="rossi",
            nome="maria",
            luogo_nascita="Mantova",
            data_nascita=datetime.date(1980, 2, 1),
            comune_residenza="Pegognaga",
            indirizzo_residenza="Via Roma 1",
            data_scadenza=datetime.date(2031, 2, 1),
            comune_emissione="Pegognaga",
        )

        self.assertEqual(payload["auth_number"], 7)
        self.assertEqual(payload["sigla"], "Sig.ra")
        self.assertEqual(payload["nato_word"], "nata")
        self.assertEqual(authorization_year_for_record(record), 2026)

        output = build_authorization_output_path(
            "docs",
            "template.doc",
            cognome=str(payload["cognome"]),
            nome=str(payload["nome"]),
            numero=int(payload["auth_number"]),
            year=int(payload["year"]),
        )
        self.assertEqual(output.name, "ROSSI Maria Autoriz. disabili n. 7 2026.doc")


if __name__ == "__main__":
    unittest.main()
