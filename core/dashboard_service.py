from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_config import load_config, resolve_path
from core.logging_utils import setup_module_logger

OK = "OK"
WARNING = "ATTENZIONE"
ERROR = "ERRORE"
UNAVAILABLE = "Non disponibile"

APP_CONFIG = load_config()
LOG_FILE = resolve_path(APP_CONFIG["paths"]["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)

PRIORITY_KEYS = ("priorita", "priorità", "priority", "urgenza")
CATEGORY_KEYS = ("categoria", "category")
HIGH_PRIORITY_VALUES = {
    "alta",
    "alta priorita",
    "alta priorità",
    "urgente",
    "high",
    "urgent",
}
OSPITALITA_REQUIRED_FIELDS = (
    "protocollo",
    "data_presentazione",
    "denunciante_dichiarante",
    "cittadino_ospitato",
)


@dataclass(frozen=True)
class DashboardCard:
    key: str
    title: str
    status: str
    metrics: tuple[tuple[str, str], ...]
    detail: str = ""


@dataclass(frozen=True)
class DashboardSnapshot:
    updated_at: dt.datetime
    cards: dict[str, DashboardCard]


def collect_dashboard_snapshot() -> DashboardSnapshot:
    cards = {
        "pass_invalidi": _safe_collect("pass_invalidi", _collect_pass_invalidi),
        "segnalazioni": _safe_collect("segnalazioni", _collect_segnalazioni),
        "ospitalita": _safe_collect("ospitalita", _collect_ospitalita),
    }
    return DashboardSnapshot(updated_at=dt.datetime.now(), cards=cards)


def _safe_collect(key: str, collector) -> DashboardCard:
    try:
        return collector()
    except Exception as exc:
        logger.exception("Errore dashboard %s", key)
        title = _title_for_key(key)
        return DashboardCard(
            key=key,
            title=title,
            status=ERROR,
            metrics=(("Stato", "Errore lettura"),),
            detail=str(exc) or "Errore non specificato",
        )


def _title_for_key(key: str) -> str:
    return {
        "pass_invalidi": "Pass Invalidi",
        "segnalazioni": "Segnalazioni",
        "ospitalita": "Ospitalita Stranieri",
    }.get(key, key)


def _collect_pass_invalidi() -> DashboardCard:
    from pass_invalidi import carica_tutti, get_status

    records, files, errors = carica_tutti()
    status_counts = {"valid": 0, "soon": 0, "expired": 0}
    for record in records:
        status = get_status(record.get("scadenza"))
        if status in status_counts:
            status_counts[status] += 1

    status = OK
    detail = _latest_file_label(files)
    if errors:
        status = WARNING
        detail = f"{detail} - Errori lettura: {len(errors)}"
    if not files:
        status = WARNING
        detail = UNAVAILABLE

    return DashboardCard(
        key="pass_invalidi",
        title="Pass Invalidi",
        status=status,
        metrics=(
            ("Record caricabili", str(len(records))),
            ("Pass validi", str(status_counts["valid"])),
            ("In scadenza", str(status_counts["soon"])),
            ("Scaduti", str(status_counts["expired"])),
            ("Ultimo file", detail),
        ),
        detail=_first_error(errors),
    )


def _collect_segnalazioni() -> DashboardCard:
    from segnalazioni import SEGNALAZIONI_BACKUP_FILE, SEGNALAZIONI_FILE, SegnalazioniFrame

    frame = SegnalazioniFrame.__new__(SegnalazioniFrame)
    frame.segnalazioni = []
    frame._next_progressivo = 1
    frame._load_from_disk()

    raw_items, raw_source = _load_raw_segnalazioni(SEGNALAZIONI_FILE, SEGNALAZIONI_BACKUP_FILE)
    priority_summary = summarize_priority_fields(raw_items)

    total = len(frame.segnalazioni)
    open_count = sum(1 for item in frame.segnalazioni if item.stato == "in_corso")
    closed_count = sum(1 for item in frame.segnalazioni if item.stato == "archiviata")
    status = OK if raw_source else WARNING
    detail = raw_source.name if raw_source else UNAVAILABLE

    return DashboardCard(
        key="segnalazioni",
        title="Segnalazioni",
        status=status,
        metrics=(
            ("Totale segnalazioni", str(total)),
            ("Aperte", str(open_count)),
            ("Chiuse", str(closed_count)),
            ("Urgenti/alta priorita", priority_summary["high_priority"]),
            ("Senza categoria/priorita", priority_summary["missing"]),
            ("File dati", detail),
        ),
        detail="" if raw_source else "File segnalazioni non trovato o non leggibile.",
    )


def _collect_ospitalita() -> DashboardCard:
    from ospitalita_stranieri import FOLDER_OSPITALITA, _extract_records, _list_input_files

    if not os.path.isdir(FOLDER_OSPITALITA):
        return DashboardCard(
            key="ospitalita",
            title="Ospitalita Stranieri",
            status=WARNING,
            metrics=(
                ("Record caricabili", "0"),
                ("Pratiche incomplete", UNAVAILABLE),
                ("Ultimo file", UNAVAILABLE),
            ),
            detail="Cartella origine non raggiungibile.",
        )

    files = _list_input_files()
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in files:
        try:
            file_records, _insight = _extract_records(path)
            records.extend(file_records)
        except Exception as exc:
            logger.exception("Errore dashboard ospitalita: %s", path)
            errors.append(f"{os.path.basename(path)}: {exc}")

    incomplete = count_incomplete_ospitalita(records)
    detail = _latest_file_label(files)
    status = OK
    if errors:
        status = WARNING
        detail = f"{detail} - Errori lettura: {len(errors)}"
    if not files:
        status = WARNING
        detail = UNAVAILABLE

    return DashboardCard(
        key="ospitalita",
        title="Ospitalita Stranieri",
        status=status,
        metrics=(
            ("Record caricabili", str(len(records))),
            ("Pratiche incomplete", str(incomplete) if records else UNAVAILABLE),
            ("Ultimo file", detail),
        ),
        detail=_first_error(errors),
    )


def summarize_priority_fields(items: list[dict[str, Any]]) -> dict[str, str]:
    has_priority = any(_first_present(item, PRIORITY_KEYS) is not None for item in items)
    has_category = any(_first_present(item, CATEGORY_KEYS) is not None for item in items)
    if not has_priority and not has_category:
        return {"high_priority": UNAVAILABLE, "missing": UNAVAILABLE}

    high_priority = 0
    missing = 0
    for item in items:
        priority = _first_present(item, PRIORITY_KEYS)
        category = _first_present(item, CATEGORY_KEYS)
        if _normalize_label(priority) in HIGH_PRIORITY_VALUES:
            high_priority += 1
        if _is_blank(priority) or _is_blank(category):
            missing += 1

    return {"high_priority": str(high_priority), "missing": str(missing)}


def count_incomplete_ospitalita(records: list[dict[str, Any]]) -> int:
    return sum(
        1
        for record in records
        if any(_is_blank(record.get(field)) for field in OSPITALITA_REQUIRED_FIELDS)
    )


def _load_raw_segnalazioni(primary: Path, backup: Path) -> tuple[list[dict[str, Any]], Path | None]:
    for path in (primary, backup):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            logger.exception("Errore lettura dashboard segnalazioni: %s", path)
            continue
        items = payload.get("segnalazioni", []) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)], path
    return [], None


def _latest_file_label(files: list[str]) -> str:
    if not files:
        return UNAVAILABLE
    return os.path.basename(files[0])


def _first_error(errors: list[str]) -> str:
    if not errors:
        return ""
    first = errors[0]
    if len(errors) == 1:
        return first
    return f"{first} (+{len(errors) - 1})"


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_map = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        if key in lower_map:
            return lower_map[key]
    return None


def _normalize_label(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_blank(value: Any) -> bool:
    return _normalize_label(value) in {"", "-", "none", "null"}
