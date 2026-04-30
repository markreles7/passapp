from __future__ import annotations

import json
import tkinter as tk
from tkinter import filedialog, messagebox

from app_config import CONFIG_PATH, load_config, save_config
from ui_style import (
    APP_BG,
    CARD_BG,
    CARD_BORDER,
    SECONDARY,
    TEXT,
    TEXT_MUTED,
    create_card,
    create_primary_button,
)


class ConfigurazioneInizialeFrame(tk.Frame):
    def __init__(self, parent, controller=None):
        super().__init__(parent, bg=APP_BG)
        self.controller = controller
        self.status_var = tk.StringVar()
        self.fields: dict[str, tk.StringVar] = {}
        self._build_ui()

    def on_show(self):
        if self.controller is not None:
            self.controller.title("Configurazione iniziale - PassApp")

    def _build_ui(self):
        shell = tk.Frame(self, bg=APP_BG)
        shell.pack(fill="both", expand=True, padx=28, pady=24)

        tk.Label(
            shell,
            text="Configurazione iniziale",
            bg=APP_BG,
            fg=TEXT,
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            shell,
            text="Imposta i percorsi usati dai moduli operativi per questo Comune.",
            bg=APP_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(8, 18))

        card, inner = create_card(shell, padx=18, pady=16)
        card.pack(fill="both", expand=True)
        form = tk.Frame(inner, bg=CARD_BG)
        form.pack(fill="both", expand=True)
        form.columnconfigure(1, weight=1)

        rows = (
            ("paths.pass_invalidi_network_folder", "Cartella Pass Invalidi", "dir"),
            ("paths.pass_invalidi_pattern", "Pattern file Pass Invalidi", "text"),
            ("paths.pass_invalidi_docs_folder", "Cartella documenti Pass Invalidi", "dir"),
            ("paths.pass_invalidi_authorization_template", "Modello autorizzazione Pass", "file"),
            ("paths.ospitalita_network_folder", "Cartella Ospitalita Stranieri", "dir"),
            ("paths.ospitalita_patterns", "Pattern file Ospitalita", "text"),
            ("paths.segnalazioni_file", "File segnalazioni JSON", "file"),
            ("paths.documents_dir", "Cartella documenti", "dir"),
            ("paths.segnalazioni_pdf_dir", "Cartella PDF segnalazioni", "dir"),
            ("paths.fascicoli_segnalazioni_dir", "Cartella fascicoli segnalazioni", "dir"),
            ("paths.report_mensili_dir", "Cartella report mensili", "dir"),
            ("paths.logo_path", "Logo applicazione", "file"),
        )

        config = load_config(force_reload=True)
        for row_index, (key, label, browse_type) in enumerate(rows):
            value = self._get_value(config, key)
            variable = tk.StringVar(value=value)
            self.fields[key] = variable
            self._field_row(form, row_index, label, variable, browse_type)

        footer = tk.Frame(inner, bg=CARD_BG)
        footer.pack(fill="x", pady=(16, 0))
        tk.Label(
            footer,
            textvariable=self.status_var,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        create_primary_button(footer, "Salva configurazione", self._save).pack(side="right")

        tk.Label(
            shell,
            text=f"File configurazione: {CONFIG_PATH}",
            bg=APP_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor="w", pady=(10, 0))

    def _field_row(self, parent, row_index, label, variable, browse_type):
        tk.Label(
            parent,
            text=label,
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=row_index, column=0, sticky="w", padx=(0, 12), pady=6)
        tk.Entry(
            parent,
            textvariable=variable,
            bg="#FFFFFF",
            fg=TEXT,
            relief="solid",
            bd=1,
            font=("Segoe UI", 10),
        ).grid(row=row_index, column=1, sticky="ew", pady=6, ipady=5)
        if browse_type in {"dir", "file"}:
            tk.Button(
                parent,
                text="Sfoglia",
                bg=SECONDARY,
                fg=TEXT,
                activebackground=CARD_BORDER,
                relief="flat",
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                padx=12,
                pady=6,
                command=lambda: self._browse(variable, browse_type),
            ).grid(row=row_index, column=2, sticky="e", padx=(8, 0), pady=6)
        else:
            tk.Label(parent, text="", bg=CARD_BG).grid(row=row_index, column=2)

    def _browse(self, variable, browse_type):
        if browse_type == "dir":
            selected = filedialog.askdirectory(parent=self)
        else:
            selected = filedialog.askopenfilename(parent=self)
        if selected:
            variable.set(selected)

    def _save(self):
        raw_config = self._load_raw_config()
        raw_config.setdefault("paths", {})

        for key, variable in self.fields.items():
            section, field = key.split(".", 1)
            value = variable.get().strip()
            if field == "ospitalita_patterns":
                raw_config.setdefault(section, {})[field] = [
                    item.strip() for item in value.split(";") if item.strip()
                ]
            elif value:
                raw_config.setdefault(section, {})[field] = value

        try:
            save_config(raw_config)
        except OSError as exc:
            messagebox.showerror(
                "Configurazione non salvata",
                f"Impossibile salvare il file di configurazione.\n\n{exc}",
                parent=self,
            )
            return
        self.status_var.set("Configurazione salvata. Riavvia PassApp per ricaricare tutti i moduli.")
        messagebox.showinfo(
            "Configurazione salvata",
            "I percorsi sono stati salvati. Riavvia PassApp per applicarli a tutti i moduli.",
            parent=self,
        )

    @staticmethod
    def _load_raw_config():
        if not CONFIG_PATH.exists():
            return {}
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _get_value(config, key):
        section, field = key.split(".", 1)
        value = config.get(section, {}).get(field, "")
        if isinstance(value, list):
            return "; ".join(str(item) for item in value)
        return str(value)
