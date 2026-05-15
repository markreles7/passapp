from __future__ import annotations

import datetime
import glob
import os
import re

import openpyxl

from app_config import load_config, resolve_path
from core.dates import parse_date
from core.logging_utils import setup_module_logger

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]

CARTELLA_RETE = PATHS["pass_invalidi_network_folder"]
PATTERN_FILE = PATHS["pass_invalidi_pattern"]
GIORNI_SCADENZA = int(APP_CONFIG["pass_invalidi"]["warning_days"])
WORK_COPY_DIR = resolve_path("data/workcopies/pass_invalidi")
AUTH_DOCS_DIR = PATHS.get("pass_invalidi_docs_folder") or os.path.join(CARTELLA_RETE, "Tesserini rilasciati")
AUTH_TEMPLATE_PATH = PATHS.get("pass_invalidi_authorization_template") or os.path.join(
    CARTELLA_RETE,
    "Modello autorizzazione.doc",
)
AUTH_CITY_DEFAULT = PATHS.get("pass_invalidi_authorization_city", "PEGOGNAGA")
logger = setup_module_logger(__name__, resolve_path(PATHS["log_file"]))


def get_status(val):
    d = parse_date(val)
    if d is None:
        return None
    today = datetime.date.today()
    diff = (d - today).days
    if diff < 0:
        return "expired"
    if diff <= GIORNI_SCADENZA:
        return "soon"
    return "valid"


def carica_file(path):
    records = []
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        logger.exception("Errore lettura file pass invalidi: %s", path)
        return records, str(exc)

    source_name = os.path.basename(path)
    for row in rows:
        if not row or row[0] is None:
            continue
        try:
            num = int(float(str(row[0]).strip()))
        except (ValueError, TypeError):
            continue

        generalita = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if not generalita or generalita.lower() in ("generalita", "generalita'", "nan", "none"):
            continue

        nome, indirizzo = generalita, ""
        rilascio = row[2] if len(row) > 2 else None
        scadenza = row[3] if len(row) > 3 else None
        note_start = 4
        maybe_indirizzo = row[2] if len(row) > 2 else None
        has_indirizzo_col = (
            isinstance(maybe_indirizzo, str)
            and maybe_indirizzo.strip() != ""
            and parse_date(maybe_indirizzo) is None
        )

        if has_indirizzo_col:
            indirizzo = str(maybe_indirizzo).strip()
            rilascio = row[3] if len(row) > 3 else None
            scadenza = row[4] if len(row) > 4 else None
            note_start = 6 if len(row) > 6 else 5
        elif " - " in generalita:
            parts = generalita.split(" - ", 1)
            nome, indirizzo = parts[0].strip(), parts[1].strip()
        else:
            match = re.search(
                r"\b(VIA|STR\.|STRADA|PIAZZA|P\.ZA|CORSO|VIALE|FRAZ\.|FRAZIONE|VICOLO|BORGO|CONTRADA|LOC\.)\b",
                generalita,
                re.IGNORECASE,
            )
            if match:
                idx = match.start()
                nome = generalita[:idx].strip(" -")
                indirizzo = generalita[idx:].strip()

        note_raw = " | ".join(
            str(cell).strip()
            for cell in (row[note_start:] if len(row) > note_start else [])
            if cell and str(cell).strip() not in ("None", "nan", "")
        )

        name_tokens = [token for token in re.split(r"\s+", nome.strip()) if token]
        cognome = name_tokens[0].upper() if name_tokens else nome.upper()
        nome_proprio = " ".join(name_tokens[1:]).strip() if len(name_tokens) > 1 else ""

        records.append(
            {
                "numero": num,
                "nome": nome.upper(),
                "cognome": cognome,
                "nome_proprio": nome_proprio,
                "nato_il": "",
                "indirizzo": indirizzo,
                "rilascio": rilascio,
                "scadenza": scadenza,
                "note": note_raw,
                "source": source_name,
            }
        )

    return records, None


def carica_tutti():
    pattern = os.path.join(CARTELLA_RETE, PATTERN_FILE)
    files = sorted(glob.glob(pattern), key=_file_sort_key, reverse=True)
    all_records = []
    errors = []
    for path in files:
        records, error = carica_file(path)
        if error:
            errors.append(f"{os.path.basename(path)}: {error}")
        else:
            all_records.extend(records)
    return all_records, files, errors


def _extract_year_from_name(name: str) -> int:
    years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", name)]
    return max(years) if years else -1


def _file_sort_key(path: str):
    base = os.path.basename(path)
    year = _extract_year_from_name(base)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = 0.0
    return (year, mtime, base.lower())
