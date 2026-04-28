import os
import tempfile
import unittest
from pathlib import Path

from core.file_state import capture_file_snapshot, file_matches_snapshot


class TestFileState(unittest.TestCase):
    def test_file_matches_snapshot_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "registro.xlsx"
            path.write_bytes(b"original")

            snapshot = capture_file_snapshot(path)

            self.assertTrue(file_matches_snapshot(snapshot))

    def test_file_does_not_match_snapshot_when_size_changes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "registro.xlsx"
            path.write_bytes(b"original")
            snapshot = capture_file_snapshot(path)

            path.write_bytes(b"original changed")

            self.assertFalse(file_matches_snapshot(snapshot))

    def test_file_does_not_match_snapshot_when_modified_time_changes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "registro.xlsx"
            path.write_bytes(b"original")
            snapshot = capture_file_snapshot(path)

            os.utime(path, ns=(snapshot.modified_ns + 1_000_000_000, snapshot.modified_ns + 1_000_000_000))

            self.assertFalse(file_matches_snapshot(snapshot))

    def test_missing_snapshot_is_not_considered_safe(self):
        self.assertFalse(file_matches_snapshot(None))


if __name__ == "__main__":
    unittest.main()
