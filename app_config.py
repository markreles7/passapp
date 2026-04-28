from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "data" / "config.json"

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "log_file": "data/passapp.log",
        "segnalazioni_file": "data/segnalazioni.json",
        "documents_dir": "documenti",
        "segnalazioni_pdf_dir": "documenti/segnalazioni_pdf",
        "fascicoli_segnalazioni_dir": "documenti/fascicoli_segnalazioni",
        "logo_path": "assets/logo.jpg",
        "pass_invalidi_network_folder": r"R:\Polizia_locale\INVALIDI",
        "pass_invalidi_pattern": "REGISTRO INVALIDI COMUNE*.xlsx",
        "ospitalita_network_folder": r"R:\Comune\COMUNICAZIONE OSPITALITA' STRANIERI",
        "ospitalita_patterns": [
            "registro comunicazioni *.xls",
            "registro comunicazioni *.xlsx",
            "*.xls",
            "*.xlsx",
        ],
    },
    "pass_invalidi": {
        "warning_days": 60,
    },
    "ui": {
        "app_name": "PassApp Suite Ufficio Servizi",
        "main_title": "Suite Ufficio Servizi - Polizia Locale",
        "dashboard_title": "Dashboard Servizi Comunali",
        "dashboard_subtitle": "Polizia Locale",
        "dashboard_description": "Seleziona il modulo operativo da aprire.",
        "window": {
            "width": 1180,
            "height": 760,
            "min_width": 980,
            "min_height": 640,
        },
        "theme": {
            "bg": "#F5F3EF",
            "bg2": "#EDE9E3",
            "surface": "#FFFFFF",
            "border": "#DDD8D0",
            "accent": "#2D6BE4",
            "accent_dark": "#1A4FAF",
            "success": "#1E9E6B",
            "warning": "#C97A10",
            "danger": "#C0392B",
            "text": "#1A1A1A",
            "text_muted": "#6B6560",
            "text_dim": "#A09B94",
        },
        "modules": {
            "pass_invalidi": {
                "title": "Pass Invalidi - Polizia Locale",
                "menu_title": "Pass Invalidi",
                "menu_description": "Registro pass, filtri scadenze e dettaglio storico.",
                "icon": "PI",
                "accent": "#2D6BE4",
                "accent_dark": "#1A4FAF",
            },
            "segnalazioni": {
                "title": "Segnalazioni Cittadini - Polizia Locale",
                "menu_title": "Segnalazioni Cittadini",
                "menu_description": "Gestione segnalazioni, assegnazioni e stato lavorazione.",
                "icon": "SC",
                "accent": "#C97A10",
                "accent_dark": "#9C5D08",
            },
            "ospitalita": {
                "title": "Comunicazioni Ospitalita Stranieri - Polizia Locale",
                "menu_title": "Ospitalita Stranieri",
                "menu_description": "Gestione pratiche ospitalita e verifica documentale.",
                "icon": "OS",
                "accent": "#2A7E54",
                "accent_dark": "#1C5A3C",
            },
        },
    },
}

_CONFIG_CACHE: dict[str, Any] | None = None
_CONFIG_DIAGNOSTIC: str | None = None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(force_reload: bool = False) -> dict[str, Any]:
    global _CONFIG_CACHE, _CONFIG_DIAGNOSTIC
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config = deepcopy(DEFAULT_CONFIG)
    _CONFIG_DIAGNOSTIC = None
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config = _deep_merge(config, raw)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as exc:
        _CONFIG_DIAGNOSTIC = f"Configurazione JSON non valida in {CONFIG_PATH}: {exc}"
        logger.warning(_CONFIG_DIAGNOSTIC)
    except OSError as exc:
        _CONFIG_DIAGNOSTIC = f"Configurazione non leggibile in {CONFIG_PATH}: {exc}"
        logger.warning(_CONFIG_DIAGNOSTIC)

    _CONFIG_CACHE = config
    return config


def get_config_diagnostic() -> str | None:
    return _CONFIG_DIAGNOSTIC


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path
