import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class TestAppConfigPaths(unittest.TestCase):
    def test_frozen_runtime_paths_use_exe_dir_and_bundle_assets(self):
        import app_config

        original_executable = sys.executable
        original_meipass = getattr(sys, "_MEIPASS", None)
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            exe_dir = root / "dist" / "PassApp"
            bundle_dir = exe_dir / "_internal"
            exe_dir.mkdir(parents=True)
            bundle_dir.mkdir()

            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "executable", str(exe_dir / "PassApp.exe")):
                sys._MEIPASS = str(bundle_dir)  # type: ignore[attr-defined]
                reloaded = importlib.reload(app_config)

                self.assertEqual(reloaded.BASE_DIR.resolve(), exe_dir.resolve())
                self.assertEqual(reloaded.CONFIG_PATH.resolve(), (exe_dir / "data" / "config.json").resolve())
                self.assertEqual(
                    reloaded.resolve_path("data/segnalazioni.json").resolve(),
                    (exe_dir / "data" / "segnalazioni.json").resolve(),
                )
                self.assertEqual(
                    reloaded.resolve_path("documenti/report_mensili").resolve(),
                    (exe_dir / "documenti" / "report_mensili").resolve(),
                )
                self.assertEqual(
                    reloaded.resolve_path("assets/logo.jpg").resolve(),
                    (bundle_dir / "assets" / "logo.jpg").resolve(),
                )

        if original_meipass is None and hasattr(sys, "_MEIPASS"):
            delattr(sys, "_MEIPASS")
        elif original_meipass is not None:
            sys._MEIPASS = original_meipass  # type: ignore[attr-defined]
        sys.executable = original_executable
        importlib.reload(app_config)


if __name__ == "__main__":
    unittest.main()
