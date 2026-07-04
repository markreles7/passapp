import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.segnalazioni_pdf import ai_source_label, render_segnalazione_pdf


PDF_PAYLOAD = {
    "numero": "1",
    "stato": "In corso",
    "riferimento": "1/2026",
    "data_ora_ricezione": "15/05/2026 - 09:30",
    "nominativo": "Mario Rossi",
    "residenza": "Via Roma 1",
    "indirizzo": "Via Roma 2",
    "telefono": "333",
    "modalita": "Telefonicamente",
    "categoria": "Verde pubblico",
    "priorita": "Media",
    "stato_lavorazione": "In valutazione",
    "ricevente": "Operatore Uno",
    "descrizione": "Testo grezzo originale",
    "agente": "Agente Due",
    "data_accertamento": "15/05/2026",
    "verifica": "Riscontro grezzo registrato in app",
}


class TestSegnalazionePdfExportOptions(unittest.TestCase):
    def _render_and_capture(self, *, include_raw_fields: bool | None = None, source: str = "locale"):
        captured: dict[str, object] = {}

        def fake_run(command, **_kwargs):
            payload_path = Path(command[command.index("-PayloadPath") + 1])
            script_path = Path(command[command.index("-File") + 1])
            output_path = Path(command[command.index("-PdfPath") + 1])
            captured["payload"] = json.loads(payload_path.read_text(encoding="utf-8"))
            captured["script"] = script_path.read_text(encoding="utf-8")
            output_path.write_bytes(b"%PDF-1.4")
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmp_dir, patch(
            "core.segnalazioni_pdf.prepare_segnalazione_pdf",
            return_value=("Relazione descrittiva riformulata.", source),
        ), patch("core.segnalazioni_pdf.subprocess.run", side_effect=fake_run):
            output_pdf = Path(tmp_dir) / "segnalazione.pdf"
            if include_raw_fields is None:
                render_segnalazione_pdf(PDF_PAYLOAD, output_pdf)
            else:
                render_segnalazione_pdf(PDF_PAYLOAD, output_pdf, include_raw_fields=include_raw_fields)

        return captured

    def test_pdf_export_defaults_to_formal_document_without_raw_fields(self):
        captured = self._render_and_capture()

        self.assertFalse(captured["payload"]["include_raw_fields"])
        script = str(captured["script"])
        self.assertIn("$includeRawFields = $false", script)
        self.assertIn("if ($includeRawFields)", script)
        self.assertLess(script.index("if ($includeRawFields)"), script.index("CONTENUTO ORIGINALE REGISTRATO"))
        self.assertLess(script.index("if ($includeRawFields)"), script.index("Riscontro registrato in app"))

    def test_pdf_export_can_include_raw_fields_for_internal_document(self):
        captured = self._render_and_capture(include_raw_fields=True)

        self.assertTrue(captured["payload"]["include_raw_fields"])
        script = str(captured["script"])
        self.assertIn("ALLEGATO INTERNO - DATI ORIGINALI REGISTRATI", script)
        self.assertIn("ATTIVITA' DI ACCERTAMENTO", script)

    def test_pdf_export_includes_ai_source_label_for_openrouter(self):
        captured = self._render_and_capture(source="openrouter")

        self.assertEqual(captured["payload"]["testo_generato_da"], "openrouter")
        self.assertEqual(
            captured["payload"]["testo_generato_label"],
            "Testo descrittivo generato con AI tramite OpenRouter.",
        )
        self.assertIn("$testoGeneratoLabel = [string]$payload.testo_generato_label", str(captured["script"]))

    def test_ai_source_label_reports_local_fallback(self):
        self.assertEqual(
            ai_source_label("locale"),
            "Testo descrittivo generato localmente da PassApp (fallback senza AI esterna).",
        )


if __name__ == "__main__":
    unittest.main()
