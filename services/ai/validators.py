from __future__ import annotations

import json
from typing import Any

from services.ai.exceptions import AIValidationError
from services.ai.schemas import OperationalCommand


def extract_json_object(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        clean = "\n".join(lines[1:-1]).strip() if len(lines) > 2 else clean
    decoder = json.JSONDecoder()
    for index, char in enumerate(clean):
        if char != "{":
            continue
        try:
            value, _end = decoder.raw_decode(clean[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise AIValidationError("La risposta non contiene un oggetto JSON valido.")


def validate_operational_response(text: str) -> OperationalCommand:
    return OperationalCommand.from_dict(extract_json_object(text))
