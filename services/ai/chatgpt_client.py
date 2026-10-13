from __future__ import annotations

import asyncio
import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.ai.chatgpt_auth import ChatGPTAuth, RESOURCE, request_json
from services.ai.exceptions import AIServiceError


@dataclass(frozen=True)
class ChatGPTConfig:
    model: str = ""
    timeout: float = 120
    base_url: str = "https://api.openai.com"

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None):
        value = value or {}
        return cls(model=str(value.get("model") or "").strip(),
                   timeout=max(1, min(float(value.get("timeout", 120)), 600)))


@dataclass(frozen=True)
class AIHealthStatus:
    available: bool
    server_url: str
    configured_model: str
    model_available: bool
    message: str
    models: tuple = ()


class ChatGPTClient:
    def __init__(self, config: ChatGPTConfig, auth=None):
        self.config = config
        self.auth = auth or ChatGPTAuth()

    def list_models(self):
        payload = request_json(RESOURCE + "/models", token=self.auth.access_token(), timeout=self.config.timeout)
        models = payload.get("models")
        if not isinstance(models, list):
            raise AIServiceError("Catalogo modelli ChatGPT non valido.")
        return tuple((m["slug"], str(m.get("display_name") or m["slug"])) for m in models
                     if isinstance(m, dict) and m.get("visibility") == "list" and isinstance(m.get("slug"), str))

    def health_check_sync(self):
        try:
            models = self.list_models()
            selected = self.config.model or (models[0][0] if models else "")
            available = bool(selected) and selected in {m[0] for m in models}
            message = "ChatGPT collegato. Piano autorizzato." if available else "Scegli un modello disponibile per questo account."
            return AIHealthStatus(True, RESOURCE, selected, available, message, models)
        except AIServiceError as exc:
            return AIHealthStatus(False, RESOURCE, self.config.model, False, str(exc))

    async def health_check(self):
        return await asyncio.to_thread(self.health_check_sync)

    async def chat(self, system_prompt, user_input, *, structured=False):
        return await asyncio.to_thread(self.chat_sync, system_prompt, user_input, structured=structured)

    def chat_sync(self, system_prompt, user_input, *, structured=False):
        models = self.list_models()
        selected = self.config.model or (models[0][0] if models else "")
        if not selected or selected not in {m[0] for m in models}:
            raise AIServiceError("Modello ChatGPT non disponibile. Aggiorna i modelli in Configurazione.")
        payload = {"model": selected, "instructions": system_prompt,
                   "input": [{"role": "user", "content": user_input}],
                   "store": False, "stream": True}
        if structured:
            payload["text"] = {"format": {"type": "json_object"}}
        request = Request(RESOURCE + "/responses", data=json.dumps(payload).encode(),
                          headers={"Authorization": "Bearer " + self.auth.access_token(),
                                   "Content-Type": "application/json", "Accept": "text/event-stream"})
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                return _consume_stream(response)
        except HTTPError as exc:
            messages = {401: "Accesso ChatGPT scaduto: ricollega l'account.",
                        403: "Uso del piano ChatGPT non autorizzato per questa app.",
                        429: "Limite ChatGPT raggiunto. Controlla Gestisci utilizzo."}
            raise AIServiceError(messages.get(exc.code, f"ChatGPT ha risposto con errore HTTP {exc.code}.")) from None
        except (TimeoutError, socket.timeout):
            raise AIServiceError("Timeout della richiesta ChatGPT. Riprova.") from None
        except (OSError, URLError):
            raise AIServiceError("ChatGPT non raggiungibile. Controlla la connessione Internet.") from None

    @staticmethod
    def response_text(payload):
        text = payload.get("output_text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        raise AIServiceError("ChatGPT non ha restituito un testo utilizzabile.")


def _consume_stream(response):
    chunks = []
    data = []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif not line and data:
            try:
                event = json.loads("\n".join(data))
            except ValueError:
                raise AIServiceError("Stream ChatGPT non valido.") from None
            data = []
            kind = event.get("type")
            if kind == "response.output_text.delta":
                chunks.append(event.get("delta", ""))
            elif kind in {"response.failed", "response.incomplete", "error"}:
                raise AIServiceError("ChatGPT non ha completato la richiesta. Controlla il piano e riprova; la bozza non e stata accettata.")
            elif kind == "response.completed":
                completed = event.get("response", {})
                if completed.get("status") not in (None, "completed"):
                    raise AIServiceError("Risposta ChatGPT incompleta.")
                return {"output_text": "".join(chunks), "model": completed.get("model", "")}
    raise AIServiceError("Connessione ChatGPT interrotta prima del completamento. Riprova.")
