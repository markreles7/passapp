from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
import json
import os
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from app_config import load_config, resolve_path
from core.logging_utils import setup_module_logger

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]

MODALITA_OPZIONI = ("Personalmente", "Telefonicamente")
STATO_OPZIONI = ("in_corso", "archiviata")
CATEGORIA_OPZIONI = (
    "Viabilita",
    "Sosta",
    "Segnaletica",
    "Decoro urbano",
    "Rifiuti",
    "Illuminazione pubblica",
    "Verde pubblico",
    "Animali",
    "Rumore",
    "Occupazione suolo pubblico",
    "Sicurezza urbana",
    "Abusi/irregolarita",
    "Altro",
)
PRIORITA_OPZIONI = ("Bassa", "Media", "Alta", "Urgente")
STATO_LAVORAZIONE_OPZIONI = (
    "Aperta",
    "In valutazione",
    "Sopralluogo da programmare",
    "Sopralluogo programmato",
    "In attesa altro ufficio",
    "In lavorazione",
    "Chiusa",
    "Archiviata",
)
CATEGORIA_DEFAULT = "Altro"
PRIORITA_DEFAULT = "Media"
STATO_LAVORAZIONE_DEFAULT = "Aperta"
PRIORITA_RANK = {"Urgente": 0, "Alta": 1, "Media": 2, "Bassa": 3}

DATA_DIR = resolve_path("data")
SEGNALAZIONI_FILE = resolve_path(PATHS["segnalazioni_file"])
SEGNALAZIONI_BACKUP_FILE = Path(f"{SEGNALAZIONI_FILE}.bak")
SEGNALAZIONI_PDF_DIR = resolve_path(PATHS["segnalazioni_pdf_dir"])
logger = setup_module_logger(__name__, resolve_path(PATHS["log_file"]))


@dataclass
class Segnalazione:
    numero_progressivo: int
    anno: str
    mese: str
    giorno: str
    ora: str
    nominativo: str = ""
    residenza: str = ""
    indirizzo: str = ""
    telefono: str = ""
    modalita_segnalazione: str = "Personalmente"
    descrizione_segnalazione: str = ""
    ricevente: str = ""
    agente_verificatore: str = ""
    verifica_effettuata: str = ""
    data_verifica: str = ""
    categoria: str = CATEGORIA_DEFAULT
    priorita: str = PRIORITA_DEFAULT
    stato_lavorazione: str = STATO_LAVORAZIONE_DEFAULT
    stato: str = "in_corso"

    def searchable_text(self) -> str:
        parts = [
            str(self.numero_progressivo),
            self.anno,
            self.mese,
            self.giorno,
            self.ora,
            self.nominativo,
            self.residenza,
            self.indirizzo,
            self.telefono,
            self.modalita_segnalazione,
            self.descrizione_segnalazione,
            self.ricevente,
            self.agente_verificatore,
            self.verifica_effettuata,
            self.data_verifica,
            self.categoria,
            self.priorita,
            self.stato_lavorazione,
            self.stato,
        ]
        return " ".join(parts).lower()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Segnalazione | None:
        try:
            numero = int(raw.get("numero_progressivo", 0))
        except (TypeError, ValueError):
            return None
        if numero <= 0:
            return None

        modalita = str(raw.get("modalita_segnalazione", MODALITA_OPZIONI[0]))
        if modalita not in MODALITA_OPZIONI:
            modalita = MODALITA_OPZIONI[0]

        stato = str(raw.get("stato", "in_corso"))
        if stato not in STATO_OPZIONI:
            stato = "in_corso"
        categoria = normalize_categoria(str(raw.get("categoria", raw.get("category", ""))))
        priorita = normalize_priorita(str(raw.get("priorita", raw.get("priorità", raw.get("priority", "")))))
        stato_lavorazione = normalize_stato_lavorazione(
            str(raw.get("stato_lavorazione", raw.get("stato_lavoro", ""))),
            stato,
        )

        return cls(
            numero_progressivo=numero,
            anno=str(raw.get("anno", "")),
            mese=str(raw.get("mese", "")),
            giorno=str(raw.get("giorno", "")),
            ora=str(raw.get("ora", "")),
            nominativo=str(raw.get("nominativo", "")),
            residenza=str(raw.get("residenza", "")),
            indirizzo=str(raw.get("indirizzo", "")),
            telefono=str(raw.get("telefono", "")),
            modalita_segnalazione=modalita,
            descrizione_segnalazione=str(raw.get("descrizione_segnalazione", "")),
            ricevente=str(raw.get("ricevente", "")),
            agente_verificatore=str(raw.get("agente_verificatore", "")),
            verifica_effettuata=str(raw.get("verifica_effettuata", "")),
            data_verifica=str(raw.get("data_verifica", "")),
            categoria=categoria,
            priorita=priorita,
            stato_lavorazione=stato_lavorazione,
            stato=stato,
        )


def normalize_categoria(value: str) -> str:
    return _normalize_choice(value, CATEGORIA_OPZIONI, CATEGORIA_DEFAULT)


def normalize_priorita(value: str) -> str:
    aliases = {
        "alta priorita": "Alta",
        "alta": "Alta",
        "urgente": "Urgente",
        "urgent": "Urgente",
        "high": "Alta",
        "media": "Media",
        "medium": "Media",
        "bassa": "Bassa",
        "low": "Bassa",
    }
    marker = _norm_label(value)
    return aliases.get(marker) or _normalize_choice(value, PRIORITA_OPZIONI, PRIORITA_DEFAULT)


def normalize_stato_lavorazione(value: str, stato_record: str = "in_corso") -> str:
    marker = _norm_label(value)
    aliases = {
        "in_corso": "Aperta",
        "aperta": "Aperta",
        "aperto": "Aperta",
        "archiviata": "Archiviata",
        "archiviato": "Archiviata",
        "chiusa": "Chiusa",
        "chiuso": "Chiusa",
    }
    if marker in aliases:
        return aliases[marker]
    default = "Archiviata" if stato_record == "archiviata" else STATO_LAVORAZIONE_DEFAULT
    return _normalize_choice(value, STATO_LAVORAZIONE_OPZIONI, default)


def segnalazione_sort_key(seg: Segnalazione):
    try:
        date_key = dt.datetime(int(seg.anno), int(seg.mese), int(seg.giorno), 0, 0).timestamp()
    except (TypeError, ValueError):
        date_key = 0.0
    return (PRIORITA_RANK.get(seg.priorita, 99), -date_key, -int(seg.numero_progressivo))


def segnalazione_matches_filters(
    seg: Segnalazione,
    *,
    query: str = "",
    categoria: str = "Tutte",
    priorita: str = "Tutte",
    stato_lavorazione: str = "Tutti",
    solo_urgenti: bool = False,
    solo_aperte: bool = False,
) -> bool:
    if query and query not in seg.searchable_text():
        return False
    if categoria != "Tutte" and seg.categoria != categoria:
        return False
    if priorita != "Tutte" and seg.priorita != priorita:
        return False
    if stato_lavorazione != "Tutti" and seg.stato_lavorazione != stato_lavorazione:
        return False
    if solo_urgenti and seg.priorita != "Urgente":
        return False
    return not (solo_aperte and seg.stato_lavorazione in {"Chiusa", "Archiviata"})


def load_segnalazioni(
    path: Path = SEGNALAZIONI_FILE,
    backup_path: Path = SEGNALAZIONI_BACKUP_FILE,
) -> tuple[list[Segnalazione], Path | None]:
    for source in (path, backup_path):
        payload = read_segnalazioni_payload(source)
        if payload is None:
            continue
        raw_items = payload.get("segnalazioni", []) if isinstance(payload, dict) else payload
        if not isinstance(raw_items, list):
            continue
        records = [seg for item in raw_items if isinstance(item, dict) and (seg := Segnalazione.from_dict(item))]
        return records, source
    return [], None


def save_segnalazioni(
    segnalazioni: list[Segnalazione],
    path: Path = SEGNALAZIONI_FILE,
    backup_path: Path = SEGNALAZIONI_BACKUP_FILE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="segnalazioni_", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"segnalazioni": [item.to_dict() for item in segnalazioni]}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, backup_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def next_progressivo(segnalazioni: list[Segnalazione]) -> int:
    return max((item.numero_progressivo for item in segnalazioni), default=0) + 1


def read_segnalazioni_payload(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.exception("Errore lettura file segnalazioni: %s", path)
        return None
    return payload if isinstance(payload, (dict, list)) else None


def repair_mojibake(value: str) -> str:
    text = str(value or "").strip()
    if not text or not any(marker in text for marker in ("Ã", "Â", "â", "ð")):
        return text
    try:
        raw = bytearray()
        for ch in text:
            code = ord(ch)
            if code <= 255:
                raw.append(code)
            else:
                raw.extend(ch.encode("cp1252"))
        return bytes(raw).decode("utf-8").strip()
    except Exception:
        return text


def _norm_label(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _normalize_choice(value: str, options: tuple[str, ...], default: str) -> str:
    marker = _norm_label(value)
    if not marker:
        return default
    for option in options:
        if _norm_label(option) == marker:
            return option
    return default
