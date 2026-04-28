from __future__ import annotations

import glob
import importlib.util
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app_config import CONFIG_PATH, get_config_diagnostic, load_config, resolve_path
from core.powershell import check_office_com

OK = "OK"
WARNING = "ATTENZIONE"
ERROR = "ERRORE"


@dataclass(frozen=True)
class DiagnosticItem:
    status: str
    name: str
    detail: str


def _item(status: str, name: str, detail: str) -> DiagnosticItem:
    return DiagnosticItem(status=status, name=name, detail=detail)


def _check_import(module_name: str) -> DiagnosticItem:
    if importlib.util.find_spec(module_name) is not None:
        return _item(OK, f"Libreria {module_name}", "Disponibile.")
    return _item(ERROR, f"Libreria {module_name}", "Non disponibile: installare le dipendenze richieste.")


def _check_writable_dir(path: Path, label: str) -> DiagnosticItem:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="passapp_check_", suffix=".tmp", dir=path, delete=False) as handle:
            handle.write(b"ok")
            temp_name = handle.name
        Path(temp_name).unlink(missing_ok=True)
        return _item(OK, label, f"Scrittura disponibile: {path}")
    except OSError as exc:
        return _item(ERROR, label, f"Scrittura non disponibile: {path} ({exc})")


def _check_office_com(app_name: str, label: str) -> DiagnosticItem:
    available, detail = check_office_com(app_name)
    if available:
        return _item(OK, label, detail)
    if detail == "Controllo disponibile solo su Windows.":
        return _item(WARNING, label, detail)
    return _item(ERROR, label, detail)


def _check_config_file_exists() -> DiagnosticItem:
    if CONFIG_PATH.exists():
        return _item(OK, "File configurazione", f"Presente: {CONFIG_PATH}")
    return _item(WARNING, "File configurazione", f"Mancante: {CONFIG_PATH}. Verranno usati i default.")


def _check_config_validity() -> tuple[dict, DiagnosticItem]:
    config = load_config(force_reload=True)
    diagnostic = get_config_diagnostic()
    if diagnostic:
        return config, _item(ERROR, "Validità configurazione", diagnostic)

    if CONFIG_PATH.exists():
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return config, _item(ERROR, "Validità configurazione", str(exc))
        if not isinstance(raw, dict):
            return config, _item(ERROR, "Validità configurazione", "Il file config.json non contiene un oggetto JSON.")

    return config, _item(OK, "Validità configurazione", "Configurazione caricata correttamente.")


def _check_folder(path: Path, label: str) -> DiagnosticItem:
    if path.exists() and path.is_dir():
        return _item(OK, label, f"Cartella disponibile: {path}")
    return _item(ERROR, label, f"Cartella non trovata: {path}")


def _check_pattern_files(folder: Path, patterns: list[str], label: str) -> DiagnosticItem:
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(glob.glob(str(folder / pattern)))
    unique_matches = sorted(set(matches))
    if unique_matches:
        return _item(OK, label, f"Trovati {len(unique_matches)} file.")
    pattern_label = ", ".join(patterns)
    return _item(WARNING, label, f"Nessun file trovato con pattern: {pattern_label}")


def run_diagnostics() -> list[DiagnosticItem]:
    config, config_validity = _check_config_validity()
    paths = config.get("paths", {})

    pass_folder = Path(paths.get("pass_invalidi_network_folder", ""))
    pass_pattern = str(paths.get("pass_invalidi_pattern", ""))
    osp_folder = Path(paths.get("ospitalita_network_folder", ""))
    osp_patterns = [str(p) for p in paths.get("ospitalita_patterns", [])]
    seg_pdf_dir = resolve_path(paths.get("segnalazioni_pdf_dir", "documenti/segnalazioni_pdf"))
    data_dir = resolve_path("data")
    workcopies_dir = data_dir / "workcopies"

    items = [
        _check_config_file_exists(),
        config_validity,
        _check_folder(pass_folder, "Cartella Pass Invalidi"),
        _check_pattern_files(pass_folder, [pass_pattern], "File Pass Invalidi") if pass_pattern else _item(
            ERROR, "File Pass Invalidi", "Pattern Pass Invalidi non configurato."
        ),
        _check_folder(osp_folder, "Cartella Ospitalità"),
        _check_pattern_files(osp_folder, osp_patterns, "File Ospitalità") if osp_patterns else _item(
            ERROR, "File Ospitalità", "Pattern Ospitalità non configurati."
        ),
        _check_writable_dir(seg_pdf_dir, "Cartella PDF segnalazioni"),
        _check_import("openpyxl"),
        _check_import("xlrd"),
        _check_office_com("Word.Application", "Microsoft Word"),
        _check_office_com("Excel.Application", "Microsoft Excel"),
        _check_writable_dir(data_dir, "Permessi scrittura data"),
        _check_writable_dir(workcopies_dir, "Permessi scrittura workcopies"),
    ]
    return items
