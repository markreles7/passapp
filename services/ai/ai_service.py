from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app_config import load_config
from services.ai.audit import log_ai_interaction
from services.ai.exceptions import AIValidationError
from services.ai.chatgpt_client import ChatGPTClient, ChatGPTConfig
from services.ai.prompts import PROMPT_VERSION, operational_system_prompt, repair_prompt
from services.ai.schemas import OperationalCommand
from services.ai.validators import validate_operational_response


@dataclass(frozen=True)
class AIAnalysis:
    command: OperationalCommand
    raw_response: str
    repaired: bool = False


class AIService:
    def __init__(self, client: ChatGPTClient):
        self.client = client

    @classmethod
    def from_app_config(cls, config: dict[str, Any] | None = None) -> "AIService":
        app_config = config or load_config(force_reload=True)
        return cls(ChatGPTClient(ChatGPTConfig.from_mapping(app_config.get("ai"))))

    async def process_user_command_async(self, text: str, context: dict[str, Any] | None = None) -> AIAnalysis:
        import asyncio

        return await asyncio.to_thread(self.process_user_command, text, context)

    def process_user_command(self, text: str, context: dict[str, Any] | None = None) -> AIAnalysis:
        user_text = str(text or "").strip()
        if not user_text:
            raise AIValidationError("Inserisci un comando da analizzare.")
        input_text = user_text
        if context:
            input_text += "\n\nContesto PassApp (sola lettura):\n" + str(context)
        try:
            response = self.client.chat_sync(operational_system_prompt(), input_text, structured=True)
            raw = self.client.response_text(response)
        except Exception as exc:
            log_ai_interaction(
                original_text=user_text,
                raw_response="",
                validated_response=None,
                model=self.client.config.model,
                endpoint=f"{self.client.config.base_url}/v1/responses",
                prompt_version=PROMPT_VERSION,
                error=str(exc),
            )
            raise
        try:
            command = validate_operational_response(raw)
            repaired = False
        except AIValidationError as first_error:
            repair_response = self.client.chat_sync(
                operational_system_prompt(), repair_prompt(raw, str(first_error)), structured=True
            )
            raw_repair = self.client.response_text(repair_response)
            command = validate_operational_response(raw_repair)
            raw = raw_repair
            repaired = True
        analysis = AIAnalysis(command, raw, repaired)
        log_ai_interaction(
            original_text=user_text,
            raw_response=raw,
            validated_response=command.to_dict(),
            model=self.client.config.model,
            endpoint=f"{self.client.config.base_url}/v1/responses",
            prompt_version=PROMPT_VERSION,
            proposed_actions=[item.__dict__ for item in command.proposed_actions],
        )
        return analysis
