from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app_config import BASE_DIR, load_config, resolve_path
from core.logging_utils import setup_module_logger

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]

FASCICOLI_BASE_DIR = resolve_path(PATHS.get("fascicoli_segnalazioni_dir", "documenti/fascicoli_segnalazioni"))
FASCICOLI_FILE = resolve_path("data/fascicoli.json")
FASCICOLI_MALFORMED_BACKUP_DIR = resolve_path("data/backups/fascicoli")
FASCICOLO_SUBDIRS = ("foto", "allegati", "sopralluoghi", "documenti", "export")
INVALID_WINDOWS_CHARS = r'<>:"/\\|?*'
PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
logger = setup_module_logger(__name__, resolve_path("data/passapp.log"))


@dataclass
class FascicoloRecord:
    segnalazione_id: int
    relative_path: str
    data_creazione: str


@dataclass
class FascicoloAttachment:
    id_allegato: int
    segnalazione_id: int
    relative_path: str
    nome_file: str
    tipo: str
    origine: str
    data_aggiunta: str
    sopralluogo_id: int | None = None
    descrizione: str = ""


def safe_windows_name(value: str, max_length: int = 90) -> str:
    text = str(value or "").strip().lower()
    text = "".join("_" if ch in INVALID_WINDOWS_CHARS else ch for ch in text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[^a-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip(" ._")
    if not text:
        text = "pratica"
    return text[:max_length].rstrip(" ._") or "pratica"


def build_fascicolo_folder_name(segnalazione, max_length: int = 120) -> str:
    seg_id = _segnalazione_id(segnalazione)
    year = safe_windows_name(str(getattr(segnalazione, "anno", ""))) or str(dt.date.today().year)
    context = " ".join(
        part
        for part in (
            str(getattr(segnalazione, "indirizzo", "")),
            str(getattr(segnalazione, "descrizione_segnalazione", ""))[:45],
        )
        if part.strip()
    )
    suffix = safe_windows_name(context, max_length=70)
    prefix = f"SEG-{year}-{seg_id:04d}"
    return f"{prefix}_{suffix}"[:max_length].rstrip(" ._")


def ensure_fascicolo(segnalazione, registry_path: Path = FASCICOLI_FILE, base_dir: Path = FASCICOLI_BASE_DIR) -> Path:
    registry = load_registry(registry_path)
    seg_id = _segnalazione_id(segnalazione)
    record = _find_fascicolo(registry, seg_id)
    if record is None:
        folder = _unique_folder(base_dir / build_fascicolo_folder_name(segnalazione))
        record = {
            "segnalazione_id": seg_id,
            "relative_path": path_to_relative(folder),
            "data_creazione": now_timestamp(),
        }
        registry["fascicoli"].append(record)
        save_registry(registry, registry_path)
    folder = relative_to_path(record["relative_path"])
    create_fascicolo_subdirs(folder)
    return folder


def get_fascicolo_path(segnalazione_id: int, registry_path: Path = FASCICOLI_FILE) -> Path | None:
    registry = load_registry(registry_path)
    record = _find_fascicolo(registry, int(segnalazione_id))
    if record is None:
        return None
    return relative_to_path(record["relative_path"])


def fascicolo_exists(segnalazione_id: int, registry_path: Path = FASCICOLI_FILE) -> bool:
    path = get_fascicolo_path(segnalazione_id, registry_path)
    return bool(path and path.exists())


def add_attachment(
    segnalazione,
    source_path: Path,
    tipo: str,
    *,
    origine: str = "segnalazione",
    sopralluogo_id: int | None = None,
    descrizione: str = "",
    registry_path: Path = FASCICOLI_FILE,
    base_dir: Path = FASCICOLI_BASE_DIR,
) -> FascicoloAttachment:
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    folder = ensure_fascicolo(segnalazione, registry_path, base_dir)
    destination_dir = folder / _subdir_for_tipo(tipo)
    destination_dir.mkdir(parents=True, exist_ok=True)

    destination = _available_destination(destination_dir, safe_windows_name(source.stem, 70) + source.suffix.lower(), source)
    if destination != source.resolve():
        if not destination.exists():
            shutil.copy2(source, destination)

    registry = load_registry(registry_path)
    relative_path = path_to_relative(destination)
    existing = _find_attachment_by_path(registry, _segnalazione_id(segnalazione), relative_path)
    if existing is not None:
        return _attachment_from_dict(existing)

    item = FascicoloAttachment(
        id_allegato=_next_attachment_id(registry),
        segnalazione_id=_segnalazione_id(segnalazione),
        relative_path=relative_path,
        nome_file=destination.name,
        tipo=tipo,
        origine=origine,
        data_aggiunta=now_timestamp(),
        sopralluogo_id=sopralluogo_id,
        descrizione=descrizione,
    )
    registry["allegati"].append(asdict(item))
    save_registry(registry, registry_path)
    return item


def list_attachments(
    segnalazione_id: int,
    *,
    sopralluogo_id: int | None = None,
    registry_path: Path = FASCICOLI_FILE,
) -> list[FascicoloAttachment]:
    registry = load_registry(registry_path)
    out: list[FascicoloAttachment] = []
    for raw in registry["allegati"]:
        if int(raw.get("segnalazione_id", 0)) != int(segnalazione_id):
            continue
        if sopralluogo_id is not None and raw.get("sopralluogo_id") != sopralluogo_id:
            continue
        out.append(_attachment_from_dict(raw))
    return sorted(out, key=lambda item: (item.data_aggiunta, item.id_allegato))


def delete_attachment(
    segnalazione_id: int,
    id_allegato: int,
    *,
    remove_file: bool = True,
    registry_path: Path = FASCICOLI_FILE,
) -> FascicoloAttachment:
    registry = load_registry(registry_path)
    target_idx = None
    target_raw: dict[str, Any] | None = None
    for idx, raw in enumerate(registry["allegati"]):
        if int(raw.get("segnalazione_id", 0)) == int(segnalazione_id) and int(raw.get("id_allegato", 0)) == int(id_allegato):
            target_idx = idx
            target_raw = raw
            break
    if target_idx is None or target_raw is None:
        raise FileNotFoundError(f"Allegato {id_allegato} non trovato")

    attachment = _attachment_from_dict(target_raw)
    file_path = relative_to_path(attachment.relative_path)
    if remove_file and file_path.exists():
        _ensure_safe_attachment_delete(registry, int(segnalazione_id), file_path)
        file_path.unlink()

    del registry["allegati"][target_idx]
    save_registry(registry, registry_path)
    return attachment


def generate_photo_sheet_html(
    segnalazione,
    registry_path: Path = FASCICOLI_FILE,
    base_dir: Path = FASCICOLI_BASE_DIR,
) -> Path:
    folder = ensure_fascicolo(segnalazione, registry_path, base_dir)
    export_dir = folder / "export"
    export_dir.mkdir(parents=True, exist_ok=True)
    photos = [item for item in list_attachments(_segnalazione_id(segnalazione), registry_path=registry_path) if item.tipo == "foto"]
    if not photos:
        raise RuntimeError("Non sono presenti foto nel fascicolo.")

    output = export_dir / "scheda_fotografica.html"
    title = f"Scheda fotografica segnalazione n. {_segnalazione_id(segnalazione)}"
    rows = []
    for photo in photos:
        photo_path = relative_to_path(photo.relative_path)
        src = html.escape(os.path.relpath(photo_path, export_dir).replace("\\", "/"))
        rows.append(
            "<figure>"
            f'<img src="{src}" alt="{html.escape(photo.nome_file)}">'
            f"<figcaption>{html.escape(photo.nome_file)}<br>{html.escape(photo.descrizione or photo.origine)}</figcaption>"
            "</figure>"
        )
    body = f"""<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ font-size: 22px; margin-bottom: 4px; }}
    .meta {{ margin-bottom: 18px; color: #555; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; }}
    figure {{ margin: 0; border: 1px solid #ddd; padding: 10px; break-inside: avoid; }}
    img {{ width: 100%; max-height: 220px; object-fit: contain; background: #f5f5f5; }}
    figcaption {{ font-size: 12px; margin-top: 8px; color: #444; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">
    Luogo: {html.escape(str(getattr(segnalazione, "indirizzo", "")) or "-")}<br>
    Data: {html.escape(_segnalazione_date(segnalazione))}<br>
    Foto: {len(photos)}
  </div>
  <section class="grid">
    {''.join(rows)}
  </section>
</body>
</html>
"""
    output.write_text(body, encoding="utf-8")
    return output


def open_path(path: Path) -> None:
    target = Path(path)
    if os.name == "nt":
        os.startfile(target)  # type: ignore[attr-defined]
        return
    if os.name == "posix":
        subprocess.Popen(["xdg-open", str(target)])
        return
    raise RuntimeError("Apertura file non supportata su questo sistema.")


def load_registry(path: Path = FASCICOLI_FILE) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {"fascicoli": [], "allegati": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        backup = backup_malformed_registry_file(path)
        logger.exception("Registro fascicoli JSON malformato. Backup creato: %s", backup)
        return {"fascicoli": [], "allegati": []}
    except OSError:
        logger.exception("Registro fascicoli non leggibile: %s", path)
        return {"fascicoli": [], "allegati": []}
    if not isinstance(payload, dict):
        return {"fascicoli": [], "allegati": []}
    fascicoli = payload.get("fascicoli", [])
    allegati = payload.get("allegati", [])
    return {
        "fascicoli": fascicoli if isinstance(fascicoli, list) else [],
        "allegati": allegati if isinstance(allegati, list) else [],
    }


def save_registry(registry: dict[str, list[dict[str, Any]]], path: Path = FASCICOLI_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="fascicoli_", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(registry, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            Path(f"{path}.bak").write_bytes(path.read_bytes())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def create_fascicolo_subdirs(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in FASCICOLO_SUBDIRS:
        (folder / name).mkdir(parents=True, exist_ok=True)


def path_to_relative(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return resolved.as_posix()


def relative_to_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def now_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def backup_malformed_registry_file(path: Path) -> Path:
    backup_dir = _backup_dir_for(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}_malformed_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def _backup_dir_for(path: Path) -> Path:
    try:
        if path.resolve() == FASCICOLI_FILE.resolve():
            return FASCICOLI_MALFORMED_BACKUP_DIR
    except OSError:
        pass
    return path.parent / "backups" / "fascicoli"


def _subdir_for_tipo(tipo: str) -> str:
    if tipo == "foto":
        return "foto"
    if tipo == "scheda_sopralluogo":
        return "sopralluoghi"
    if tipo == "documento":
        return "documenti"
    return "allegati"


def _available_destination(destination_dir: Path, filename: str, source: Path) -> Path:
    candidate = destination_dir / filename
    if candidate.exists() and candidate.stat().st_size == source.stat().st_size:
        return candidate.resolve()
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while candidate.exists():
        candidate = destination_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def _unique_folder(folder: Path) -> Path:
    candidate = folder
    counter = 1
    while candidate.exists():
        candidate = folder.with_name(f"{folder.name}_{counter}")
        counter += 1
    return candidate


def _find_fascicolo(registry: dict[str, list[dict[str, Any]]], segnalazione_id: int) -> dict[str, Any] | None:
    for item in registry["fascicoli"]:
        if int(item.get("segnalazione_id", 0)) == int(segnalazione_id):
            return item
    return None


def _find_attachment_by_path(
    registry: dict[str, list[dict[str, Any]]],
    segnalazione_id: int,
    relative_path: str,
) -> dict[str, Any] | None:
    for item in registry["allegati"]:
        if int(item.get("segnalazione_id", 0)) == int(segnalazione_id) and item.get("relative_path") == relative_path:
            return item
    return None


def _ensure_safe_attachment_delete(registry: dict[str, list[dict[str, Any]]], segnalazione_id: int, file_path: Path) -> None:
    folder_record = _find_fascicolo(registry, segnalazione_id)
    if folder_record is None:
        raise RuntimeError("Fascicolo non trovato per l'allegato selezionato.")
    folder = relative_to_path(str(folder_record.get("relative_path", ""))).resolve()
    candidate = file_path.resolve()
    try:
        candidate.relative_to(folder)
    except ValueError as exc:
        raise RuntimeError("Eliminazione bloccata: il file non si trova nel fascicolo della pratica.") from exc


def _next_attachment_id(registry: dict[str, list[dict[str, Any]]]) -> int:
    return max((int(item.get("id_allegato", 0)) for item in registry["allegati"]), default=0) + 1


def _attachment_from_dict(raw: dict[str, Any]) -> FascicoloAttachment:
    sopralluogo_id = raw.get("sopralluogo_id")
    return FascicoloAttachment(
        id_allegato=int(raw.get("id_allegato", 0)),
        segnalazione_id=int(raw.get("segnalazione_id", 0)),
        relative_path=str(raw.get("relative_path", "")),
        nome_file=str(raw.get("nome_file", "")),
        tipo=str(raw.get("tipo", "allegato")),
        origine=str(raw.get("origine", "segnalazione")),
        data_aggiunta=str(raw.get("data_aggiunta", "")),
        sopralluogo_id=int(sopralluogo_id) if sopralluogo_id else None,
        descrizione=str(raw.get("descrizione", "")),
    )


def _segnalazione_id(segnalazione) -> int:
    return int(getattr(segnalazione, "numero_progressivo"))


def _segnalazione_date(segnalazione) -> str:
    parts = [str(getattr(segnalazione, field, "")).strip() for field in ("giorno", "mese", "anno")]
    text = "/".join(part for part in parts if part)
    return text or "-"
