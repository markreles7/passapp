import datetime
import tempfile
import unittest
from pathlib import Path

from core.backups import BackupError, create_excel_backup


class TestExcelBackups(unittest.TestCase):
    def test_create_excel_backup_uses_category_clean_name_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "REGISTRO INVALIDI COMUNE 2026.xlsx"
            source.write_bytes(b"excel-content")

            backup = create_excel_backup(
                source,
                "pass_invalidi",
                backup_root=root / "backups",
                timestamp=datetime.datetime(2026, 4, 28, 17, 45, 30),
            )

            self.assertEqual(backup.parent, root / "backups" / "pass_invalidi")
            self.assertEqual(backup.name, "REGISTRO_INVALIDI_COMUNE_2026_20260428_174530.xlsx")
            self.assertEqual(backup.read_bytes(), b"excel-content")

    def test_create_excel_backup_raises_clear_error_if_source_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing = root / "mancante.xlsx"

            with self.assertRaises(BackupError) as ctx:
                create_excel_backup(
                    missing,
                    "pass_invalidi",
                    backup_root=root / "backups",
                    timestamp=datetime.datetime(2026, 4, 28, 17, 45, 30),
                )

            self.assertIn("Backup del file originale non riuscito", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
