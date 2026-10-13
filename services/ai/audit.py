from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from app_config import resolve_path

AI_AUDIT_FILE = resolve_path("data/ai_audit.jsonl")


def log_ai_interaction(
    *,
    original_text: str,
    raw_response: str,
    validated_response: dict[str, Any] | None,
    model: str,
    endpoint: str,
    prompt_version: str,
    proposed_actions: list[dict[str, Any]] | None = None,
    modified_actions: list[dict[str, Any]] | None = None,
    confirmed_actions: list[dict[str, Any]] | None = None,
    records: list[str] | None = None,
    documents: list[str] | None = None,
    error: str | None = None,
    operator: str | None = None,
    path: Path = AI_AUDIT_FILE,
) -> None:
    event = {
        "timestamp": dt.datetime.now().replace(microsecond=0).isoformat(),
        "operator": operator,
        "model": model,
        "endpoint": endpoint,
        "prompt_version": prompt_version,
        "original_text": original_text,
        "raw_response": raw_response,
        "validated_response": validated_response,
        "proposed_actions": proposed_actions or [],
        "modified_actions": modified_actions or [],
        "confirmed_actions": confirmed_actions or [],
        "records": records or [],
        "documents": documents or [],
        "error": error,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_ai_interactions(path: Path = AI_AUDIT_FILE, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
    except OSError:
        return []
    return events[-limit:]
