import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.ai_documents import prepare_pass_invalidi_authorization
from core.pass_invalidi_authorizations import authorization_replacements, generate_authorization_doc_with_word
from core.segnalazioni import Segnalazione
from core.segnalazioni_pdf import build_pdf_payload, render_segnalazione_pdf
from core.sopralluoghi import Sopralluogo
from services.ai.exceptions import AIServiceError


PASS = dict(auth_number=999, year=2026, release_date="13/10/2026", expiry_date="31/05/2031",
            protocol_number="PROVA-1", protocol_date="02/10/2026", sigla="Sig.ra", cognome="ROSSI",
            nome="Maria", nato_word="nata", birth_place="Suzzara (MN)", birth_date="31/05/1980",
            residence_city="Pegognaga", residence_address="via Roma 123", issue_date="13/10/2026")
CONFIG = {"ai": {"documents_enabled": True}}
TEXT = "Testo completo del documento elaborato sulla base dei dati forniti, senza aggiungere circostanze mancanti."


def mock_response(client, text):
    client.return_value.chat_sync.return_value = {"output_text": text}
    client.return_value.response_text.side_effect = lambda response: response["output_text"]


def test_pass_invalidi_calls_chatgpt_and_accepts_only_register_consistent_fields():
    expected = authorization_replacements(PASS)
    with patch("core.ai_documents.ChatGPTClient") as client:
        mock_response(client, json.dumps(expected))
        assert prepare_pass_invalidi_authorization(PASS, CONFIG) == expected
    assert client.return_value.chat_sync.call_args.kwargs["structured"] is True
    assert json.loads(client.return_value.chat_sync.call_args.args[1].split("\n", 1)[1])["dati"]["protocol_number"] == "PROVA-1"


@pytest.mark.parametrize("change", ["wrong_date", "missing_field", "extra_field", "not_json"])
def test_pass_invalidi_rejects_ai_changes_without_creating_word(tmp_path, change):
    fields = authorization_replacements(PASS)
    if change == "wrong_date":
        fields["DATA_DOCUMENTO"] = "01/01/1900"
    elif change == "missing_field":
        fields.pop("DATA_DOCUMENTO")
    elif change == "extra_field":
        fields["ISTRUZIONI"] = "changed"
    raw = "testo senza JSON" if change == "not_json" else json.dumps(fields)
    template = tmp_path / "template.doc"
    template.write_bytes(b"original template")
    output = tmp_path / "authorization.doc"
    with patch("core.ai_documents.load_config", return_value=CONFIG), patch("core.ai_documents.ChatGPTClient") as client, \
         patch("core.pass_invalidi_authorizations.subprocess.run") as word:
        mock_response(client, raw)
        with pytest.raises(AIServiceError):
            generate_authorization_doc_with_word(template, output, PASS, use_chatgpt=True)
    word.assert_not_called()
    assert not output.exists() and template.read_bytes() == b"original template"


def test_disabling_document_ai_prevents_pass_request():
    with patch("core.ai_documents.ChatGPTClient") as client:
        assert prepare_pass_invalidi_authorization(PASS, {"ai": {"documents_enabled": False}}) == authorization_replacements(PASS)
    client.assert_not_called()


def fake_word(captured):
    def run(command, **_kwargs):
        captured.update(json.loads(Path(command[command.index("-PayloadPath") + 1]).read_text(encoding="utf-8")))
        Path(command[command.index("-PdfPath") + 1]).write_bytes(b"%PDF-1.4")
        return subprocess.CompletedProcess(command, 0, "", "")
    return run


def signal():
    return Segnalazione(numero_progressivo=999, anno="2026", mese="10", giorno="13", ora="09:00",
                        nominativo="Persona di prova", indirizzo="Luogo di prova", descrizione_segnalazione="Fatti riferiti di prova")


def test_segnalazione_pdf_contains_chatgpt_text_from_completed_fields(tmp_path):
    captured = {}
    payload = build_pdf_payload(signal())
    assert payload["data_accertamento"] == "-"
    with patch("core.ai_documents.load_config", return_value=CONFIG), patch("core.ai_documents.ChatGPTClient") as client, \
         patch("core.segnalazioni_pdf.subprocess.run", side_effect=fake_word(captured)):
        mock_response(client, TEXT)
        render_segnalazione_pdf(payload, tmp_path / "segnalazione.pdf")
    assert captured["testo_segnalazione_generato"] == TEXT and captured["testo_generato_da"] == "chatgpt"
    prompt = client.return_value.chat_sync.call_args.args[1]
    assert "Fatti riferiti di prova" in prompt and "Persona di prova" in prompt


def test_sopralluogo_pdf_contains_chatgpt_verbale_with_report_and_inspection_fields(tmp_path):
    from qt_app import sopralluoghi_pdf
    item = Sopralluogo(999, 999, "13/10/2026", "09:30", "Operatore di prova", "Luogo di prova",
                      "Esito accertato di prova", "Note di prova", stato="effettuato")
    captured = {}
    with patch("qt_app.sopralluoghi_pdf.load_config", return_value=CONFIG), patch("core.ai_documents.ChatGPTClient") as client, \
         patch("qt_app.sopralluoghi_pdf.list_attachments", return_value=[]), \
         patch("qt_app.sopralluoghi_pdf.VERBALE_SOPRALLUOGO_TEMPLATE", tmp_path / "missing.doc"), \
         patch("qt_app.sopralluoghi_pdf.subprocess.run", side_effect=fake_word(captured)):
        mock_response(client, TEXT)
        sopralluoghi_pdf.render_sopralluogo_pdf(signal(), item, tmp_path / "verbale.pdf")
    assert captured["verbale_generato"] == TEXT and captured["testo_generato_da"] == "chatgpt"
    prompt = client.return_value.chat_sync.call_args.args[1]
    assert all(value in prompt for value in ["Fatti riferiti di prova", "Esito accertato di prova", "Note di prova", "Operatore di prova"])


def test_automatic_pass_worker_requests_chatgpt_even_without_assistant_page():
    from qt_app.workers import PassAuthorizationWorker
    with patch("core.pass_invalidi_authorizations.authorization_payload_for_record", return_value=PASS), \
         patch("core.pass_invalidi_authorizations.generate_authorization_doc_with_word") as create, patch("core.audit.log_audit_event"):
        PassAuthorizationWorker(Path("template.doc"), Path("output"), [{"numero": 999}]).run()
    assert create.call_args.kwargs["use_chatgpt"] is True


def test_assistant_cannot_be_clicked_or_opened_programmatically():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from qt_app.sidebar import Sidebar
    from qt_app.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    sidebar = Sidebar()
    selected = []
    sidebar.selected.connect(selected.append)
    button = sidebar.buttons["assistente_operativo"]
    assert not button.isEnabled()
    button.click()
    assert selected == []
    window = SimpleNamespace(stack=Mock())
    MainWindow.show_page(window, "assistente_operativo")
    window.stack.setCurrentWidget.assert_not_called()
    assert app
