import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.logging_utils import setup_module_logger


class TestLoggingUtils(unittest.TestCase):
    def test_setup_module_logger_uses_rotating_file_handler(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "passapp.log"
            logger_name = f"test.passapp.{id(path)}"

            logger = setup_module_logger(logger_name, path, max_bytes=1234, backup_count=2)

            self.assertEqual(logger.level, logging.INFO)
            self.assertFalse(logger.propagate)
            self.assertEqual(len(logger.handlers), 1)
            handler = logger.handlers[0]
            self.assertIsInstance(handler, RotatingFileHandler)
            self.assertEqual(handler.maxBytes, 1234)
            self.assertEqual(handler.backupCount, 2)

            logger.info("test message")
            handler.flush()
            self.assertTrue(path.exists())

            logger.removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    unittest.main()
