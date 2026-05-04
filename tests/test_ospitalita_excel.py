import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.ospitalita_excel import (
    build_pending_payload,
    compact_values,
    reserve_progressivo_slot,
    split_display_name_address,
    write_pending_with_excel_com,
)


class TestOspitalitaExcel(unittest.TestCase):
    def test_reserve_progressivo_reuses_empty_slot_then_appends(self):
        records = [
            {"progressivo": "1", "source": "OSPITALITA 2026.xlsx", "protocollo": ""},
            {"progressivo": "2", "source": "OSPITALITA 2026.xlsx", "protocollo": "123"},
        ]

        progressivo, target, original, mode = reserve_progressivo_slot(records, "OSPITALITA 2026.xlsx")

        self.assertEqual(progressivo, "1")
        self.assertIs(target, records[0])
        self.assertEqual(original, records[0])
        self.assertEqual(mode, "update_slot")

        records[0]["protocollo"] = "999"
        progressivo, target, original, mode = reserve_progressivo_slot(records, "OSPITALITA 2026.xlsx")
        self.assertEqual((progressivo, target, original, mode), ("3", None, None, "append"))

    def test_display_split_and_payload(self):
        self.assertEqual(split_display_name_address("Mario Rossi | Via Roma 1"), ("Mario Rossi", "Via Roma 1"))
        self.assertEqual(compact_values("Mario Rossi", "", "Via Roma 1"), "Mario Rossi | Via Roma 1")

        payload = build_pending_payload(
            [
                {
                    "mode": "append",
                    "progressivo": "7",
                    "protocollo": "123/2026",
                    "data": "28/04/2026",
                    "denunciante_nome": "Mario Rossi",
                    "denunciante_indirizzo": "Via Roma 1",
                    "straniero_nome": "Ana Verdi",
                    "straniero_indirizzo": "Via Milano 2",
                    "motivo": "OSPITA",
                    "indirizzo_ospitalita": "Via Ospitalita 3",
                }
            ]
        )

        self.assertEqual(payload[0]["progressivo"], "7")
        self.assertEqual(payload[0]["motivo"], "OSPITA")
        self.assertEqual(payload[0]["mode"], "append")

    def test_writer_builds_expected_payload_file(self):
        captured_payload = None

        def fake_run(command, **_kwargs):
            nonlocal captured_payload
            payload_path = Path(command[command.index("-PayloadPath") + 1])
            captured_payload = json.loads(payload_path.read_text(encoding="utf-8"))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        pending = [
            {
                "progressivo": "7",
                "protocollo": "123/2026",
                "data": "28/04/2026",
                "denunciante_nome": "Mario Rossi",
                "denunciante_indirizzo": "Via Roma 1",
                "straniero_nome": "Ana Verdi",
                "straniero_indirizzo": "Via Milano 2",
                "motivo": "OSPITA",
                "indirizzo_ospitalita": "Via Ospitalita 3",
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir, patch("core.ospitalita_excel.subprocess.run", side_effect=fake_run):
            write_pending_with_excel_com(Path(tmp_dir) / "registro.xls", pending)

        self.assertEqual(captured_payload, build_pending_payload(pending))


if __name__ == "__main__":
    unittest.main()
