import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from core.fascicoli import (
    add_attachment,
    build_fascicolo_folder_name,
    ensure_fascicolo,
    generate_photo_sheet_html,
    list_attachments,
    safe_windows_name,
)


@dataclass
class SegnalazioneStub:
    numero_progressivo: int = 1
    anno: str = "2026"
    giorno: str = "28"
    mese: str = "04"
    indirizzo: str = "Via Roma 1"
    descrizione_segnalazione: str = "Buca strada"


class TestFascicoli(unittest.TestCase):
    def test_safe_windows_name_removes_invalid_chars(self):
        self.assertEqual(safe_windows_name('Via <Roma>: "buca"/strada?'), "via_roma_buca_strada")

    def test_ensure_fascicolo_creates_expected_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir) / "fascicoli"
            registry = Path(tmp_dir) / "fascicoli.json"

            folder = ensure_fascicolo(SegnalazioneStub(), registry, base_dir)

            self.assertTrue(folder.exists())
            for subdir in ("foto", "allegati", "sopralluoghi", "documenti", "export"):
                self.assertTrue((folder / subdir).is_dir())
            self.assertTrue(build_fascicolo_folder_name(SegnalazioneStub()).startswith("SEG-2026-0001"))

    def test_add_attachment_copies_once_and_records_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "fascicoli"
            registry = root / "fascicoli.json"
            source = root / "foto prova.jpg"
            source.write_bytes(b"image")
            segnalazione = SegnalazioneStub()

            first = add_attachment(segnalazione, source, "foto", registry_path=registry, base_dir=base_dir)
            second = add_attachment(segnalazione, source, "foto", registry_path=registry, base_dir=base_dir)

            attachments = list_attachments(segnalazione.numero_progressivo, registry_path=registry)
            self.assertEqual(first.id_allegato, second.id_allegato)
            self.assertEqual(len(attachments), 1)
            self.assertIn("/foto/", first.relative_path.replace("\\", "/"))

    def test_generate_photo_sheet_html(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            base_dir = root / "fascicoli"
            registry = root / "fascicoli.json"
            source = root / "foto.jpg"
            source.write_bytes(b"image")
            segnalazione = SegnalazioneStub()
            add_attachment(segnalazione, source, "foto", registry_path=registry, base_dir=base_dir)

            output = generate_photo_sheet_html(segnalazione, registry, base_dir)

            self.assertTrue(output.exists())
            self.assertIn("Scheda fotografica", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
