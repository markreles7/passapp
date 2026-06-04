import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.auth import (
    ADMIN_INITIAL_PASSWORD,
    ADMIN_USERNAME,
    AuthError,
    authenticate,
    create_user,
)


class TestAuth(unittest.TestCase):
    def test_default_admin_is_created_and_password_is_hashed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "users.json"

            with patch("core.auth._current_machine_hash", return_value="machine-a"):
                user = authenticate(ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, store_path=store_path)

            self.assertTrue(user.is_admin)
            self.assertNotIn(ADMIN_INITIAL_PASSWORD, store_path.read_text(encoding="utf-8"))

    def test_admin_can_create_user_profile(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "users.json"

            with patch("core.auth._current_machine_hash", return_value="machine-a"):
                admin = authenticate(ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, store_path=store_path)
                create_user("operatore1", "Password.123", created_by=admin, store_path=store_path)
                user = authenticate("operatore1", "Password.123", store_path=store_path)

            self.assertFalse(user.is_admin)
            self.assertEqual(user.username, "operatore1")

    def test_non_admin_cannot_create_user_profile(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "users.json"

            with patch("core.auth._current_machine_hash", return_value="machine-a"):
                admin = authenticate(ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, store_path=store_path)
                create_user("operatore1", "Password.123", created_by=admin, store_path=store_path)
                operator = authenticate("operatore1", "Password.123", store_path=store_path)

                with self.assertRaises(AuthError):
                    create_user("operatore2", "Password.456", created_by=operator, store_path=store_path)

    def test_admin_is_blocked_on_different_machine(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            store_path = Path(tmp_dir) / "users.json"

            with patch("core.auth._current_machine_hash", return_value="machine-a"):
                authenticate(ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, store_path=store_path)

            with patch("core.auth._current_machine_hash", return_value="machine-b"):
                with self.assertRaises(AuthError):
                    authenticate(ADMIN_USERNAME, ADMIN_INITIAL_PASSWORD, store_path=store_path)


if __name__ == "__main__":
    unittest.main()
