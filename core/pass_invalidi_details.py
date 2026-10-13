"""Persist fields which are not columns in the municipal Excel register."""
from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

FIELDS = ("cognome", "nome_proprio", "nato_il", "sesso", "luogo_nascita", "comune_residenza",
          "protocol_number", "protocol_date", "issue_date")


def details_path_for_config(config: dict) -> Path:
    from app_config import resolve_path
    paths = config["paths"]
    configured = paths.get("pass_invalidi_details_file")
    return resolve_path(configured) if configured else Path(paths["pass_invalidi_network_folder"]) / "dati_autorizzazioni_pass.json"


def _key(record: dict) -> str:
    return f"{str(record['source']).strip().casefold()}::{int(record['numero'])}"


def load_details(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "records": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("records"), dict):
            raise ValueError("Struttura non valida")
        return data
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Archivio dati autorizzazioni non leggibile: {path}. {exc}") from exc


def enrich_records(records: list[dict], path: Path) -> None:
    details = load_details(path)["records"]
    for record in records:
        saved = details.get(_key(record), {})
        # Do not attach an old person's details to a reused register number.
        if str(saved.get("full_name", "")).strip().casefold() != str(record.get("nome", "")).strip().casefold():
            continue
        record.update({name: saved[name] for name in FIELDS if name in saved})


@contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 10
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Archivio autorizzazioni occupato da un altro operatore. Riprova.") from None
                    time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def save_details(changes: list[dict], path: Path) -> None:
    with _locked(path):
        data = load_details(path)
        for record in changes:
            key = _key(record)
            if record.get("mode") == "delete_existing":
                data["records"].pop(key, None)
                continue
            saved = {name: str(record[name]) for name in FIELDS if name in record}
            saved["full_name"] = str(record.get("nome", ""))
            data["records"][key] = saved
        fd, temporary = tempfile.mkstemp(prefix="pass_details_", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
