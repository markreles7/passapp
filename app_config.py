from __future__ import annotations

import json
import logging
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from ui_style import MODULE_COLORS, modern_theme

SOURCE_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = SOURCE_DIR
    RESOURCE_DIR = SOURCE_DIR
CONFIG_PATH = BASE_DIR / "data" / "config.json"
BUNDLED_CONFIG_PATH = RESOURCE_DIR / "data" / "config.json"

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "log_file": "data/passapp.log",
        "segnalazioni_file": "data/segnalazioni.json",
        "documents_dir": "documenti",
        "segnalazioni_pdf_dir": "documenti/segnalazioni_pdf",
        "fascicoli_segnalazioni_dir": "documenti/fascicoli_segnalazioni",
        "report_mensili_dir": "documenti/report_mensili",
        "templates_dir": "templates",
        "verbale_sopralluogo_template": "templates/verbale_sopralluogo.doc",
        "fascicolo_fotografico_template": "templates/fascicolo_fotografico.doc",
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
    "ai": {
        "gemini_api_key": "",
        "gemini_model": "gemini-3-flash-preview",
        "gemini_base_prompt": (
            "Sei un assistente redazionale per un ufficio di Polizia Locale. "
            "Devi trasformare i dati inseriti dagli operatori in testi amministrativi chiari, formali e professionali. "
            "Usa solo i dati disponibili, non inventare norme, responsabilita, misure, nominativi, date o fatti. "
            "Se un dato non e presente, indica che non risulta agli atti. "
            "Mantieni un tono neutro e istituzionale, evitando frasi colloquiali o valutazioni personali."
        ),
        "gemini_enabled_for_segnalazione_pdf": True,
        "gemini_enabled_for_sopralluogo": True,
        "gemini_timeout_seconds": 45,
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


def _apply_modern_ui_theme(config: dict[str, Any]) -> None:
    ui = config.setdefault("ui", {})
    theme = ui.setdefault("theme", {})
    theme.update(modern_theme())

    modules = ui.setdefault("modules", {})
    module_labels = {
        "sopralluoghi": {
            "title": "Sopralluoghi - Polizia Locale",
            "menu_title": "Sopralluoghi",
            "menu_description": "Gestione sopralluoghi collegati alle segnalazioni.",
            "icon": "SP",
        },
        "report": {
            "title": "Report mensile",
            "menu_title": "Report mensile",
            "menu_description": "Riepilogo mensile attivita e moduli.",
            "icon": "RM",
        },
        "contatti": {
            "title": "Contatti utili",
            "menu_title": "Contatti utili",
            "menu_description": "Rubrica uffici, enti e riferimenti operativi.",
            "icon": "CT",
        },
        "audit": {
            "title": "Storico modifiche",
            "menu_title": "Storico modifiche",
            "menu_description": "Consultazione audit trail e operazioni registrate.",
            "icon": "AU",
        },
    }
    for key, defaults in module_labels.items():
        modules.setdefault(key, defaults)

    for key, (accent, accent_dark) in MODULE_COLORS.items():
        if key in modules:
            modules[key]["accent"] = accent
            modules[key]["accent_dark"] = accent_dark


def load_config(force_reload: bool = False) -> dict[str, Any]:
    global _CONFIG_CACHE, _CONFIG_DIAGNOSTIC
    if _CONFIG_CACHE is not None and not force_reload:
        return _CONFIG_CACHE

    config = deepcopy(DEFAULT_CONFIG)
    _CONFIG_DIAGNOSTIC = None
    config_path = CONFIG_PATH
    if getattr(sys, "frozen", False) and not config_path.exists() and BUNDLED_CONFIG_PATH.exists():
        config_path = BUNDLED_CONFIG_PATH

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            config = _deep_merge(config, raw)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as exc:
        _CONFIG_DIAGNOSTIC = f"Configurazione JSON non valida in {config_path}: {exc}"
        logger.warning(_CONFIG_DIAGNOSTIC)
    except OSError as exc:
        _CONFIG_DIAGNOSTIC = f"Configurazione non leggibile in {config_path}: {exc}"
        logger.warning(_CONFIG_DIAGNOSTIC)

    _apply_modern_ui_theme(config)
    _CONFIG_CACHE = config
    return config


def save_config(config: dict[str, Any]) -> None:
    global _CONFIG_CACHE
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _CONFIG_CACHE = None


def get_config_diagnostic() -> str | None:
    return _CONFIG_DIAGNOSTIC


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "assets":
        return RESOURCE_DIR / path
    return BASE_DIR / path
