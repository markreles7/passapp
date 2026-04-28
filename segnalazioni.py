from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import load_config, resolve_path
from core.fascicoli import add_attachment, ensure_fascicolo, generate_photo_sheet_html, open_path
from core.logging_utils import setup_module_logger
from core.powershell import check_office_com
from fascicoli import FascicoloWindow, fascicolo_status_text
from sopralluoghi import SopralluoghiWindow

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
UI_CONFIG = APP_CONFIG["ui"]
THEME = UI_CONFIG["theme"]

BG = THEME["bg"]
BG2 = THEME["bg2"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = UI_CONFIG["modules"]["segnalazioni"]["accent"]
ACCENT_DARK = UI_CONFIG["modules"]["segnalazioni"]["accent_dark"]
SUCCESS = THEME["success"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]
TEXT_DIM = THEME["text_dim"]

MODALITA_OPZIONI = ("Personalmente", "Telefonicamente")
STATO_OPZIONI = ("in_corso", "archiviata")
DATA_DIR = resolve_path("data")
SEGNALAZIONI_FILE = resolve_path(PATHS["segnalazioni_file"])
SEGNALAZIONI_BACKUP_FILE = Path(f"{SEGNALAZIONI_FILE}.bak")
LOG_FILE = resolve_path(PATHS["log_file"])
DOCS_DIR = resolve_path(PATHS["documents_dir"])
SEGNALAZIONI_PDF_DIR = resolve_path(PATHS["segnalazioni_pdf_dir"])

try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass

logger = setup_module_logger(__name__, LOG_FILE)


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
            self.stato,
        ]
        return " ".join(parts).lower()

    @classmethod
    def from_dict(cls, raw: dict) -> Segnalazione | None:
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
            stato=stato,
        )


class SegnalazioniFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller

        self.segnalazioni: list[Segnalazione] = []
        self._next_progressivo = 1
        self._selected_numero: int | None = None
        self._selected_stato: str | None = None
        self._detail_widgets: list[tk.Widget] = []
        self._readonly_widgets: list[tk.Entry] = []
        self._radio_widgets: list[tk.Radiobutton] = []
        self._save_error_notified = False
        self._detail_canvas: tk.Canvas | None = None
        self._word_available: bool | None = None

        self.search_in_corso = tk.StringVar()
        self.search_archiviate = tk.StringVar()
        self.search_in_corso.trace_add("write", lambda *_: self._refresh_trees())
        self.search_archiviate.trace_add("write", lambda *_: self._refresh_trees())

        self.var_numero = tk.StringVar()
        self.var_anno = tk.StringVar()
        self.var_mese = tk.StringVar()
        self.var_giorno = tk.StringVar()
        self.var_ora = tk.StringVar()
        self.var_nominativo = tk.StringVar()
        self.var_residenza = tk.StringVar()
        self.var_indirizzo = tk.StringVar()
        self.var_telefono = tk.StringVar()
        self.var_modalita = tk.StringVar(value=MODALITA_OPZIONI[0])
        self.var_ricevente = tk.StringVar()
        self.var_agente = tk.StringVar()
        self.var_data_verifica = tk.StringVar()
        self.var_stato = tk.StringVar(value="in_corso")

        self._ttk_style = ttk.Style(self)
        self._setup_styles()
        self._load_from_disk()
        self._build_ui()
        self._refresh_trees()
        self._clear_detail()

    def on_show(self):
        self.controller.title(UI_CONFIG["modules"]["segnalazioni"]["title"])

    def _setup_styles(self):
        try:
            self._ttk_style.theme_use("clam")
        except tk.TclError:
            pass

        self._ttk_style.configure("Segn.TNotebook", background=SURFACE, borderwidth=0, tabmargins=(8, 8, 8, 0))
        self._ttk_style.configure(
            "Segn.TNotebook.Tab",
            background=BG2,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            padding=(16, 9),
            borderwidth=0,
        )
        self._ttk_style.map(
            "Segn.TNotebook.Tab",
            background=[("selected", "#FFF2E1"), ("active", "#F8E9D4")],
            foreground=[("selected", ACCENT_DARK), ("active", ACCENT_DARK)],
        )

        self._ttk_style.configure(
            "Segn.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=34,
            font=("Segoe UI", 10),
            bordercolor=BORDER,
            relief="flat",
        )
        self._ttk_style.configure(
            "Segn.Treeview.Heading",
            background=BG2,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bordercolor=BORDER,
        )
        self._ttk_style.map(
            "Segn.Treeview",
            background=[("selected", "#FFE8C7")],
            foreground=[("selected", ACCENT_DARK)],
        )
        self._ttk_style.map("Segn.Treeview.Heading", background=[("active", BORDER)])

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=24, pady=18)

        self._build_header(shell)

        split = tk.PanedWindow(shell, orient="horizontal", sashrelief="flat", bd=0, bg=BG, sashwidth=8)
        split.pack(fill="both", expand=True, pady=(14, 0))

        left = tk.Frame(split, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        right = tk.Frame(split, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        split.add(left, stretch="always", minsize=400)
        split.add(right, stretch="always", minsize=500)

        self._build_lists_panel(left)
        self._build_detail_panel(right)

    def _build_header(self, parent):
        hdr = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        hdr.pack(fill="x")

        top = tk.Frame(hdr, bg=SURFACE)
        top.pack(fill="x", padx=18, pady=(14, 8))

        title_wrap = tk.Frame(top, bg=SURFACE)
        title_wrap.pack(side="left")

        tk.Label(
            title_wrap,
            text="📝",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 15),
            width=2,
            padx=6,
            pady=4,
        ).pack(side="left", padx=(0, 12))

        title_box = tk.Frame(title_wrap, bg=SURFACE)
        title_box.pack(side="left")
        tk.Label(
            title_box,
            text="Gestione Segnalazioni Cittadini",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Polizia Locale",
            bg=SURFACE,
            fg=ACCENT,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        actions = tk.Frame(top, bg=SURFACE)
        actions.pack(side="right")

        tk.Button(
            actions,
            text="← Torna al Menu Principale",
            bg=BG2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=12,
            pady=8,
            command=lambda: self.controller.show_frame("MainMenuFrame"),
        ).pack(side="right", padx=(10, 0))

        tk.Button(
            actions,
            text="➕ Nuova Segnalazione",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=14,
            pady=8,
            command=self._new_report,
        ).pack(side="right")

        cards = tk.Frame(hdr, bg=SURFACE)
        cards.pack(fill="x", padx=18, pady=(2, 14))

        self.lbl_in_corso = self._stat_card(cards, "Segnalazioni in corso", ACCENT, "📌")
        self.lbl_archiviate = self._stat_card(cards, "Segnalazioni archiviate", SUCCESS, "🗂")

    def _stat_card(self, parent, title, color, icon):
        box = tk.Frame(parent, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        box.pack(side="left", padx=(0, 10))
        tk.Label(box, text=f"{icon} {title}", bg=BG2, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold"), padx=10, pady=5).pack(
            anchor="w"
        )
        lbl = tk.Label(box, text="0", bg=BG2, fg=color, font=("Segoe UI", 16, "bold"), padx=10, pady=8)
        lbl.pack(anchor="w")
        return lbl

    def _build_lists_panel(self, parent):
        tk.Label(
            parent,
            text="Registro Segnalazioni",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=12, pady=(12, 0))

        self.notebook = ttk.Notebook(parent, style="Segn.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(8, 10))

        self.tab_in = tk.Frame(self.notebook, bg=SURFACE)
        self.tab_arch = tk.Frame(self.notebook, bg=SURFACE)
        self.notebook.add(self.tab_in, text="In corso")
        self.notebook.add(self.tab_arch, text="Archiviate")

        self.tree_in = self._build_single_list(self.tab_in, self.search_in_corso, "in_corso")
        self.tree_arch = self._build_single_list(self.tab_arch, self.search_archiviate, "archiviata")

    def _build_single_list(self, parent, search_var, stato):
        top = tk.Frame(parent, bg=SURFACE)
        top.pack(fill="x", padx=12, pady=(10, 8))

        search_box = tk.Frame(top, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        search_box.pack(fill="x")
        tk.Label(search_box, text="🔍", bg=SURFACE, font=("Segoe UI", 11), padx=10).pack(side="left")
        tk.Entry(
            search_box,
            textvariable=search_var,
            font=("Segoe UI", 10),
            relief="flat",
            bd=0,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=ACCENT,
        ).pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(
            search_box,
            text="✕",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
            relief="flat",
            cursor="hand2",
            activebackground=BG2,
            command=lambda: search_var.set(""),
        ).pack(side="right", padx=8)

        frame = tk.Frame(parent, bg=SURFACE)
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        vsb = ttk.Scrollbar(frame, orient="vertical")
        vsb.pack(side="right", fill="y")

        tree = ttk.Treeview(
            frame,
            columns=("numero", "data", "ora", "nominativo", "ricevente"),
            show="headings",
            yscrollcommand=vsb.set,
            selectmode="browse",
            style="Segn.Treeview",
        )
        tree.heading("numero", text="N°")
        tree.heading("data", text="Data")
        tree.heading("ora", text="Ora")
        tree.heading("nominativo", text="Nominativo")
        tree.heading("ricevente", text="Ricevente")

        tree.column("numero", width=55, anchor="center")
        tree.column("data", width=95, anchor="center")
        tree.column("ora", width=70, anchor="center")
        tree.column("nominativo", width=180, anchor="w")
        tree.column("ricevente", width=120, anchor="w")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("odd", background="#FAFAF8")
        tree.tag_configure("even", background=SURFACE)
        tree.tag_configure("arch", foreground=TEXT_MUTED)
        vsb.config(command=tree.yview)
        tree.bind("<<TreeviewSelect>>", lambda _e, t=tree, s=stato: self._on_select(t, s))
        return tree

    def _build_detail_panel(self, parent):
        head = tk.Frame(parent, bg=SURFACE)
        head.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(
            head,
            text="Dettaglio Segnalazione",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            head,
            text="Compila i dati della segnalazione e della verifica.",
            bg=SURFACE,
            fg=TEXT_DIM,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        canvas_shell = tk.Frame(parent, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        canvas_shell.pack(fill="both", expand=True, padx=12, pady=(8, 8))
        canvas_wrap = tk.Frame(canvas_shell, bg=SURFACE)
        canvas_wrap.pack(fill="both", expand=True, padx=1, pady=1)

        vsb = ttk.Scrollbar(canvas_wrap, orient="vertical")
        vsb.pack(side="right", fill="y")

        canvas = tk.Canvas(canvas_wrap, bg=SURFACE, highlightthickness=0, yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.config(command=canvas.yview)
        self._detail_canvas = canvas

        self.detail_inner = tk.Frame(canvas, bg=SURFACE)
        self.detail_window = canvas.create_window((0, 0), window=self.detail_inner, anchor="nw")
        self.detail_inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(self.detail_window, width=e.width))
        self._bind_detail_mousewheel(canvas_wrap, canvas)

        self._build_form_fields()

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=12)

        footer = tk.Frame(parent, bg=SURFACE)
        footer.pack(fill="x", padx=12, pady=(10, 12))

        self.btn_save = tk.Button(
            footer,
            text="Salva Segnalazione",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=16,
            pady=9,
            command=self._save_current,
        )
        self.btn_save.pack(side="left")

        self.btn_concludi = tk.Button(
            footer,
            text="Concludi Segnalazione",
            bg=SUCCESS,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground="#17744B",
            padx=16,
            pady=9,
            command=self._concludi_current,
        )
        self.btn_concludi.pack(side="left", padx=(8, 0))

        self.btn_pdf = tk.Button(
            footer,
            text="Salva in PDF",
            bg="#355C7D",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground="#2A4A65",
            padx=16,
            pady=9,
            command=self._export_selected_pdf,
        )
        self.btn_pdf.pack(side="left", padx=(8, 0))

        self.btn_sopralluoghi = tk.Button(
            footer,
            text="Sopralluoghi",
            bg="#6A4C93",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground="#563B78",
            padx=16,
            pady=9,
            command=self._open_sopralluoghi,
        )
        self.btn_sopralluoghi.pack(side="left", padx=(8, 0))

        self.btn_elimina = tk.Button(
            footer,
            text="Elimina Segnalazione",
            bg="#B33B2E",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground="#8E2E24",
            padx=16,
            pady=9,
            command=self._delete_selected_report,
        )
        self.btn_elimina.pack(side="left", padx=(8, 0))

        self.btn_annulla = tk.Button(
            footer,
            text="Annulla / Torna indietro",
            bg=BG2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=16,
            pady=9,
            command=self._annulla_torna_indietro,
        )
        self.btn_annulla.pack(side="left", padx=(8, 0))

        fascicolo_bar = tk.Frame(parent, bg=SURFACE)
        fascicolo_bar.pack(fill="x", padx=12, pady=(0, 12))
        self.lbl_fascicolo = tk.Label(
            fascicolo_bar,
            text="Fascicolo: non creato",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        )
        self.lbl_fascicolo.pack(anchor="w", pady=(0, 6))

        fascicolo_actions = tk.Frame(fascicolo_bar, bg=SURFACE)
        fascicolo_actions.pack(fill="x")
        self.btn_crea_fascicolo = self._small_action_button(fascicolo_actions, "Crea fascicolo", ACCENT, self._create_fascicolo)
        self.btn_crea_fascicolo.pack(side="left")
        self.btn_apri_fascicolo = self._small_action_button(fascicolo_actions, "Apri fascicolo", "#355C7D", self._open_fascicolo)
        self.btn_apri_fascicolo.pack(side="left", padx=(6, 0))
        self.btn_add_foto = self._small_action_button(
            fascicolo_actions,
            "Aggiungi foto",
            SUCCESS,
            lambda: self._add_fascicolo_files("foto"),
        )
        self.btn_add_foto.pack(side="left", padx=(6, 0))
        self.btn_add_allegato = self._small_action_button(
            fascicolo_actions,
            "Aggiungi allegato",
            "#6A4C93",
            lambda: self._add_fascicolo_files("allegato"),
        )
        self.btn_add_allegato.pack(side="left", padx=(6, 0))
        self.btn_mostra_allegati = self._small_action_button(
            fascicolo_actions,
            "Mostra allegati",
            BG2,
            self._show_fascicolo,
            fg=TEXT_MUTED,
        )
        self.btn_mostra_allegati.pack(side="left", padx=(6, 0))
        self.btn_scheda_fotografica = self._small_action_button(
            fascicolo_actions,
            "Genera scheda fotografica",
            "#B33B2E",
            self._generate_photo_sheet,
        )
        self.btn_scheda_fotografica.pack(side="left", padx=(6, 0))

    def _bind_detail_mousewheel(self, scope_widget: tk.Widget, canvas: tk.Canvas):
        def on_wheel(event):
            if event.delta:
                canvas.yview_scroll(-1 * int(event.delta / 120), "units")
                return "break"
            num = getattr(event, "num", None)
            if num == 4:
                canvas.yview_scroll(-1, "units")
                return "break"
            if num == 5:
                canvas.yview_scroll(1, "units")
                return "break"
            return None

        def bind_all(_event):
            self.bind_all("<MouseWheel>", on_wheel)
            self.bind_all("<Button-4>", on_wheel)
            self.bind_all("<Button-5>", on_wheel)

        def unbind_all(_event):
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")

        scope_widget.bind("<Enter>", bind_all, add="+")
        scope_widget.bind("<Leave>", unbind_all, add="+")

    def _build_form_fields(self):
        sec_protocollo = self._section_box("Protocollo / Data / Ora")
        self._compact_protocol_row(sec_protocollo)
        self._entry_row(sec_protocollo, "Stato", self.var_stato, readonly=True)

        sec_cittadino = self._section_box("Dati del Cittadino")
        self._entry_row(sec_cittadino, "Nominativo", self.var_nominativo)
        self._entry_row(sec_cittadino, "Residenza", self.var_residenza)
        self._entry_row(sec_cittadino, "Indirizzo", self.var_indirizzo)
        self._entry_row(sec_cittadino, "Telefono", self.var_telefono)
        self._mode_row(sec_cittadino, "Modalita di segnalazione", self.var_modalita)
        self.txt_descrizione = self._text_row(sec_cittadino, "Segnala", 6)
        self._entry_row(sec_cittadino, "Ricevente", self.var_ricevente)

        sec_verifica = self._section_box("Verifica Ufficio Polizia Locale")
        self._entry_row(sec_verifica, "Agente verificatore", self.var_agente)
        self.txt_verifica = self._text_row(
            sec_verifica,
            "Verifica effettuata dall'Ufficio Polizia Locale",
            5,
        )
        self._entry_row(sec_verifica, "Data verifica", self.var_data_verifica)

    def _section_box(self, title):
        box = tk.Frame(self.detail_inner, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="x", padx=10, pady=8)
        tk.Label(box, text=title, bg=BG2, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=12, pady=(10, 6)
        )
        body = tk.Frame(box, bg=BG2)
        body.pack(fill="x", padx=12, pady=(0, 10))
        return body

    def _small_action_button(self, parent, text, color, command, fg="white"):
        return tk.Button(
            parent,
            text=text,
            bg=color,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=color,
            padx=10,
            pady=6,
            command=command,
        )

    def _compact_protocol_row(self, parent):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=(0, 6))

        def compact(label, var, width, readonly=False):
            cell = tk.Frame(row, bg=BG2)
            cell.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(cell, text=label, bg=BG2, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
            ent = tk.Entry(
                cell,
                textvariable=var,
                font=("Segoe UI", 10),
                relief="solid",
                bd=1,
                width=width,
                bg=SURFACE,
                fg=TEXT,
                insertbackground=ACCENT,
                disabledbackground="#F5F1EA",
                disabledforeground=TEXT_MUTED,
                readonlybackground="#F5F1EA",
            )
            ent.pack(fill="x", ipady=5, pady=(3, 0))
            self._detail_widgets.append(ent)
            if readonly:
                ent.configure(state="readonly")
                self._readonly_widgets.append(ent)
            return ent

        compact("Numero progressivo", self.var_numero, 10, readonly=True)
        compact("Anno", self.var_anno, 6)
        compact("Mese", self.var_mese, 6)
        compact("Giorno", self.var_giorno, 6)
        compact("Ora", self.var_ora, 7)

    def _entry_row(self, parent, label, var, readonly=False):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG2, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold"), width=22, anchor="w").pack(
            side="left"
        )
        ent = tk.Entry(
            row,
            textvariable=var,
            font=("Segoe UI", 10),
            relief="solid",
            bd=1,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=ACCENT,
            disabledbackground="#F5F1EA",
            disabledforeground=TEXT_MUTED,
            readonlybackground="#F5F1EA",
        )
        ent.pack(side="left", fill="x", expand=True, ipady=5)
        self._detail_widgets.append(ent)
        if readonly:
            ent.configure(state="readonly")
            self._readonly_widgets.append(ent)
        return ent

    def _mode_row(self, parent, label, var):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG2, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold"), width=22, anchor="w").pack(
            side="left"
        )

        options = tk.Frame(row, bg=BG2)
        options.pack(side="left", fill="x", expand=True)
        for idx, mode in enumerate(MODALITA_OPZIONI):
            rb = tk.Radiobutton(
                options,
                text=mode,
                value=mode,
                variable=var,
                bg=BG2,
                fg=TEXT,
                activebackground=BG2,
                font=("Segoe UI", 10),
                anchor="w",
                selectcolor=SURFACE,
            )
            rb.pack(side="left", padx=(0 if idx == 0 else 12, 0))
            self._radio_widgets.append(rb)
        return options

    def _text_row(self, parent, label, height):
        row = tk.Frame(parent, bg=BG2)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, bg=BG2, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        txt = tk.Text(
            row,
            height=height,
            font=("Segoe UI", 10),
            wrap="word",
            relief="solid",
            bd=1,
            bg=SURFACE,
            fg=TEXT,
            insertbackground=ACCENT,
            padx=8,
            pady=6,
        )
        txt.pack(fill="x", expand=True, pady=(3, 0))
        self._detail_widgets.append(txt)
        return txt

    def _new_report(self):
        now = dt.datetime.now()
        seg = Segnalazione(
            numero_progressivo=self._next_progressivo,
            anno=f"{now.year}",
            mese=f"{now.month:02d}",
            giorno=f"{now.day:02d}",
            ora=f"{now.hour:02d}:{now.minute:02d}",
            stato="in_corso",
        )
        self._next_progressivo += 1
        self.segnalazioni.append(seg)
        self._save_to_disk()
        self._refresh_trees()
        self.notebook.select(self.tab_in)
        self._select_report(seg.numero_progressivo, "in_corso")

    def _refresh_trees(self):
        self._fill_tree(self.tree_in, "in_corso", self.search_in_corso.get().strip().lower())
        self._fill_tree(self.tree_arch, "archiviata", self.search_archiviate.get().strip().lower())

        n_in = sum(1 for s in self.segnalazioni if s.stato == "in_corso")
        n_arch = sum(1 for s in self.segnalazioni if s.stato == "archiviata")
        self.lbl_in_corso.config(text=str(n_in))
        self.lbl_archiviate.config(text=str(n_arch))

    def _fill_tree(self, tree, stato, query):
        tree.delete(*tree.get_children())
        row_idx = 0
        for seg in self.segnalazioni:
            if seg.stato != stato:
                continue
            if query and query not in seg.searchable_text():
                continue
            iid = f"{stato}:{seg.numero_progressivo}"
            tags = ["odd" if row_idx % 2 else "even"]
            if stato == "archiviata":
                tags.append("arch")
            tree.insert(
                "",
                "end",
                iid=iid,
                tags=tuple(tags),
                values=(
                    seg.numero_progressivo,
                    f"{seg.giorno}/{seg.mese}/{seg.anno}",
                    seg.ora,
                    seg.nominativo or "—",
                    seg.ricevente or "—",
                ),
            )
            row_idx += 1

    def _on_select(self, tree, stato):
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        try:
            numero = int(iid.split(":")[1])
        except Exception:
            return
        self._select_report(numero, stato)

    def _select_report(self, numero, stato):
        report = self._find_report(numero, stato)
        if report is None:
            return
        self._selected_numero = numero
        self._selected_stato = stato
        self._load_detail(report)

    def _find_report(self, numero, stato):
        for seg in self.segnalazioni:
            if seg.numero_progressivo == numero and seg.stato == stato:
                return seg
        return None

    def _load_detail(self, seg: Segnalazione):
        self.var_numero.set(str(seg.numero_progressivo))
        self.var_anno.set(seg.anno)
        self.var_mese.set(seg.mese)
        self.var_giorno.set(seg.giorno)
        self.var_ora.set(seg.ora)
        self.var_nominativo.set(seg.nominativo)
        self.var_residenza.set(seg.residenza)
        self.var_indirizzo.set(seg.indirizzo)
        self.var_telefono.set(seg.telefono)
        self.var_modalita.set(seg.modalita_segnalazione or MODALITA_OPZIONI[0])
        self.var_ricevente.set(seg.ricevente)
        self.var_agente.set(seg.agente_verificatore)
        self.var_data_verifica.set(seg.data_verifica)
        self.var_stato.set(seg.stato)

        self.txt_descrizione.configure(state="normal")
        self.txt_descrizione.delete("1.0", "end")
        self.txt_descrizione.insert("1.0", seg.descrizione_segnalazione or "")
        self.txt_verifica.configure(state="normal")
        self.txt_verifica.delete("1.0", "end")
        self.txt_verifica.insert("1.0", seg.verifica_effettuata or "")

        editable = seg.stato == "in_corso"
        self._set_form_editable(editable)
        self._update_fascicolo_status()

    def _clear_detail(self):
        self.var_numero.set("")
        self.var_anno.set("")
        self.var_mese.set("")
        self.var_giorno.set("")
        self.var_ora.set("")
        self.var_nominativo.set("")
        self.var_residenza.set("")
        self.var_indirizzo.set("")
        self.var_telefono.set("")
        self.var_modalita.set(MODALITA_OPZIONI[0])
        self.var_ricevente.set("")
        self.var_agente.set("")
        self.var_data_verifica.set("")
        self.var_stato.set("")
        self.txt_descrizione.configure(state="normal")
        self.txt_descrizione.delete("1.0", "end")
        self.txt_verifica.configure(state="normal")
        self.txt_verifica.delete("1.0", "end")
        self._set_form_editable(False)
        self._update_fascicolo_status()

    def _clear_tree_selection(self):
        for tree in (self.tree_in, self.tree_arch):
            tree.selection_remove(*tree.selection())

    def _clear_selection(self):
        self._selected_numero = None
        self._selected_stato = None
        self._clear_tree_selection()
        self._clear_detail()

    @staticmethod
    def _is_report_empty(seg: Segnalazione) -> bool:
        fields = (
            seg.nominativo,
            seg.residenza,
            seg.indirizzo,
            seg.telefono,
            seg.descrizione_segnalazione,
            seg.ricevente,
            seg.agente_verificatore,
            seg.verifica_effettuata,
            seg.data_verifica,
        )
        return all(not str(field).strip() for field in fields)

    def _set_form_editable(self, editable):
        for w in self._detail_widgets:
            if isinstance(w, tk.Text):
                w.configure(
                    state="normal" if editable else "disabled",
                    bg=SURFACE if editable else "#F5F1EA",
                    fg=TEXT if editable else TEXT_MUTED,
                )
            elif isinstance(w, tk.Entry):
                if w in self._readonly_widgets:
                    continue
                w.configure(state="normal" if editable else "disabled")
        for rb in self._radio_widgets:
            rb.configure(state="normal" if editable else "disabled")
        self.btn_save.configure(state="normal" if editable else "disabled")
        self.btn_concludi.configure(state="normal" if editable else "disabled")
        selected = self._get_selected() is not None
        self.btn_pdf.configure(state="normal" if selected else "disabled")
        self.btn_sopralluoghi.configure(state="normal" if selected else "disabled")
        self.btn_elimina.configure(state="normal" if selected else "disabled")
        self.btn_annulla.configure(state="normal" if selected else "disabled")
        for button in (
            self.btn_crea_fascicolo,
            self.btn_apri_fascicolo,
            self.btn_add_foto,
            self.btn_add_allegato,
            self.btn_mostra_allegati,
            self.btn_scheda_fotografica,
        ):
            button.configure(state="normal" if selected else "disabled")

    def _validate_form_values(self):
        anno = self.var_anno.get().strip()
        mese = self.var_mese.get().strip()
        giorno = self.var_giorno.get().strip()
        ora = self.var_ora.get().strip()
        nominativo = self.var_nominativo.get().strip()
        descrizione = self.txt_descrizione.get("1.0", "end").strip()
        ricevente = self.var_ricevente.get().strip()

        if not anno or not mese or not giorno:
            return False, "Compila Anno, Mese e Giorno."

        try:
            dt.date(int(anno), int(mese), int(giorno))
        except (TypeError, ValueError):
            return False, "La data (Anno/Mese/Giorno) non e valida."

        try:
            dt.datetime.strptime(ora, "%H:%M")
        except ValueError:
            return False, "L'ora non e valida. Usa il formato HH:MM (es. 09:30)."

        if not nominativo:
            return False, "Il campo Nominativo e obbligatorio."
        if not descrizione:
            return False, "Il campo Segnala e obbligatorio."
        if not ricevente:
            return False, "Il campo Ricevente e obbligatorio."

        return True, ""

    def _save_current(self) -> bool:
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione da modificare.")
            return False
        if seg.stato != "in_corso":
            messagebox.showinfo("Archivio", "Le segnalazioni archiviate sono in sola lettura.")
            return False
        if self.var_modalita.get() not in MODALITA_OPZIONI:
            messagebox.showwarning("Valore non valido", "Modalita di segnalazione non valida.")
            return False

        valid, reason = self._validate_form_values()
        if not valid:
            logger.warning("Validazione segnalazione non superata: %s", reason)
            messagebox.showwarning("Dati non validi", reason)
            return False

        seg.anno = self.var_anno.get().strip()
        seg.mese = self.var_mese.get().strip()
        seg.giorno = self.var_giorno.get().strip()
        seg.ora = self.var_ora.get().strip()
        seg.nominativo = self.var_nominativo.get().strip()
        seg.residenza = self.var_residenza.get().strip()
        seg.indirizzo = self.var_indirizzo.get().strip()
        seg.telefono = self.var_telefono.get().strip()
        seg.modalita_segnalazione = self.var_modalita.get().strip()
        seg.descrizione_segnalazione = self.txt_descrizione.get("1.0", "end").strip()
        seg.ricevente = self.var_ricevente.get().strip()
        seg.agente_verificatore = self.var_agente.get().strip()
        seg.verifica_effettuata = self.txt_verifica.get("1.0", "end").strip()
        seg.data_verifica = self.var_data_verifica.get().strip()
        if not self._save_to_disk():
            return False
        self._refresh_trees()
        self._select_report(seg.numero_progressivo, seg.stato)
        return True

    def _concludi_current(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione da concludere.")
            return
        if seg.stato != "in_corso":
            return

        if not self._save_current():
            return
        seg = self._get_selected()
        if seg is None:
            return
        if not seg.agente_verificatore.strip():
            messagebox.showwarning("Dati incompleti", "Compila il campo Agente verificatore prima di concludere.")
            return
        if not seg.verifica_effettuata.strip():
            messagebox.showwarning("Dati incompleti", "Compila il campo Verifica effettuata prima di concludere.")
            return
        if not seg.data_verifica.strip():
            seg.data_verifica = dt.date.today().strftime("%d/%m/%Y")

        seg.stato = "archiviata"
        if not self._save_to_disk():
            return
        self._refresh_trees()
        self.notebook.select(self.tab_arch)
        self._select_report(seg.numero_progressivo, "archiviata")

    def _annulla_torna_indietro(self):
        seg = self._get_selected()
        if seg is None:
            self.controller.show_frame("MainMenuFrame")
            return

        if seg.stato == "in_corso" and self._is_report_empty(seg):
            if messagebox.askyesno(
                "Annulla nuova segnalazione",
                "La segnalazione e vuota. Vuoi eliminarla?",
                parent=self,
            ):
                self.segnalazioni = [s for s in self.segnalazioni if s.numero_progressivo != seg.numero_progressivo]
                self._save_to_disk()
                self._refresh_trees()
                self._clear_selection()
            return

        self._clear_selection()

    def _delete_selected_report(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione da eliminare.")
            return

        stato_label = "in corso" if seg.stato == "in_corso" else "archiviata"
        if not messagebox.askyesno(
            "Conferma eliminazione",
            f"Eliminare la segnalazione n. {seg.numero_progressivo} ({stato_label})?",
            parent=self,
        ):
            return

        self.segnalazioni = [s for s in self.segnalazioni if s.numero_progressivo != seg.numero_progressivo]
        self._save_to_disk()
        self._refresh_trees()
        self._clear_selection()

    def _open_sopralluoghi(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        SopralluoghiWindow(self, seg)

    def _update_fascicolo_status(self):
        if not hasattr(self, "lbl_fascicolo"):
            return
        seg = self._get_selected()
        if seg is None:
            self.lbl_fascicolo.configure(text="Fascicolo: non creato")
            return
        try:
            self.lbl_fascicolo.configure(text=fascicolo_status_text(seg.numero_progressivo))
        except Exception:
            logger.exception("Errore stato fascicolo segnalazione n. %s", seg.numero_progressivo)
            self.lbl_fascicolo.configure(text="Fascicolo: errore lettura")

    def _create_fascicolo(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            folder = ensure_fascicolo(seg)
        except Exception as exc:
            logger.exception("Errore creazione fascicolo segnalazione n. %s", seg.numero_progressivo)
            messagebox.showerror("Fascicolo non creato", f"Impossibile creare il fascicolo.\n\n{exc}")
            return
        self._update_fascicolo_status()
        messagebox.showinfo("Fascicolo creato", f"Fascicolo disponibile in:\n{folder}")

    def _open_fascicolo(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            open_path(ensure_fascicolo(seg))
        except Exception as exc:
            logger.exception("Errore apertura fascicolo segnalazione n. %s", seg.numero_progressivo)
            messagebox.showerror("Apertura non riuscita", f"Impossibile aprire il fascicolo.\n\n{exc}")
            return
        self._update_fascicolo_status()

    def _add_fascicolo_files(self, tipo: str):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        if tipo == "foto":
            filetypes = [("Immagini", "*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp"), ("Tutti i file", "*.*")]
            title = "Aggiungi foto al fascicolo"
        else:
            filetypes = [("Tutti i file", "*.*")]
            title = "Aggiungi allegato al fascicolo"
        files = filedialog.askopenfilenames(parent=self, title=title, filetypes=filetypes)
        if not files:
            return
        added = 0
        for filename in files:
            try:
                add_attachment(seg, Path(filename), tipo, origine="segnalazione")
                added += 1
            except Exception:
                logger.exception("Errore aggiunta file al fascicolo: %s", filename)
        self._update_fascicolo_status()
        messagebox.showinfo("Fascicolo aggiornato", f"File aggiunti: {added}")

    def _show_fascicolo(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        FascicoloWindow(self, seg)

    def _generate_photo_sheet(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione.")
            return
        try:
            output = generate_photo_sheet_html(seg)
            open_path(output)
        except Exception as exc:
            logger.exception("Errore scheda fotografica segnalazione n. %s", seg.numero_progressivo)
            messagebox.showerror("Scheda non creata", f"Impossibile generare la scheda fotografica.\n\n{exc}")
            return
        self._update_fascicolo_status()

    @staticmethod
    def _safe_filename(value: str) -> str:
        safe = re.sub(r'[\\/:*?"<>|]+', "_", value.strip())
        safe = re.sub(r"\s+", "_", safe)
        return safe[:80] if safe else "segnalazione"

    @staticmethod
    def _repair_mojibake(value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        if not any(marker in text for marker in ("Ã", "Â", "â", "ð")):
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

    def _build_doc_payload(self, seg: Segnalazione) -> dict[str, str]:
        stato_label = "In corso" if seg.stato == "in_corso" else "Archiviata"
        anno = self._repair_mojibake(seg.anno)
        mese = self._repair_mojibake(seg.mese)
        giorno = self._repair_mojibake(seg.giorno)
        ora = self._repair_mojibake(seg.ora)
        data_ora = f"{giorno}/{mese}/{anno} - {ora}".strip(" -") if all((anno, mese, giorno, ora)) else "-"

        def value_or_dash(value: str) -> str:
            text = self._repair_mojibake(value)
            return text if text else "-"

        return {
            "numero": str(seg.numero_progressivo),
            "anno": value_or_dash(anno),
            "stato": stato_label,
            "data_ora_ricezione": data_ora,
            "nominativo": value_or_dash(seg.nominativo),
            "residenza": value_or_dash(seg.residenza),
            "indirizzo": value_or_dash(seg.indirizzo),
            "telefono": value_or_dash(seg.telefono),
            "modalita": value_or_dash(seg.modalita_segnalazione) if seg.modalita_segnalazione else MODALITA_OPZIONI[0],
            "ricevente": value_or_dash(seg.ricevente),
            "descrizione": value_or_dash(seg.descrizione_segnalazione),
            "agente": value_or_dash(seg.agente_verificatore),
            "data_accertamento": value_or_dash(seg.data_verifica or dt.date.today().strftime("%d/%m/%Y")),
            "verifica": value_or_dash(seg.verifica_effettuata),
            "riferimento": f"{seg.numero_progressivo}/{value_or_dash(anno)}",
        }

    def _snapshot_current_form(self, seg: Segnalazione) -> Segnalazione:
        return Segnalazione(
            numero_progressivo=seg.numero_progressivo,
            anno=self.var_anno.get().strip() or seg.anno,
            mese=self.var_mese.get().strip() or seg.mese,
            giorno=self.var_giorno.get().strip() or seg.giorno,
            ora=self.var_ora.get().strip() or seg.ora,
            nominativo=self.var_nominativo.get().strip() or seg.nominativo,
            residenza=self.var_residenza.get().strip() or seg.residenza,
            indirizzo=self.var_indirizzo.get().strip() or seg.indirizzo,
            telefono=self.var_telefono.get().strip() or seg.telefono,
            modalita_segnalazione=self.var_modalita.get().strip() or seg.modalita_segnalazione,
            descrizione_segnalazione=self.txt_descrizione.get("1.0", "end").strip() or seg.descrizione_segnalazione,
            ricevente=self.var_ricevente.get().strip() or seg.ricevente,
            agente_verificatore=self.var_agente.get().strip() or seg.agente_verificatore,
            verifica_effettuata=self.txt_verifica.get("1.0", "end").strip() or seg.verifica_effettuata,
            data_verifica=self.var_data_verifica.get().strip() or seg.data_verifica,
            stato=seg.stato,
        )

    def _export_selected_pdf(self):
        seg = self._get_selected()
        if seg is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona una segnalazione da esportare in PDF.")
            return
        if not self._is_word_available():
            messagebox.showwarning(
                "Microsoft Word non disponibile",
                "Per esportare in PDF e necessario Microsoft Word Desktop installato su questo PC.",
            )
            return

        try:
            SEGNALAZIONI_PDF_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        nominativo = self._safe_filename(seg.nominativo)
        default_name = f"SEGNALAZIONE_{seg.numero_progressivo}_{nominativo}.pdf"
        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Salva segnalazione in PDF",
            initialdir=str(SEGNALAZIONI_PDF_DIR),
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not save_path:
            return

        out_path = Path(save_path)
        payload = self._build_doc_payload(self._snapshot_current_form(seg))
        try:
            self._render_pdf_report(payload, out_path)
        except Exception as exc:
            logger.exception("Errore esportazione PDF segnalazione n. %s", seg.numero_progressivo)
            messagebox.showerror(
                "Esportazione non riuscita",
                f"Impossibile creare il PDF.\n\nDettagli:\n{exc}",
            )
            return

        try:
            add_attachment(seg, out_path, "documento", origine="segnalazione")
            self._update_fascicolo_status()
        except Exception:
            logger.exception("Errore registrazione PDF nel fascicolo segnalazione n. %s", seg.numero_progressivo)

        messagebox.showinfo("PDF creato", f"Segnalazione esportata in:\n{out_path}")

    def _render_pdf_report(self, payload: dict[str, str], output_pdf: Path):
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)

$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param(
        [object]$Selection,
        [string]$Text,
        [int]$Size = 9,
        [bool]$Bold = $false,
        [int]$Alignment = 0,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = $Alignment
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

function Add-LeftRightLine {
    param(
        [object]$Selection,
        [string]$LeftText,
        [string]$RightText,
        [double]$RightTab,
        [int]$Size = 9,
        [bool]$BoldLeft = $false,
        [bool]$BoldRight = $false,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = 0
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.ParagraphFormat.TabStops.ClearAll()
    $null = $Selection.ParagraphFormat.TabStops.Add($RightTab, 2, 0)
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($BoldLeft) { 1 } else { 0 }
    $Selection.TypeText($LeftText)
    $Selection.TypeText("`t")
    $Selection.Font.Bold = if ($BoldRight) { 1 } else { 0 }
    $Selection.TypeText($RightText)
    $Selection.TypeParagraph()
}

function Add-InfoLine {
    param(
        [object]$Selection,
        [string]$LabelLeft,
        [string]$ValueLeft,
        [double]$MidTab,
        [string]$LabelRight = "",
        [string]$ValueRight = "",
        [int]$Size = 9,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = 0
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.ParagraphFormat.TabStops.ClearAll()
    if (-not [string]::IsNullOrWhiteSpace($LabelRight)) {
        $null = $Selection.ParagraphFormat.TabStops.Add($MidTab, 0, 0)
    }
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = 1
    $Selection.TypeText($LabelLeft)
    $Selection.Font.Bold = 0
    $Selection.TypeText($ValueLeft)
    if (-not [string]::IsNullOrWhiteSpace($LabelRight)) {
        $Selection.TypeText("`t")
        $Selection.Font.Bold = 1
        $Selection.TypeText($LabelRight)
        $Selection.Font.Bold = 0
        $Selection.TypeText($ValueRight)
    }
    $Selection.TypeParagraph()
}

function Compact-Text {
    param(
        [string]$Text,
        [int]$MaxLength = 0
    )
    if ([string]::IsNullOrWhiteSpace($Text) -or $Text -eq "-") {
        return "-"
    }

    $clean = (($Text -replace "`r?`n", " ") -replace "\s{2,}", " ").Trim()
    if ($MaxLength -gt 0 -and $clean.Length -gt $MaxLength) {
        $suffix = " [testo completo in PassApp]"
        $limit = [Math]::Max(1, $MaxLength - $suffix.Length)
        return $clean.Substring(0, $limit).TrimEnd() + $suffix
    }
    return $clean
}

function Add-HandLines {
    param(
        [object]$Selection,
        [int]$Rows = 6
    )
    for ($i = 0; $i -lt $Rows; $i++) {
        Add-Paragraph -Selection $Selection -Text "____________________________________________________________________________________________" -Size 9 -SpaceAfter 2
    }
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Add()
    $sel = $word.Selection
    $pageSetup = $doc.PageSetup

    $pageSetup.TopMargin = $word.CentimetersToPoints(1.1)
    $pageSetup.BottomMargin = $word.CentimetersToPoints(1.0)
    $pageSetup.LeftMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.RightMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.HeaderDistance = $word.CentimetersToPoints(0.5)
    $pageSetup.FooterDistance = $word.CentimetersToPoints(0.5)

    $usableWidth = $pageSetup.PageWidth - $pageSetup.LeftMargin - $pageSetup.RightMargin
    $midTab = [Math]::Round($usableWidth * 0.53, 0)
    $rightTab = [Math]::Round($usableWidth, 0)

    $numero = Compact-Text -Text $payload.numero -MaxLength 20
    $stato = Compact-Text -Text $payload.stato -MaxLength 30
    $riferimento = Compact-Text -Text $payload.riferimento -MaxLength 30
    $ricezione = Compact-Text -Text $payload.data_ora_ricezione -MaxLength 40
    $nominativo = Compact-Text -Text $payload.nominativo -MaxLength 85
    $residenza = Compact-Text -Text $payload.residenza -MaxLength 85
    $indirizzo = Compact-Text -Text $payload.indirizzo -MaxLength 110
    $telefono = Compact-Text -Text $payload.telefono -MaxLength 30
    $modalita = Compact-Text -Text $payload.modalita -MaxLength 30
    $ricevente = Compact-Text -Text $payload.ricevente -MaxLength 60
    $descrizione = Compact-Text -Text $payload.descrizione -MaxLength 650
    $agente = Compact-Text -Text $payload.agente -MaxLength 60
    $dataAccertamento = Compact-Text -Text $payload.data_accertamento -MaxLength 30
    $verifica = Compact-Text -Text $payload.verifica -MaxLength 340

    $footerRange = $doc.Sections.Item(1).Footers.Item(1).Range
    $footerRange.Text = "Documento generato automaticamente da PassApp. In caso di compilazione cartacea, riportare l'esito nel gestionale."
    $footerRange.ParagraphFormat.Alignment = 1
    $footerRange.Font.Name = "Calibri"
    $footerRange.Font.Size = 8
    $footerRange.Font.Bold = 0

    Add-Paragraph -Selection $sel -Text "COMUNE DI PEGOGNAGA" -Size 11 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "Polizia Locale" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "MODULO DI SEGNALAZIONE ACCERTAMENTO" -Size 11 -Bold $true -Alignment 1 -SpaceAfter 6

    Add-LeftRightLine -Selection $sel -LeftText ("Pratica n. " + $numero + " - Stato: " + $stato) -RightText ("Rif.: " + $riferimento) -RightTab $rightTab -Size 9 -BoldLeft $true -BoldRight $true -SpaceAfter 5
    Add-InfoLine -Selection $sel -LabelLeft "Data/Ora ricezione: " -ValueLeft $ricezione -MidTab $midTab -LabelRight "Modalita': " -ValueRight $modalita -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Segnalante: " -ValueLeft $nominativo -MidTab $midTab -LabelRight "Operatore ricevente: " -ValueRight $ricevente -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Residenza: " -ValueLeft $residenza -MidTab $midTab -LabelRight "Telefono: " -ValueRight $telefono -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Indirizzo: " -ValueLeft $indirizzo -MidTab $midTab -Size 9 -SpaceAfter 5

    Add-Paragraph -Selection $sel -Text "OGGETTO DELLA SEGNALAZIONE" -Size 9 -Bold $true -Alignment 1 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text $descrizione -Size 9 -SpaceAfter 5

    Add-Paragraph -Selection $sel -Text "ATTIVITA' DI ACCERTAMENTO" -Size 9 -Bold $true -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text ("Agente accertatore: " + $agente + "    Data accertamento: " + $dataAccertamento) -Size 9 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text ("Riscontro registrato in app: " + $verifica) -Size 9 -SpaceAfter 5

    Add-Paragraph -Selection $sel -Text "SPAZIO RISERVATO ALL'AGENTE ACCERTATORE (COMPILAZIONE MANUALE SE NECESSARIO)" -Size 9 -Bold $true -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text "Annotazioni, esito sopralluogo e provvedimenti adottati:" -Size 9 -SpaceAfter 2
    Add-HandLines -Selection $sel -Rows 6

    Add-Paragraph -Selection $sel -Text "Firma operatore ricevente: ____________________" -Size 9 -Alignment 2 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text "Firma agente accertatore: ____________________" -Size 9 -Alignment 2 -SpaceAfter 0

    $doc.ExportAsFixedFormat($PdfPath, 17)
    $doc.Close($false)
    $doc = $null
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
        with tempfile.TemporaryDirectory(prefix="passapp_segn_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            payload_path = tmp_path / "payload.json"
            script_path = tmp_path / "export.ps1"

            payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            script_path.write_text(ps_script, encoding="utf-8")

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(script_path),
                    "-PdfPath",
                    str(output_pdf),
                    "-PayloadPath",
                    str(payload_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if result.returncode != 0:
                details = (result.stderr or result.stdout or "Errore sconosciuto").strip()
                raise RuntimeError(details)

        if not output_pdf.exists():
            raise RuntimeError("Il file PDF non e stato creato.")

    def _is_word_available(self) -> bool:
        if self._word_available is not None:
            return self._word_available
        self._word_available = check_office_com("Word.Application")[0]
        return self._word_available

    def _get_selected(self):
        if self._selected_numero is None or self._selected_stato is None:
            return None
        return self._find_report(self._selected_numero, self._selected_stato)

    def _read_payload_file(self, path: Path):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            logger.exception("Errore lettura file segnalazioni: %s", path)
            return None
        if isinstance(payload, (dict, list)):
            return payload
        logger.warning("Formato segnalazioni non valido: root non lista/dizionario (%s)", path)
        return None

    def _load_from_disk(self):
        self.segnalazioni = []
        self._next_progressivo = 1

        payload = None
        if SEGNALAZIONI_FILE.exists():
            payload = self._read_payload_file(SEGNALAZIONI_FILE)
        if payload is None and SEGNALAZIONI_BACKUP_FILE.exists():
            payload = self._read_payload_file(SEGNALAZIONI_BACKUP_FILE)
            if payload is not None:
                logger.warning("Ripristino segnalazioni da backup: %s", SEGNALAZIONI_BACKUP_FILE)
        if payload is None:
            return

        items = payload.get("segnalazioni", []) if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            logger.warning("Formato segnalazioni non valido: root non lista (%s)", SEGNALAZIONI_FILE)
            return

        max_progressivo = 0
        for raw in items:
            if not isinstance(raw, dict):
                continue
            segnalazione = Segnalazione.from_dict(raw)
            if segnalazione is None:
                continue
            self.segnalazioni.append(segnalazione)
            if segnalazione.numero_progressivo > max_progressivo:
                max_progressivo = segnalazione.numero_progressivo

        self.segnalazioni.sort(key=lambda s: s.numero_progressivo)
        self._next_progressivo = max_progressivo + 1 if max_progressivo > 0 else 1

    def _save_to_disk(self) -> bool:
        tmp_path: Path | None = None
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            payload = {
                "segnalazioni": [asdict(seg) for seg in self.segnalazioni],
            }

            tmp_fd, tmp_name = tempfile.mkstemp(prefix="segnalazioni_", suffix=".tmp", dir=str(DATA_DIR))
            tmp_path = Path(tmp_name)
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())

            if SEGNALAZIONI_FILE.exists():
                try:
                    shutil.copyfile(SEGNALAZIONI_FILE, SEGNALAZIONI_BACKUP_FILE)
                except OSError:
                    logger.exception("Errore creazione backup segnalazioni: %s", SEGNALAZIONI_BACKUP_FILE)

            os.replace(tmp_path, SEGNALAZIONI_FILE)
            self._save_error_notified = False
            return True
        except OSError:
            logger.exception("Errore salvataggio file segnalazioni: %s", SEGNALAZIONI_FILE)
            if not self._save_error_notified:
                messagebox.showwarning(
                    "Salvataggio non riuscito",
                    f"Impossibile salvare il file locale:\n{SEGNALAZIONI_FILE}",
                )
                self._save_error_notified = True
            return False
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
