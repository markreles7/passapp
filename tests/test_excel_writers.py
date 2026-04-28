import datetime
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import openpyxl

import pass_invalidi
from core.file_state import capture_file_snapshot
from ospitalita_stranieri import OspitalitaStranieriFrame
from pass_invalidi import PassInvalidiFrame


def _date_value(value):
    return value.date() if hasattr(value, "date") else value


class TestExcelWriters(unittest.TestCase):
    def test_pass_invalidi_save_uses_xlsx_writer_for_xlsx_workcopy(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = root / "originale.xlsx"
            workcopy = root / "copia.xlsx"
            original.write_bytes(b"original")
            workcopy.write_bytes(b"workcopy")

            frame = PassInvalidiFrame.__new__(PassInvalidiFrame)
            frame._pending_new_records = [{"numero": 1}]
            frame._working_copy_file = workcopy
            frame._primary_source_file = original
            frame._source_file_snapshot = capture_file_snapshot(original)
            frame._write_pending_to_xlsx = MagicMock()
            frame._write_pending_with_excel_com = MagicMock()
            frame.btn_save_changes = SimpleNamespace(config=lambda **_kwargs: None)
            frame.all_records = []
            frame.applica_filtro = MagicMock()

            with (
                patch("pass_invalidi.create_excel_backup") as backup_mock,
                patch.object(pass_invalidi.messagebox, "showinfo"),
            ):
                result = frame.salva_modifiche(trigger_reload=False)

            self.assertTrue(result)
            frame._write_pending_to_xlsx.assert_called_once_with(workcopy)
            frame._write_pending_with_excel_com.assert_not_called()
            backup_mock.assert_called_once_with(original, "pass_invalidi")
            self.assertEqual(original.read_bytes(), b"workcopy")

    def test_pass_invalidi_xlsx_writer_updates_slot_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            workbook_path = Path(tmp_dir) / "registro_invalidi.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["N", "GENERALITA", "RILASCIO", "SCADENZA", "NOTE"])
            ws.append([1, "", None, None, None])
            ws.append([2, "ESISTENTE", "01/01/2025", "01/01/2026", "nota"])
            wb.save(workbook_path)
            wb.close()

            frame = PassInvalidiFrame.__new__(PassInvalidiFrame)
            frame._pending_new_records = [
                {
                    "numero": 1,
                    "cognome": "ROSSI",
                    "nome_proprio": "Mario",
                    "indirizzo": "Via Roma 1",
                    "rilascio": "10/03/2026",
                    "scadenza": "10/03/2031",
                    "note": "slot riusato",
                },
                {
                    "numero": 3,
                    "cognome": "BIANCHI",
                    "nome_proprio": "Luisa",
                    "indirizzo": "Via Milano 2",
                    "rilascio": "11/03/2026",
                    "scadenza": "11/03/2031",
                    "note": "nuova riga",
                },
            ]

            frame._write_pending_to_xlsx(workbook_path)

            saved = openpyxl.load_workbook(workbook_path, data_only=True)
            ws_saved = saved.active
            self.assertEqual(ws_saved.cell(row=2, column=1).value, 1)
            self.assertEqual(ws_saved.cell(row=2, column=2).value, "ROSSI MARIO - VIA ROMA 1")
            self.assertEqual(_date_value(ws_saved.cell(row=2, column=3).value), datetime.date(2026, 3, 10))
            self.assertEqual(_date_value(ws_saved.cell(row=2, column=4).value), datetime.date(2031, 3, 10))
            self.assertEqual(ws_saved.cell(row=2, column=5).value, "slot riusato")
            self.assertEqual(ws_saved.cell(row=4, column=1).value, 3)
            self.assertEqual(ws_saved.cell(row=4, column=2).value, "BIANCHI LUISA - VIA MILANO 2")
            saved.close()

    def test_ospitalita_excel_com_writer_builds_expected_payload(self):
        captured_payload = None

        def fake_run(command, **_kwargs):
            nonlocal captured_payload
            payload_path = Path(command[command.index("-PayloadPath") + 1])
            captured_payload = json.loads(payload_path.read_text(encoding="utf-8"))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        frame = OspitalitaStranieriFrame.__new__(OspitalitaStranieriFrame)
        frame._pending_new_records = [
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

        with patch("ospitalita_stranieri.subprocess.run", side_effect=fake_run):
            frame._append_pending_with_excel_com(Path("registro_ospitalita.xls"))

        self.assertEqual(
            captured_payload,
            [
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
            ],
        )


if __name__ == "__main__":
    unittest.main()
