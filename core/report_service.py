from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_config import load_config, resolve_path
from core.dates import parse_date
from core.logging_utils import setup_module_logger

UNAVAILABLE = "dato non disponibile"
MONTH_NAMES = {
    1: "Gennaio",
    2: "Febbraio",
    3: "Marzo",
    4: "Aprile",
    5: "Maggio",
    6: "Giugno",
    7: "Luglio",
    8: "Agosto",
    9: "Settembre",
    10: "Ottobre",
    11: "Novembre",
    12: "Dicembre",
}
DEFAULT_MODULES = ("pass_invalidi", "segnalazioni", "ospitalita", "sopralluoghi")
PRIORITY_KEYS = ("priorita", "priorità", "priority", "urgenza")
CATEGORY_KEYS = ("categoria", "category")
HIGH_PRIORITY_VALUES = {"alta", "alta priorita", "alta priorità", "urgente", "high", "urgent"}
OSPITALITA_REQUIRED_FIELDS = (
    "protocollo",
    "data_presentazione",
    "denunciante_dichiarante",
    "cittadino_ospitato",
)

APP_CONFIG = load_config()
LOG_FILE = resolve_path(APP_CONFIG["paths"]["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)


@dataclass(frozen=True)
class ReportSection:
    title: str
    lines: tuple[tuple[str, str], ...]
    status: str = "OK"
    detail: str = ""


@dataclass(frozen=True)
class MonthlyReport:
    month: int
    year: int
    generated_at: dt.datetime
    sections: tuple[ReportSection, ...]
    text: str


@dataclass(frozen=True)
class ReportSources:
    pass_records: list[dict[str, Any]] | None = None
    pass_errors: list[str] | None = None
    segnalazioni: list[dict[str, Any]] | None = None
    sopralluoghi: list[dict[str, Any]] | None = None
    ospitalita_records: list[dict[str, Any]] | None = None
    ospitalita_errors: list[str] | None = None


def build_monthly_report(
    month: int,
    year: int,
    include_modules: tuple[str, ...] | list[str] | None = None,
    *,
    sources: ReportSources | None = None,
) -> MonthlyReport:
    month = int(month)
    year = int(year)
    if month < 1 or month > 12:
        raise ValueError("Mese non valido")
    modules = tuple(include_modules or DEFAULT_MODULES)
    source_data = sources or ReportSources()

    sections: list[ReportSection] = []
    if "pass_invalidi" in modules:
        sections.append(_safe_section("Pass Invalidi", lambda: _build_pass_section(month, year, source_data)))
    if "segnalazioni" in modules:
        sections.append(_safe_section("Segnalazioni", lambda: _build_segnalazioni_section(month, year, source_data)))
    if "sopralluoghi" in modules:
        sections.append(_safe_section("Sopralluoghi", lambda: _build_sopralluoghi_section(month, year, source_data)))
    if "ospitalita" in modules:
        sections.append(_safe_section("Ospitalita Stranieri", lambda: _build_ospitalita_section(month, year, source_data)))

    generated_at = dt.datetime.now()
    text = render_monthly_report_text(month, year, generated_at, tuple(sections))
    return MonthlyReport(month=month, year=year, generated_at=generated_at, sections=tuple(sections), text=text)


def render_monthly_report_text(
    month: int,
    year: int,
    generated_at: dt.datetime,
    sections: tuple[ReportSection, ...],
) -> str:
    lines = [
        "REPORT MENSILE ATTIVITA'",
        f"Periodo: {MONTH_NAMES[month]} {year}",
        f"Data generazione: {generated_at.strftime('%d/%m/%Y %H:%M:%S')}",
        "Ente/Comando: Polizia Locale",
        "",
    ]
    for section in sections:
        lines.append(section.title.upper())
        lines.append("-" * len(section.title))
        if section.status != "OK":
            lines.append(f"Stato sezione: {section.status}")
        for label, value in section.lines:
            lines.append(f"- {label}: {value}")
        if section.detail:
            lines.append(f"Note: {section.detail}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _safe_section(title: str, builder) -> ReportSection:
    try:
        return builder()
    except Exception as exc:
        logger.exception("Errore report mensile sezione %s", title)
        return ReportSection(
            title=title,
            status="Non disponibile",
            lines=(("Stato", "Non disponibile"),),
            detail=str(exc) or "Errore non specificato",
        )


def _build_pass_section(month: int, year: int, sources: ReportSources) -> ReportSection:
    records, errors = _load_pass_records(sources)
    status_counts = {"valid": 0, "soon": 0, "expired": 0}
    for record in records:
        status = _pass_status(record.get("scadenza"))
        if status in status_counts:
            status_counts[status] += 1

    detail = _first_error(errors)
    return ReportSection(
        title="Pass Invalidi",
        status="Parziale" if errors else "OK",
        lines=(
            ("Totale record", str(len(records))),
            ("Pass validi", str(status_counts["valid"])),
            ("Pass scaduti", str(status_counts["expired"])),
            ("Pass in scadenza", str(status_counts["soon"])),
            ("Nuovi inserimenti nel mese", UNAVAILABLE),
            ("Rinnovi nel mese", UNAVAILABLE),
        ),
        detail=detail,
    )


def _build_segnalazioni_section(month: int, year: int, sources: ReportSources) -> ReportSection:
    items = _load_segnalazioni(sources)
    month_items = [item for item in items if _raw_date_in_month(item, month, year)]
    open_count = sum(1 for item in month_items if _norm(item.get("stato")) == "in_corso")
    closed_count = sum(1 for item in month_items if _norm(item.get("stato")) == "archiviata")
    high_priority = _count_high_priority(month_items)
    categories, missing_category = _category_summary(month_items)

    return ReportSection(
        title="Segnalazioni",
        lines=(
            ("Totale segnalazioni ricevute nel mese", str(len(month_items))),
            ("Aperte", str(open_count)),
            ("Chiuse", str(closed_count)),
            ("In lavorazione", str(open_count)),
            ("Urgenti/alta priorita", _count_or_unavailable(high_priority, _has_any_key(month_items, PRIORITY_KEYS))),
            ("Suddivisione per categoria", categories or UNAVAILABLE),
            ("Segnalazioni senza categoria", _count_or_unavailable(missing_category, _has_any_key(month_items, CATEGORY_KEYS))),
            ("Tempi medi di chiusura", UNAVAILABLE),
        ),
        detail="" if items else "Nessuna segnalazione leggibile o file non presente.",
    )


def _build_sopralluoghi_section(month: int, year: int, sources: ReportSources) -> ReportSection:
    items = _load_sopralluoghi(sources)
    month_items = [item for item in items if _date_in_month(item.get("data_sopralluogo"), month, year)]
    by_operator = _operator_summary(month_items)

    return ReportSection(
        title="Sopralluoghi",
        lines=(
            ("Sopralluoghi programmati nel mese", str(sum(1 for item in month_items if _norm(item.get("stato")) == "programmato"))),
            ("Sopralluoghi effettuati", str(sum(1 for item in month_items if _norm(item.get("stato")) == "effettuato"))),
            ("Sopralluoghi da integrare", str(sum(1 for item in month_items if _norm(item.get("stato")) == "da integrare"))),
            ("Sopralluoghi chiusi", str(sum(1 for item in month_items if _norm(item.get("stato")) == "chiuso"))),
            ("Suddivisione per operatore", by_operator or UNAVAILABLE),
        ),
        detail="" if items else "Nessun sopralluogo leggibile o file non presente.",
    )


def _build_ospitalita_section(month: int, year: int, sources: ReportSources) -> ReportSection:
    records, errors = _load_ospitalita_records(sources)
    month_records = [record for record in records if _date_in_month(record.get("data_presentazione"), month, year)]
    incomplete = _count_incomplete_ospitalita(month_records)

    detail = _first_error(errors)
    if not records and not errors:
        detail = "Nessun dato ospitalita leggibile."
    return ReportSection(
        title="Ospitalita Stranieri",
        status="Parziale" if errors else "OK",
        lines=(
            ("Totale comunicazioni/record nel mese", str(len(month_records)) if records else UNAVAILABLE),
            ("Pratiche incomplete", str(incomplete) if records else UNAVAILABLE),
        ),
        detail=detail,
    )


def _load_pass_records(sources: ReportSources) -> tuple[list[dict[str, Any]], list[str]]:
    if sources.pass_records is not None:
        return sources.pass_records, sources.pass_errors or []
    from pass_invalidi import carica_tutti

    records, _files, errors = carica_tutti()
    return records, errors


def _load_segnalazioni(sources: ReportSources) -> list[dict[str, Any]]:
    if sources.segnalazioni is not None:
        return sources.segnalazioni
    from segnalazioni import SEGNALAZIONI_BACKUP_FILE, SEGNALAZIONI_FILE

    return _read_json_items(SEGNALAZIONI_FILE, SEGNALAZIONI_BACKUP_FILE, "segnalazioni")


def _load_sopralluoghi(sources: ReportSources) -> list[dict[str, Any]]:
    if sources.sopralluoghi is not None:
        return sources.sopralluoghi
    try:
        from core.sopralluoghi import load_sopralluoghi
    except ImportError:
        return []
    return [item.to_dict() for item in load_sopralluoghi()]


def _load_ospitalita_records(sources: ReportSources) -> tuple[list[dict[str, Any]], list[str]]:
    if sources.ospitalita_records is not None:
        return sources.ospitalita_records, sources.ospitalita_errors or []
    from ospitalita_stranieri import FOLDER_OSPITALITA, _extract_records, _list_input_files

    if not os.path.isdir(FOLDER_OSPITALITA):
        return [], ["Cartella origine non raggiungibile."]
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in _list_input_files():
        try:
            file_records, _insight = _extract_records(path)
            records.extend(file_records)
        except Exception as exc:
            logger.exception("Errore report mensile ospitalita: %s", path)
            errors.append(f"{os.path.basename(path)}: {exc}")
    return records, errors


def _read_json_items(primary: Path, backup: Path, key: str) -> list[dict[str, Any]]:
    for path in (primary, backup):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            logger.exception("Errore lettura report mensile: %s", path)
            continue
        items = payload.get(key, []) if isinstance(payload, dict) else payload
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _pass_status(value: Any) -> str | None:
    parsed = parse_date(value)
    if parsed is None:
        return None
    diff = (parsed - dt.date.today()).days
    if diff < 0:
        return "expired"
    if diff <= int(APP_CONFIG["pass_invalidi"]["warning_days"]):
        return "soon"
    return "valid"


def _raw_date_in_month(item: dict[str, Any], month: int, year: int) -> bool:
    parsed = parse_date(item.get("data") or item.get("data_ricezione"))
    if parsed is None:
        try:
            parsed = dt.date(int(item.get("anno", 0)), int(item.get("mese", 0)), int(item.get("giorno", 0)))
        except (TypeError, ValueError):
            return False
    return parsed.month == month and parsed.year == year


def _date_in_month(value: Any, month: int, year: int) -> bool:
    parsed = parse_date(value)
    return bool(parsed and parsed.month == month and parsed.year == year)


def _count_high_priority(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if _norm(_first_present(item, PRIORITY_KEYS)) in HIGH_PRIORITY_VALUES)


def _category_summary(items: list[dict[str, Any]]) -> tuple[str, int]:
    counts: dict[str, int] = {}
    missing = 0
    for item in items:
        category = _first_present(item, CATEGORY_KEYS)
        if _is_blank(category):
            missing += 1
            continue
        label = str(category).strip()
        counts[label] = counts.get(label, 0) + 1
    summary = ", ".join(f"{label}: {count}" for label, count in sorted(counts.items()))
    return summary, missing


def _operator_summary(items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        raw = str(item.get("operatori", "")).strip()
        if not raw:
            continue
        parts = [part.strip() for chunk in raw.split(";") for part in chunk.split(",")]
        for part in parts:
            if part:
                counts[part] = counts.get(part, 0) + 1
    return ", ".join(f"{label}: {count}" for label, count in sorted(counts.items()))


def _count_incomplete_ospitalita(records: list[dict[str, Any]]) -> int:
    return sum(1 for record in records if any(_is_blank(record.get(field)) for field in OSPITALITA_REQUIRED_FIELDS))


def _count_or_unavailable(value: int, available: bool) -> str:
    return str(value) if available else UNAVAILABLE


def _has_any_key(items: list[dict[str, Any]], keys: tuple[str, ...]) -> bool:
    return any(_first_present(item, keys) is not None for item in items)


def _first_present(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    lower_map = {str(key).lower(): value for key, value in item.items()}
    for key in keys:
        if key in lower_map:
            return lower_map[key]
    return None


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_blank(value: Any) -> bool:
    return _norm(value) in {"", "-", "none", "null"}


def _first_error(errors: list[str]) -> str:
    if not errors:
        return ""
    first = errors[0]
    if len(errors) == 1:
        return first
    return f"{first} (+{len(errors) - 1})"
