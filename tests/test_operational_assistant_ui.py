from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from qt_app.operational_assistant import OperationalAssistantPage
from services.ai.schemas import ActionResult, OperationalCommand

APP = QApplication.instance() or QApplication([])


def _command(warning: str = "") -> OperationalCommand:
    return OperationalCommand.from_dict(
        {
            "intent": "create_reminder",
            "confidence": 0.8,
            "requires_confirmation": True,
            "missing_fields": [],
            "clarification_question": None,
            "report": {"description": "Richiamare il segnalante"},
            "inspection": None,
            "target_record": None,
            "proposed_actions": [{"action": "create_reminder", "module": "reminders"}],
            "warnings": [warning] if warning else [],
        }
    )


def test_user_cancel_clears_preview_without_actions():
    page = OperationalAssistantPage({"ai": {}})
    page.analysis = SimpleNamespace(command=_command(), raw_response="{}")
    page.result_text.setPlainText("preview")
    page.confirm_button.setEnabled(True)
    page.cancel()
    assert page.analysis is None
    assert page.result_text.toPlainText() == ""
    assert not page.confirm_button.isEnabled()


def test_user_modification_is_revalidated_before_confirmation():
    page = OperationalAssistantPage({"ai": {"base_url": "http://127.0.0.1:1234", "model": "qwen3.5-4b"}})
    original = _command()
    modified = _command("testo modificato dall'operatore")
    page.analysis = SimpleNamespace(command=original, raw_response=json.dumps(original.to_dict()))
    page.input_text.setPlainText("crea un promemoria")
    page.result_text.setPlainText(json.dumps(modified.to_dict()))
    result = ActionResult("create_reminder", True, "Promemoria creato", "promemoria", "1")
    with patch.object(page.engine, "confirm", return_value=[result]) as confirm, patch.object(
        page, "_attach_requested_photos"
    ), patch("qt_app.operational_assistant.log_ai_interaction"), patch(
        "qt_app.operational_assistant.QMessageBox.information"
    ):
        page.confirm()
    confirmed_command = confirm.call_args.args[0]
    assert confirmed_command.warnings == ["testo modificato dall'operatore"]
