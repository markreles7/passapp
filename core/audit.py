from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from app_config import resolve_path
from core.logging_utils import setup_module_logger

AUDIT_LOG_FILE = resolve_path("data/audit_log.jsonl")
MAX_AUDIT_BYTES = 10 * 1024 * 1024
logger = setup_module_logger(__name__, resolve_path("data/passapp.log"))


def log_audit_event(
    module: str,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    description: str = "",
    result: str = "success",
    error: str | None = None,
    operator: str | None = None,
    extra: dict[str, Any] | None = None,
    audit_file: Path = AUDIT_LOG_FILE,
) -> bool:
    event = {
        "timestamp": dt.datetime.now().replace(microsecond=0).isoformat(),
        "module": _short(module),
        "action": _short(action),
        "entity_type": _short(entity_type),
        "entity_id": _short(entity_id),
        "description": _short(description, 240),
        "result": _short(result),
        "error": _short(error, 240) if error else None,
        "operator": _short(operator, 80) if operator else None,
        "extra": _sanitize_extra(extra),
    }
    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(audit_file)
        with audit_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        return True
    except Exception:
        logger.exception("Scrittura audit non riuscita")
        return False


def read_audit_events(
    audit_file: Path = AUDIT_LOG_FILE,
    *,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    if not audit_file.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        with audit_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    events.append(payload)
    except OSError:
        logger.exception("Lettura audit non riuscita")
        return []
    return events[-limit:]


def _rotate_if_needed(audit_file: Path) -> None:
    try:
        if audit_file.exists() and audit_file.stat().st_size > MAX_AUDIT_BYTES:
            rotated = audit_file.with_name("audit_log.1.jsonl")
            if rotated.exists():
                rotated.unlink()
            audit_file.replace(rotated)
    except OSError:
        logger.exception("Rotazione audit non riuscita")


def _sanitize_extra(extra: dict[str, Any] | None) -> dict[str, str] | None:
    if not extra:
        return None
    clean: dict[str, str] = {}
    for key, value in extra.items():
        if value is None:
            continue
        clean[_short(str(key), 60) or "campo"] = _short(str(value), 120) or ""
    return clean or None


def _short(value: str | None, limit: int = 120) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
