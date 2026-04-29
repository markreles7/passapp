import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.audit import log_audit_event, read_audit_events


class TestAudit(unittest.TestCase):
    def test_log_audit_event_creates_jsonl_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_file = Path(tmp_dir) / "audit_log.jsonl"

            result = log_audit_event(
                "segnalazioni",
                "create",
                "segnalazione",
                "SEG-2026-0001",
                "Creata nuova segnalazione",
                audit_file=audit_file,
            )

            self.assertTrue(result)
            payload = json.loads(audit_file.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["module"], "segnalazioni")
            self.assertEqual(payload["action"], "create")
            self.assertEqual(payload["result"], "success")

    def test_read_audit_events_handles_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            events = read_audit_events(Path(tmp_dir) / "missing.jsonl")

        self.assertEqual(events, [])

    def test_audit_write_error_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audit_file = Path(tmp_dir) / "audit_log.jsonl"
            with patch("pathlib.Path.open", side_effect=OSError("denied")):
                result = log_audit_event("sistema", "test", audit_file=audit_file)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
