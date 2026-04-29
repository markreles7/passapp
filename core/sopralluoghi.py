from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app_config import resolve_path
from core.dates import parse_date
from core.logging_utils import setup_module_logger

SOPRALLUOGHI_FILE = resolve_path("data/sopralluoghi.json")
SOPRALLUOGHI_BACKUP_FILE = Path(f"{SOPRALLUOGHI_FILE}.bak")
SOPRALLUOGHI_MALFORMED_BACKUP_DIR = resolve_path("data/backups/sopralluoghi")
logger = setup_module_logger(__name__, resolve_path("data/passapp.log"))
STATI_SOPRALLUOGO = (
    "da programmare",
    "programmato",
    "effettuato",
    "da integrare",
    "chiuso",
)


@dataclass
class Sopralluogo:
    id_sopralluogo: int
    segnalazione_id: int
    data_sopralluogo: str
    ora_sopralluogo: str = ""
    operatori: str = ""
    luogo: str = ""
    esito: str = ""
    note_operative: str = ""
    presenza_foto_allegati: bool = False
    ulteriori_atti: bool = False
    ufficio_destinatario: str = ""
    stato: str = "da programmare"
    data_creazione: str = ""
    data_ultima_modifica: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Sopralluogo | None:
        try:
            id_sopralluogo = int(raw.get("id_sopralluogo", 0))
            segnalazione_id = int(raw.get("segnalazione_id", 0))
        except (TypeError, ValueError):
            return None
        if id_sopralluogo <= 0 or segnalazione_id <= 0:
            return None

        stato = str(raw.get("stato", "da programmare"))
        if stato not in STATI_SOPRALLUOGO:
            stato = "da programmare"

        return cls(
            id_sopralluogo=id_sopralluogo,
            segnalazione_id=segnalazione_id,
            data_sopralluogo=str(raw.get("data_sopralluogo", "")),
            ora_sopralluogo=str(raw.get("ora_sopralluogo", "")),
            operatori=str(raw.get("operatori", "")),
            luogo=str(raw.get("luogo", "")),
            esito=str(raw.get("esito", "")),
            note_operative=str(raw.get("note_operative", "")),
            presenza_foto_allegati=bool(raw.get("presenza_foto_allegati", False)),
            ulteriori_atti=bool(raw.get("ulteriori_atti", False)),
            ufficio_destinatario=str(raw.get("ufficio_destinatario", "")),
            stato=stato,
            data_creazione=str(raw.get("data_creazione", "")),
            data_ultima_modifica=str(raw.get("data_ultima_modifica", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_sopralluoghi(path: Path = SOPRALLUOGHI_FILE) -> list[Sopralluogo]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        backup = backup_malformed_sopralluoghi_file(path)
        logger.exception("File sopralluoghi JSON malformato. Backup creato: %s", backup)
        return []
    except OSError:
        logger.exception("File sopralluoghi non leggibile: %s", path)
        return []
    items = payload.get("sopralluoghi", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    out: list[Sopralluogo] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sopralluogo = Sopralluogo.from_dict(item)
        if sopralluogo is not None:
            out.append(sopralluogo)
    return sorted(out, key=lambda item: (item.segnalazione_id, item.id_sopralluogo))


def save_sopralluoghi(
    sopralluoghi: list[Sopralluogo],
    path: Path = SOPRALLUOGHI_FILE,
    backup_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_target = backup_path if backup_path is not None else Path(f"{path}.bak")
    tmp_name = ""
    fd, tmp_name = tempfile.mkstemp(prefix="sopralluoghi_", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"sopralluoghi": [item.to_dict() for item in sopralluoghi]}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            backup_target.write_bytes(path.read_bytes())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def list_for_segnalazione(segnalazione_id: int, path: Path = SOPRALLUOGHI_FILE) -> list[Sopralluogo]:
    return [item for item in load_sopralluoghi(path) if item.segnalazione_id == segnalazione_id]


def next_sopralluogo_id(sopralluoghi: list[Sopralluogo]) -> int:
    return max((item.id_sopralluogo for item in sopralluoghi), default=0) + 1


def upsert_sopralluogo(item: Sopralluogo, path: Path = SOPRALLUOGHI_FILE) -> None:
    records = load_sopralluoghi(path)
    found = False
    for idx, current in enumerate(records):
        if current.id_sopralluogo == item.id_sopralluogo:
            records[idx] = item
            found = True
            break
    if not found:
        records.append(item)
    save_sopralluoghi(records, path)


def delete_sopralluogo(id_sopralluogo: int, path: Path = SOPRALLUOGHI_FILE) -> None:
    records = [item for item in load_sopralluoghi(path) if item.id_sopralluogo != id_sopralluogo]
    save_sopralluoghi(records, path)


def validate_sopralluogo(item: Sopralluogo) -> tuple[bool, str]:
    if parse_date(item.data_sopralluogo) is None:
        return False, "La data sopralluogo non e valida."
    if item.stato not in STATI_SOPRALLUOGO:
        return False, "Lo stato sopralluogo non e valido."
    if not item.operatori.strip():
        return False, "Il campo Operatore/i e obbligatorio."
    if item.ora_sopralluogo.strip():
        try:
            dt.datetime.strptime(item.ora_sopralluogo.strip(), "%H:%M")
        except ValueError:
            return False, "L'ora sopralluogo non e valida. Usa HH:MM."
    if item.stato in {"effettuato", "chiuso"} and not (item.esito.strip() or item.note_operative.strip()):
        return False, "Per sopralluoghi effettuati o chiusi compila Esito o Note operative."
    return True, ""


def now_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def backup_malformed_sopralluoghi_file(path: Path) -> Path:
    backup_dir = _backup_dir_for(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}_malformed_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def _backup_dir_for(path: Path) -> Path:
    try:
        if path.resolve() == SOPRALLUOGHI_FILE.resolve():
            return SOPRALLUOGHI_MALFORMED_BACKUP_DIR
    except OSError:
        pass
    return path.parent / "backups" / "sopralluoghi"
