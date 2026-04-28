import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_config
import core.diagnostics as diagnostics
from core.diagnostics import ERROR, OK, WARNING


class TestDiagnostics(unittest.TestCase):
    def tearDown(self):
        app_config.load_config(force_reload=True)

    def test_config_validity_reports_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.json"
            config_path.write_text("{invalid json", encoding="utf-8")

            with (
                patch.object(app_config, "CONFIG_PATH", config_path),
                patch.object(diagnostics, "CONFIG_PATH", config_path),
            ):
                _config, item = diagnostics._check_config_validity()

            self.assertEqual(item.status, ERROR)
            self.assertIn("JSON", item.detail)

    def test_run_diagnostics_reports_expected_local_statuses(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.json"
            pass_dir = root / "invalidi"
            osp_dir = root / "ospitalita"
            pdf_dir = root / "pdf"
            pass_dir.mkdir()
            osp_dir.mkdir()
            (pass_dir / "REGISTRO INVALIDI COMUNE 2026.xlsx").write_text("x", encoding="utf-8")
            (osp_dir / "registro comunicazioni 2026.xls").write_text("x", encoding="utf-8")
            config = {
                "paths": {
                    "pass_invalidi_network_folder": str(pass_dir),
                    "pass_invalidi_pattern": "REGISTRO INVALIDI COMUNE*.xlsx",
                    "ospitalita_network_folder": str(osp_dir),
                    "ospitalita_patterns": ["registro comunicazioni *.xls"],
                    "segnalazioni_pdf_dir": str(pdf_dir),
                }
            }
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with (
                patch.object(app_config, "CONFIG_PATH", config_path),
                patch.object(diagnostics, "CONFIG_PATH", config_path),
                patch.object(diagnostics, "_check_import", side_effect=lambda name: diagnostics._item(OK, f"Libreria {name}", "mock")),
                patch.object(diagnostics, "_check_office_com", side_effect=lambda _app, label: diagnostics._item(WARNING, label, "mock")),
            ):
                items = diagnostics.run_diagnostics()

            by_name = {item.name: item for item in items}
            self.assertEqual(by_name["File configurazione"].status, OK)
            self.assertEqual(by_name["Validità configurazione"].status, OK)
            self.assertEqual(by_name["Cartella Pass Invalidi"].status, OK)
            self.assertEqual(by_name["File Pass Invalidi"].status, OK)
            self.assertEqual(by_name["Cartella Ospitalità"].status, OK)
            self.assertEqual(by_name["File Ospitalità"].status, OK)
            self.assertEqual(by_name["Cartella PDF segnalazioni"].status, OK)


if __name__ == "__main__":
    unittest.main()
