from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from services.ai.action_engine import ActionEngine
from services.ai.ai_service import AIService
from services.ai.exceptions import AIValidationError
from services.ai.chatgpt_client import ChatGPTClient, ChatGPTConfig
from services.ai.schemas import OperationalCommand
from services.ai.validators import validate_operational_response
from core.segnalazioni import Segnalazione


VALID_COMMAND = {
    "intent": "create_report_and_inspection",
    "confidence": 0.94,
    "requires_confirmation": True,
    "missing_fields": [],
    "clarification_question": None,
    "report": {
        "reporter_name": "Signora Rossi",
        "address": "Via Roma 11",
        "description": "Il segnalante riferisce la presenza di una buca.",
        "category": "dissesto_stradale",
        "priority": "ordinaria",
    },
    "inspection": {"address": "Via Roma 11", "reason": "Verifica", "status": "da_programmare"},
    "target_record": None,
    "proposed_actions": [
        {"action": "create_report", "module": "reports"},
        {"action": "create_inspection", "module": "inspections"},
        {"action": "link_records", "module": "cases"},
    ],
    "warnings": [],
}


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.value).encode("utf-8")


class TestStructuredCommands(unittest.TestCase):
    def test_valid_json_and_text_around_json(self):
        command = validate_operational_response("risposta\n" + json.dumps(VALID_COMMAND) + "\nfine")
        self.assertEqual(command.intent, "create_report_and_inspection")

    def test_invalid_json(self):
        with self.assertRaises(AIValidationError):
            validate_operational_response("non json")

    def test_unknown_intent_has_no_actions(self):
        raw = dict(VALID_COMMAND, intent="unknown", report=None, inspection=None, proposed_actions=[])
        self.assertEqual(OperationalCommand.from_dict(raw).intent, "unknown")

    def test_required_payload_missing(self):
        raw = dict(VALID_COMMAND, report=None)
        with self.assertRaises(AIValidationError):
            OperationalCommand.from_dict(raw)

    def test_single_repair_attempt(self):
        client = ChatGPTClient(ChatGPTConfig())
        valid = {"output_text": json.dumps(VALID_COMMAND)}
        invalid = {"output_text": "invalid"}
        with patch.object(client, "chat_sync", side_effect=[invalid, valid]) as call, patch(
            "services.ai.ai_service.log_ai_interaction"
        ):
            result = AIService(client).process_user_command("crea una segnalazione")
        self.assertTrue(result.repaired)
        self.assertEqual(call.call_count, 2)

    def test_no_action_runs_without_explicit_confirm_call(self):
        engine = ActionEngine()
        command = OperationalCommand.from_dict(VALID_COMMAND)
        with patch.object(engine, "_create_report") as create:
            engine.preview(command)
        create.assert_not_called()

    def test_multiple_and_no_matching_records(self):
        engine = ActionEngine()
        with patch("services.ai.action_engine.load_segnalazioni", return_value=([], None)):
            self.assertEqual(engine.search_reports({"address": "Via Roma"}), [])
        records = [
            Segnalazione(1, "2026", "01", "01", "10:00", indirizzo="Via Roma 11"),
            Segnalazione(2, "2026", "01", "02", "10:00", indirizzo="Via Roma 11"),
        ]
        with patch("services.ai.action_engine.load_segnalazioni", return_value=(records, None)):
            self.assertEqual(len(engine.search_reports({"address": "Via Roma 11"})), 2)

class TestActionEngine(unittest.TestCase):
    def _memory_store(self):
        store = {"reports": [], "inspections": []}

        def load_reports():
            return list(store["reports"]), None

        def save_reports(items):
            store["reports"] = list(items)

        def load_inspections():
            return list(store["inspections"])

        def save_inspections(items):
            store["inspections"] = list(items)

        return store, load_reports, save_reports, load_inspections, save_inspections

    def test_confirm_creates_report_and_inspection_transaction(self):
        store, lr, sr, li, si = self._memory_store()
        command = OperationalCommand.from_dict(VALID_COMMAND)
        with patch("services.ai.action_engine.load_segnalazioni", side_effect=lr), patch(
            "services.ai.action_engine.save_segnalazioni", side_effect=sr
        ), patch("services.ai.action_engine.load_sopralluoghi", side_effect=li), patch(
            "services.ai.action_engine.save_sopralluoghi", side_effect=si
        ), patch("services.ai.action_engine.log_audit_event"):
            results = ActionEngine().confirm(command, "Agente Test")
        self.assertEqual(len(store["reports"]), 1)
        self.assertEqual(len(store["inspections"]), 1)
        self.assertEqual(store["inspections"][0].segnalazione_id, store["reports"][0].numero_progressivo)
        self.assertTrue(all(result.success for result in results))

    def test_rollback_when_linked_action_fails(self):
        store, lr, sr, li, si = self._memory_store()
        command = OperationalCommand.from_dict(VALID_COMMAND)
        engine = ActionEngine()
        with patch("services.ai.action_engine.load_segnalazioni", side_effect=lr), patch(
            "services.ai.action_engine.save_segnalazioni", side_effect=sr
        ), patch("services.ai.action_engine.load_sopralluoghi", side_effect=li), patch(
            "services.ai.action_engine.save_sopralluoghi", side_effect=si
        ), patch.object(engine, "_link_records", side_effect=RuntimeError("errore")), patch(
            "services.ai.action_engine.log_audit_event"
        ):
            engine.registry["link_records"] = engine._link_records
            with self.assertRaises(RuntimeError):
                engine.confirm(command, "Agente Test")
        self.assertEqual(store["reports"], [])
        self.assertEqual(store["inspections"], [])

    def test_document_generation_stays_a_draft_requiring_user_input(self):
        raw = dict(
            VALID_COMMAND,
            intent="generate_inspection_document",
            report=None,
            inspection=None,
            document_request={"document_type": "inspection_report", "status": "draft", "include_photos": True},
            target_record={"case_number": 1},
            proposed_actions=[{"action": "generate_inspection_document", "module": "documents"}],
        )
        command = OperationalCommand.from_dict(raw)
        store, lr, sr, li, si = self._memory_store()
        store["reports"].append(Segnalazione(1, "2026", "01", "01", "10:00", indirizzo="Via Roma 11"))
        with patch("services.ai.action_engine.load_segnalazioni", side_effect=lr), patch(
            "services.ai.action_engine.save_segnalazioni", side_effect=sr
        ), patch("services.ai.action_engine.load_sopralluoghi", side_effect=li), patch(
            "services.ai.action_engine.save_sopralluoghi", side_effect=si
        ), patch("services.ai.action_engine.log_audit_event"):
            result = ActionEngine().confirm(command, "Agente Test")[0]
        self.assertTrue(result.requires_user_input)
        self.assertIn("bozza IA", result.message)


if __name__ == "__main__":
    unittest.main()
