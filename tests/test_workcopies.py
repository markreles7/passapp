import os
import tempfile
import time
import unittest
from pathlib import Path

from core.workcopies import cleanup_old_workcopies, create_working_copy


class TestWorkcopyCleanup(unittest.TestCase):
    def test_cleanup_removes_only_old_matching_excel_files(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            old_match = root / "invalidi_old.xlsx"
            recent_match = root / "invalidi_recent.xlsx"
            old_foreign = root / "altro_old.xlsx"
            old_tmp = root / "invalidi_old.tmp"
            for path in (old_match, recent_match, old_foreign, old_tmp):
                path.write_text("x", encoding="utf-8")

            old_time = time.time() - (31 * 24 * 60 * 60)
            os.utime(old_match, (old_time, old_time))
            os.utime(old_foreign, (old_time, old_time))
            os.utime(old_tmp, (old_time, old_time))

            removed = cleanup_old_workcopies(root, prefixes=("invalidi_",), max_age_days=30)

            self.assertEqual(removed, 1)
            self.assertFalse(old_match.exists())
            self.assertTrue(recent_match.exists())
            self.assertTrue(old_foreign.exists())
            self.assertTrue(old_tmp.exists())

    def test_cleanup_missing_directory_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing"

            self.assertEqual(cleanup_old_workcopies(missing, prefixes=("invalidi_",)), 0)

    def test_create_working_copy_copies_file_and_captures_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "registro.xlsx"
            source.write_bytes(b"original")
            workcopies = root / "workcopies"

            result = create_working_copy(source, workcopies, prefix="invalidi_")

            self.assertTrue(result.path.exists())
            self.assertEqual(result.path.read_bytes(), b"original")
            self.assertEqual(result.path.parent, workcopies)
            self.assertTrue(result.path.name.startswith("invalidi_"))
            self.assertEqual(result.snapshot.path, str(source))
            self.assertEqual(result.snapshot.size, len(b"original"))
            self.assertEqual(result.removed_old_copies, 0)


if __name__ == "__main__":
    unittest.main()
