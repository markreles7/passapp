from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import load_config, resolve_path
from core.fascicoli import (
    add_attachment,
    ensure_fascicolo,
    fascicolo_exists,
    generate_photo_sheet_html,
    get_fascicolo_path,
    list_attachments,
    open_path,
    relative_to_path,
)
from core.logging_utils import setup_module_logger

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
DANGER = THEME["danger"]

LOG_FILE = resolve_path(PATHS["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)


class FascicoloWindow(tk.Toplevel):
    def __init__(self, parent, segnalazione):
        super().__init__(parent)
        self.segnalazione = segnalazione
        self.title(f"Fascicolo digitale - Segnalazione n. {segnalazione.numero_progressivo}")
        self.configure(bg=BG)
        self.geometry("900x560")
        self.minsize(760, 460)
        self.transient(parent.winfo_toplevel())

        self.status_var = tk.StringVar()
        self._setup_styles()
        self._build_ui()
        self._refresh()

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Fasc.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=30,
            font=("Segoe UI", 10),
            bordercolor=BORDER,
        )
        style.configure(
            "Fasc.Treeview.Heading",
            background=BG2,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map("Fasc.Treeview", background=[("selected", "#FFE8C7")], foreground=[("selected", ACCENT_DARK)])

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        tk.Label(
            title_box,
            text=f"Fascicolo digitale - Segnalazione n. {self.segnalazione.numero_progressivo}",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            textvariable=self.status_var,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        tk.Button(
            header,
            text="Chiudi",
            bg=BG2,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            padx=16,
            pady=9,
            command=self.destroy,
        ).pack(side="right", padx=16, pady=12)

        actions = tk.Frame(shell, bg=BG)
        actions.pack(fill="x", pady=(12, 8))
        self._button(actions, "Crea fascicolo", ACCENT, self._create_fascicolo).pack(side="left")
        self._button(actions, "Apri fascicolo", "#355C7D", self._open_fascicolo).pack(side="left", padx=(8, 0))
        self._button(actions, "Aggiungi foto", SUCCESS, lambda: self._add_files("foto")).pack(side="left", padx=(8, 0))
        self._button(actions, "Aggiungi allegato", "#6A4C93", lambda: self._add_files("allegato")).pack(side="left", padx=(8, 0))
        self._button(actions, "Apri file", BG2, self._open_selected, fg=TEXT_MUTED).pack(side="left", padx=(8, 0))
        self._button(actions, "Genera scheda fotografica", DANGER, self._generate_photo_sheet).pack(side="left", padx=(8, 0))

        table_wrap = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        table_wrap.pack(fill="both", expand=True)
        inner = tk.Frame(table_wrap, bg=SURFACE)
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        vsb = ttk.Scrollbar(inner, orient="vertical")
        vsb.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            inner,
            columns=("tipo", "nome", "data", "origine"),
            show="headings",
            yscrollcommand=vsb.set,
            selectmode="browse",
            style="Fasc.Treeview",
        )
        for col, text, width in (
            ("tipo", "Tipo", 110),
            ("nome", "Nome file", 330),
            ("data", "Data aggiunta", 150),
            ("origine", "Origine", 180),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self._open_selected())
        vsb.config(command=self.tree.yview)

    def _button(self, parent, text, color, command, fg="white"):
        return tk.Button(
            parent,
            text=text,
            bg=color,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=color,
            padx=12,
            pady=8,
            command=command,
        )

    def _refresh(self):
        folder = get_fascicolo_path(self.segnalazione.numero_progressivo)
        exists = bool(folder and folder.exists())
        self.status_var.set(f"Fascicolo: {'presente' if exists else 'non creato'} - {folder if folder else 'nessun percorso'}")
        self.tree.delete(*self.tree.get_children())
        for item in list_attachments(self.segnalazione.numero_progressivo):
            origin = item.origine
            if item.sopralluogo_id:
                origin = f"{origin} #{item.sopralluogo_id}"
            self.tree.insert(
                "",
                "end",
                iid=str(item.id_allegato),
                values=(item.tipo, item.nome_file, item.data_aggiunta, origin),
            )

    def _create_fascicolo(self):
        try:
            folder = ensure_fascicolo(self.segnalazione)
        except Exception as exc:
            logger.exception("Errore creazione fascicolo segnalazione n. %s", self.segnalazione.numero_progressivo)
            messagebox.showerror("Fascicolo non creato", f"Impossibile creare il fascicolo.\n\n{exc}", parent=self)
            return
        self._refresh()
        messagebox.showinfo("Fascicolo creato", f"Fascicolo disponibile in:\n{folder}", parent=self)

    def _open_fascicolo(self):
        try:
            folder = ensure_fascicolo(self.segnalazione)
            open_path(folder)
        except Exception as exc:
            logger.exception("Errore apertura fascicolo segnalazione n. %s", self.segnalazione.numero_progressivo)
            messagebox.showerror("Apertura non riuscita", f"Impossibile aprire il fascicolo.\n\n{exc}", parent=self)
            return
        self._refresh()

    def _add_files(self, tipo: str):
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
                add_attachment(self.segnalazione, Path(filename), tipo, origine="segnalazione")
                added += 1
            except Exception:
                logger.exception("Errore aggiunta allegato al fascicolo: %s", filename)
        self._refresh()
        messagebox.showinfo("Allegati aggiornati", f"File aggiunti: {added}", parent=self)

    def _open_selected(self):
        item = self._selected_attachment()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un file da aprire.", parent=self)
            return
        try:
            open_path(relative_to_path(item.relative_path))
        except Exception as exc:
            logger.exception("Errore apertura allegato: %s", item.relative_path)
            messagebox.showerror("Apertura non riuscita", f"Impossibile aprire il file.\n\n{exc}", parent=self)

    def _generate_photo_sheet(self):
        try:
            output = generate_photo_sheet_html(self.segnalazione)
            open_path(output)
        except Exception as exc:
            logger.exception("Errore scheda fotografica segnalazione n. %s", self.segnalazione.numero_progressivo)
            messagebox.showerror("Scheda non creata", f"Impossibile generare la scheda fotografica.\n\n{exc}", parent=self)
            return
        self._refresh()

    def _selected_attachment(self):
        selected = self.tree.selection()
        if not selected:
            return None
        selected_id = int(selected[0])
        for item in list_attachments(self.segnalazione.numero_progressivo):
            if item.id_allegato == selected_id:
                return item
        return None


def fascicolo_status_text(segnalazione_id: int) -> str:
    path = get_fascicolo_path(segnalazione_id)
    if fascicolo_exists(segnalazione_id):
        return f"Fascicolo: presente - {path}"
    if path:
        return f"Fascicolo: registrato, cartella mancante - {path}"
    return "Fascicolo: non creato"
