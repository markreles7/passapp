from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app_config import load_config, resolve_path
from core.audit import log_audit_event
from core.fascicoli import add_attachment
from core.logging_utils import setup_module_logger
from core.powershell import check_office_com
from core.sopralluoghi import (
    STATI_SOPRALLUOGO,
    Sopralluogo,
    delete_sopralluogo,
    list_for_segnalazione,
    load_sopralluoghi,
    next_sopralluogo_id,
    now_timestamp,
    upsert_sopralluogo,
    validate_sopralluogo,
)
from fascicoli import FascicoloWindow

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
DANGER = THEME["danger"]

LOG_FILE = resolve_path(PATHS["log_file"])
SEGNALAZIONI_PDF_DIR = resolve_path(PATHS["segnalazioni_pdf_dir"])
logger = setup_module_logger(__name__, LOG_FILE)


class SopralluoghiWindow(tk.Toplevel):
    def __init__(self, parent, segnalazione):
        super().__init__(parent)
        self.parent = parent
        self.segnalazione = segnalazione
        self._editing_id: int | None = None
        self._items: list[Sopralluogo] = []
        self._word_available: bool | None = None

        self.var_filter = tk.StringVar(value="Tutti")
        self.var_data = tk.StringVar()
        self.var_ora = tk.StringVar()
        self.var_operatori = tk.StringVar()
        self.var_luogo = tk.StringVar()
        self.var_stato = tk.StringVar(value=STATI_SOPRALLUOGO[0])
        self.var_foto = tk.BooleanVar(value=False)
        self.var_atti = tk.BooleanVar(value=False)
        self.var_ufficio = tk.StringVar()

        self.title(f"Sopralluoghi - Segnalazione n. {segnalazione.numero_progressivo}")
        self.configure(bg=BG)
        self.geometry("980x680")
        self.minsize(840, 560)
        self.transient(parent.winfo_toplevel())

        self._setup_styles()
        self._build_ui()
        self._load_items()
        self._start_new()

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Sopr.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=30,
            font=("Segoe UI", 10),
            bordercolor=BORDER,
        )
        style.configure(
            "Sopr.Treeview.Heading",
            background=BG2,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map("Sopr.Treeview", background=[("selected", "#FFE8C7")], foreground=[("selected", ACCENT_DARK)])

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        head = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        head.pack(fill="x")
        title_box = tk.Frame(head, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        tk.Label(
            title_box,
            text=f"Sopralluoghi - Segnalazione n. {self.segnalazione.numero_progressivo}",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text=self._segnalazione_summary(),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        tk.Button(
            head,
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

        body = tk.PanedWindow(shell, orient="horizontal", sashrelief="flat", bd=0, bg=BG, sashwidth=8)
        body.pack(fill="both", expand=True, pady=(12, 0))

        left = tk.Frame(body, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        right = tk.Frame(body, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        body.add(left, minsize=430, stretch="always")
        body.add(right, minsize=360, stretch="always")

        self._build_list_panel(left)
        self._build_form_panel(right)

    def _build_list_panel(self, parent):
        top = tk.Frame(parent, bg=SURFACE)
        top.pack(fill="x", padx=12, pady=(12, 8))
        tk.Label(top, text="Lista sopralluoghi", bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(side="left")

        filter_values = ("Tutti",) + STATI_SOPRALLUOGO
        filter_box = ttk.Combobox(top, textvariable=self.var_filter, values=filter_values, state="readonly", width=18)
        filter_box.pack(side="right")
        filter_box.bind("<<ComboboxSelected>>", lambda _e: self._refresh_tree())
        tk.Label(top, text="Stato", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side="right", padx=(0, 6))

        table_wrap = tk.Frame(parent, bg=SURFACE)
        table_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        vsb = ttk.Scrollbar(table_wrap, orient="vertical")
        vsb.pack(side="right", fill="y")

        self.tree = ttk.Treeview(
            table_wrap,
            columns=("data", "operatore", "stato", "esito"),
            show="headings",
            yscrollcommand=vsb.set,
            selectmode="browse",
            style="Sopr.Treeview",
        )
        for col, text, width in (
            ("data", "Data", 90),
            ("operatore", "Operatore", 130),
            ("stato", "Stato", 115),
            ("esito", "Esito sintetico", 190),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected_into_form())
        vsb.config(command=self.tree.yview)

        actions = tk.Frame(parent, bg=SURFACE)
        actions.pack(fill="x", padx=12, pady=(0, 12))
        self._button(actions, "Nuovo", ACCENT, self._start_new).pack(side="left")
        self._button(actions, "Modifica", "#355C7D", self._load_selected_into_form).pack(side="left", padx=(8, 0))
        self._button(actions, "Elimina", DANGER, self._delete_selected).pack(side="left", padx=(8, 0))
        self._button(actions, "Genera scheda sopralluogo", SUCCESS, self._export_selected_pdf).pack(side="left", padx=(8, 0))
        self._button(actions, "Foto sopr.", ACCENT, lambda: self._add_selected_attachment("foto")).pack(side="left", padx=(8, 0))
        self._button(actions, "Allegato sopr.", "#6A4C93", lambda: self._add_selected_attachment("allegato")).pack(
            side="left", padx=(8, 0)
        )
        self._button(actions, "Mostra allegati", BG2, self._show_fascicolo, fg=TEXT_MUTED).pack(side="left", padx=(8, 0))

    def _build_form_panel(self, parent):
        tk.Label(parent, text="Dettaglio sopralluogo", bg=SURFACE, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=12, pady=(12, 8)
        )
        form = tk.Frame(parent, bg=SURFACE)
        form.pack(fill="both", expand=True, padx=12)

        self._field(form, "Data sopralluogo", self.var_data, 0, "gg/mm/aaaa")
        self._field(form, "Ora", self.var_ora, 2, "HH:MM opzionale")
        self._field(form, "Operatore/i", self.var_operatori, 4)
        self._field(form, "Luogo", self.var_luogo, 6)

        tk.Label(form, text="Stato", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(
            row=8, column=0, sticky="w", pady=(8, 2)
        )
        ttk.Combobox(form, textvariable=self.var_stato, values=STATI_SOPRALLUOGO, state="readonly").grid(
            row=9, column=0, sticky="ew", pady=(0, 4)
        )

        self.txt_esito = self._text_field(form, "Esito", 10, 4)
        self.txt_note = self._text_field(form, "Note operative", 12, 5)

        checks = tk.Frame(form, bg=SURFACE)
        checks.grid(row=14, column=0, sticky="ew", pady=(8, 2))
        tk.Checkbutton(
            checks,
            text="Presenza foto/allegati",
            variable=self.var_foto,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE,
            selectcolor=SURFACE,
        ).pack(anchor="w")
        tk.Checkbutton(
            checks,
            text="Necessita ulteriori atti",
            variable=self.var_atti,
            bg=SURFACE,
            fg=TEXT,
            activebackground=SURFACE,
            selectcolor=SURFACE,
        ).pack(anchor="w")
        self._field(form, "Ufficio destinatario", self.var_ufficio, 15)

        footer = tk.Frame(parent, bg=SURFACE)
        footer.pack(fill="x", padx=12, pady=12)
        self._button(footer, "Salva sopralluogo", ACCENT, self._save_form).pack(side="left")
        self._button(footer, "Annulla", BG2, self._start_new, fg=TEXT_MUTED).pack(side="left", padx=(8, 0))

        form.columnconfigure(0, weight=1)

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

    def _field(self, parent, label, variable, row, placeholder=""):
        tk.Label(parent, text=label, bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=(8, 2)
        )
        entry = tk.Entry(parent, textvariable=variable, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10))
        entry.grid(row=row + 1, column=0, sticky="ew")
        if placeholder and not variable.get():
            entry.insert(0, "")

    def _text_field(self, parent, label, row, height):
        tk.Label(parent, text=label, bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=(8, 2)
        )
        text = tk.Text(parent, height=height, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10), wrap="word")
        text.grid(row=row + 1, column=0, sticky="nsew")
        return text

    def _load_items(self):
        try:
            self._items = list_for_segnalazione(self.segnalazione.numero_progressivo)
        except Exception:
            logger.exception("Errore lettura sopralluoghi segnalazione n. %s", self.segnalazione.numero_progressivo)
            messagebox.showerror("Errore lettura", "Impossibile leggere i sopralluoghi salvati.", parent=self)
            self._items = []
        self._refresh_tree()

    def _refresh_tree(self):
        selected_filter = self.var_filter.get()
        self.tree.delete(*self.tree.get_children())
        for item in self._items:
            if selected_filter != "Tutti" and item.stato != selected_filter:
                continue
            self.tree.insert(
                "",
                "end",
                iid=str(item.id_sopralluogo),
                values=(
                    item.data_sopralluogo or "-",
                    item.operatori or "-",
                    item.stato,
                    self._compact(item.esito or item.note_operative),
                ),
            )

    def _start_new(self):
        self._editing_id = None
        self.var_data.set("")
        self.var_ora.set("")
        self.var_operatori.set("")
        self.var_luogo.set(self.segnalazione.indirizzo or "")
        self.var_stato.set(STATI_SOPRALLUOGO[0])
        self.var_foto.set(False)
        self.var_atti.set(False)
        self.var_ufficio.set("")
        self._set_text(self.txt_esito, "")
        self._set_text(self.txt_note, "")

    def _load_selected_into_form(self):
        item = self._selected_item()
        if item is None:
            return
        self._editing_id = item.id_sopralluogo
        self.var_data.set(item.data_sopralluogo)
        self.var_ora.set(item.ora_sopralluogo)
        self.var_operatori.set(item.operatori)
        self.var_luogo.set(item.luogo)
        self.var_stato.set(item.stato)
        self.var_foto.set(item.presenza_foto_allegati)
        self.var_atti.set(item.ulteriori_atti)
        self.var_ufficio.set(item.ufficio_destinatario)
        self._set_text(self.txt_esito, item.esito)
        self._set_text(self.txt_note, item.note_operative)

    def _selected_item(self) -> Sopralluogo | None:
        selected = self.tree.selection()
        if not selected:
            return None
        try:
            selected_id = int(selected[0])
        except ValueError:
            return None
        for item in self._items:
            if item.id_sopralluogo == selected_id:
                return item
        return None

    def _save_form(self):
        now = now_timestamp()
        existing = self._find_current_edit()
        item = Sopralluogo(
            id_sopralluogo=existing.id_sopralluogo if existing else next_sopralluogo_id(load_sopralluoghi()),
            segnalazione_id=self.segnalazione.numero_progressivo,
            data_sopralluogo=self.var_data.get().strip(),
            ora_sopralluogo=self.var_ora.get().strip(),
            operatori=self.var_operatori.get().strip(),
            luogo=self.var_luogo.get().strip(),
            esito=self.txt_esito.get("1.0", "end").strip(),
            note_operative=self.txt_note.get("1.0", "end").strip(),
            presenza_foto_allegati=self.var_foto.get(),
            ulteriori_atti=self.var_atti.get(),
            ufficio_destinatario=self.var_ufficio.get().strip(),
            stato=self.var_stato.get().strip(),
            data_creazione=existing.data_creazione if existing else now,
            data_ultima_modifica=now,
        )
        valid, reason = validate_sopralluogo(item)
        if not valid:
            messagebox.showwarning("Dati non validi", reason, parent=self)
            return
        action = "update" if existing else "create"
        old_status = existing.stato if existing else ""
        try:
            upsert_sopralluogo(item)
        except Exception as exc:
            logger.exception("Errore salvataggio sopralluogo n. %s", item.id_sopralluogo)
            log_audit_event(
                "sopralluoghi",
                action,
                "sopralluogo",
                str(item.id_sopralluogo),
                "Salvataggio sopralluogo non riuscito",
                result="error",
                error=str(exc),
            )
            messagebox.showerror("Salvataggio non riuscito", f"Impossibile salvare il sopralluogo.\n\n{exc}", parent=self)
            return
        log_audit_event(
            "sopralluoghi",
            action,
            "sopralluogo",
            str(item.id_sopralluogo),
            "Creato sopralluogo" if action == "create" else "Modificato sopralluogo",
            extra={"segnalazione_id": item.segnalazione_id, "stato": item.stato},
        )
        if old_status and old_status != item.stato:
            log_audit_event(
                "sopralluoghi",
                "status_change",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Cambio stato sopralluogo",
                extra={"from": old_status, "to": item.stato},
            )
        self._load_items()
        self._editing_id = item.id_sopralluogo
        self.tree.selection_set(str(item.id_sopralluogo))
        self.tree.focus(str(item.id_sopralluogo))
        messagebox.showinfo("Sopralluogo salvato", "Il sopralluogo e stato salvato.", parent=self)

    def _find_current_edit(self) -> Sopralluogo | None:
        if self._editing_id is None:
            return None
        for item in self._items:
            if item.id_sopralluogo == self._editing_id:
                return item
        return None

    def _delete_selected(self):
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un sopralluogo da eliminare.", parent=self)
            return
        if not messagebox.askyesno("Conferma eliminazione", "Eliminare il sopralluogo selezionato?", parent=self):
            return
        try:
            delete_sopralluogo(item.id_sopralluogo)
        except Exception as exc:
            logger.exception("Errore eliminazione sopralluogo n. %s", item.id_sopralluogo)
            log_audit_event(
                "sopralluoghi",
                "delete",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Eliminazione sopralluogo non riuscita",
                result="error",
                error=str(exc),
            )
            messagebox.showerror("Eliminazione non riuscita", f"Impossibile eliminare il sopralluogo.\n\n{exc}", parent=self)
            return
        log_audit_event("sopralluoghi", "delete", "sopralluogo", str(item.id_sopralluogo), "Eliminato sopralluogo")
        self._load_items()
        self._start_new()

    def _add_selected_attachment(self, tipo: str):
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un sopralluogo.", parent=self)
            return
        if tipo == "foto":
            filetypes = [("Immagini", "*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp"), ("Tutti i file", "*.*")]
            title = "Aggiungi foto al sopralluogo"
        else:
            filetypes = [("Tutti i file", "*.*")]
            title = "Aggiungi allegato al sopralluogo"
        files = filedialog.askopenfilenames(parent=self, title=title, filetypes=filetypes)
        if not files:
            return
        added = 0
        for filename in files:
            try:
                add_attachment(
                    self.segnalazione,
                    Path(filename),
                    tipo,
                    origine="sopralluogo",
                    sopralluogo_id=item.id_sopralluogo,
                )
                added += 1
            except Exception:
                logger.exception("Errore aggiunta allegato sopralluogo: %s", filename)
                log_audit_event(
                    "sopralluoghi",
                    "add_attachment",
                    "sopralluogo",
                    str(item.id_sopralluogo),
                    "Aggiunta allegato/foto sopralluogo non riuscita",
                    result="error",
                )
        if added:
            item.presenza_foto_allegati = True
            try:
                upsert_sopralluogo(item)
            except Exception:
                logger.exception("Errore aggiornamento flag allegati sopralluogo n. %s", item.id_sopralluogo)
            self._load_items()
            log_audit_event(
                "sopralluoghi",
                "add_attachment",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Aggiunti allegati/foto al sopralluogo",
                extra={"count": added, "tipo": tipo},
            )
        messagebox.showinfo("Fascicolo aggiornato", f"File aggiunti: {added}", parent=self)

    def _show_fascicolo(self):
        FascicoloWindow(self, self.segnalazione)

    def _export_selected_pdf(self):
        item = self._selected_item()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un sopralluogo da esportare.", parent=self)
            return
        if not self._is_word_available():
            messagebox.showwarning(
                "Microsoft Word non disponibile",
                "Per generare la scheda PDF e necessario Microsoft Word Desktop installato su questo PC.",
                parent=self,
            )
            return
        try:
            SEGNALAZIONI_PDF_DIR.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        default_name = f"SOPRALLUOGO_{self.segnalazione.numero_progressivo}_{item.id_sopralluogo}.pdf"
        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Genera scheda sopralluogo",
            initialdir=str(SEGNALAZIONI_PDF_DIR),
            initialfile=default_name,
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not save_path:
            return
        try:
            self._render_pdf(item, Path(save_path))
        except Exception as exc:
            logger.exception("Errore generazione scheda sopralluogo n. %s", item.id_sopralluogo)
            log_audit_event(
                "sopralluoghi",
                "export_pdf",
                "sopralluogo",
                str(item.id_sopralluogo),
                "Generazione scheda sopralluogo non riuscita",
                result="error",
                error=str(exc),
            )
            messagebox.showerror("Generazione non riuscita", f"Impossibile creare il PDF.\n\n{exc}", parent=self)
            return
        try:
            add_attachment(
                self.segnalazione,
                Path(save_path),
                "scheda_sopralluogo",
                origine="sopralluogo",
                sopralluogo_id=item.id_sopralluogo,
            )
            item.presenza_foto_allegati = True
            upsert_sopralluogo(item)
            self._load_items()
        except Exception:
            logger.exception("Errore registrazione scheda sopralluogo n. %s nel fascicolo", item.id_sopralluogo)
        log_audit_event(
            "sopralluoghi",
            "export_pdf",
            "sopralluogo",
            str(item.id_sopralluogo),
            "Generata scheda sopralluogo",
        )
        messagebox.showinfo("PDF creato", f"Scheda sopralluogo esportata in:\n{save_path}", parent=self)

    def _render_pdf(self, item: Sopralluogo, output_pdf: Path):
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        payload = self._build_pdf_payload(item)
        ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)
$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param([object]$Selection, [string]$Text, [int]$Size = 9, [bool]$Bold = $false, [int]$Alignment = 0, [int]$SpaceAfter = 3)
    $Selection.ParagraphFormat.Alignment = $Alignment
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

function Add-Info {
    param([object]$Selection, [string]$Label, [string]$Value)
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = 9
    $Selection.Font.Bold = 1
    $Selection.TypeText($Label)
    $Selection.Font.Bold = 0
    $Selection.TypeText($Value)
    $Selection.TypeParagraph()
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Add()
    $sel = $word.Selection
    $pageSetup = $doc.PageSetup
    $pageSetup.TopMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.BottomMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.LeftMargin = $word.CentimetersToPoints(1.4)
    $pageSetup.RightMargin = $word.CentimetersToPoints(1.4)

    Add-Paragraph -Selection $sel -Text "COMUNE DI PEGOGNAGA" -Size 12 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "Polizia Locale" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text "SCHEDA SOPRALLUOGO" -Size 13 -Bold $true -Alignment 1 -SpaceAfter 8

    Add-Paragraph -Selection $sel -Text "Dati segnalazione" -Size 10 -Bold $true -SpaceAfter 2
    Add-Info -Selection $sel -Label "Segnalazione n.: " -Value $payload.segnalazione_numero
    Add-Info -Selection $sel -Label "Data ricezione: " -Value $payload.segnalazione_data
    Add-Info -Selection $sel -Label "Segnalante: " -Value $payload.segnalante
    Add-Info -Selection $sel -Label "Oggetto: " -Value $payload.descrizione
    Add-Paragraph -Selection $sel -Text "" -SpaceAfter 4

    Add-Paragraph -Selection $sel -Text "Dati sopralluogo" -Size 10 -Bold $true -SpaceAfter 2
    Add-Info -Selection $sel -Label "ID sopralluogo: " -Value $payload.id_sopralluogo
    Add-Info -Selection $sel -Label "Stato: " -Value $payload.stato
    Add-Info -Selection $sel -Label "Data/Ora: " -Value $payload.data_ora
    Add-Info -Selection $sel -Label "Luogo: " -Value $payload.luogo
    Add-Info -Selection $sel -Label "Operatore/i: " -Value $payload.operatori
    Add-Info -Selection $sel -Label "Esito: " -Value $payload.esito
    Add-Info -Selection $sel -Label "Note operative: " -Value $payload.note
    Add-Info -Selection $sel -Label "Foto/allegati: " -Value $payload.foto
    Add-Info -Selection $sel -Label "Ulteriori atti: " -Value $payload.atti
    Add-Info -Selection $sel -Label "Ufficio destinatario: " -Value $payload.ufficio

    $doc.ExportAsFixedFormat($PdfPath, 17)
    $doc.Close($false)
    $doc = $null
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
        with tempfile.TemporaryDirectory(prefix="passapp_sopr_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            payload_path = tmp_path / "payload.json"
            script_path = tmp_path / "scheda_sopralluogo.ps1"
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
                raise RuntimeError((result.stderr or result.stdout or "Errore sconosciuto").strip())
        if not output_pdf.exists():
            raise RuntimeError("Il file PDF non e stato creato.")

    def _build_pdf_payload(self, item: Sopralluogo) -> dict[str, str]:
        data_seg = "/".join(
            part for part in (self.segnalazione.giorno, self.segnalazione.mese, self.segnalazione.anno) if part
        )
        data_ora = item.data_sopralluogo
        if item.ora_sopralluogo:
            data_ora = f"{data_ora} - {item.ora_sopralluogo}"
        return {
            "segnalazione_numero": str(self.segnalazione.numero_progressivo),
            "segnalazione_data": self._value_or_dash(data_seg),
            "segnalante": self._value_or_dash(self.segnalazione.nominativo),
            "descrizione": self._value_or_dash(self.segnalazione.descrizione_segnalazione),
            "id_sopralluogo": str(item.id_sopralluogo),
            "stato": self._value_or_dash(item.stato),
            "data_ora": self._value_or_dash(data_ora),
            "luogo": self._value_or_dash(item.luogo),
            "operatori": self._value_or_dash(item.operatori),
            "esito": self._value_or_dash(item.esito),
            "note": self._value_or_dash(item.note_operative),
            "foto": "Si" if item.presenza_foto_allegati else "No",
            "atti": "Si" if item.ulteriori_atti else "No",
            "ufficio": self._value_or_dash(item.ufficio_destinatario),
        }

    def _is_word_available(self) -> bool:
        if self._word_available is None:
            self._word_available = check_office_com("Word.Application")[0]
        return self._word_available

    def _segnalazione_summary(self) -> str:
        data = "/".join(part for part in (self.segnalazione.giorno, self.segnalazione.mese, self.segnalazione.anno) if part)
        subject = self.segnalazione.nominativo or self.segnalazione.indirizzo or "Segnalazione"
        return f"{data or '-'} - {subject}"

    @staticmethod
    def _set_text(widget: tk.Text, value: str):
        widget.delete("1.0", "end")
        widget.insert("1.0", value or "")

    @staticmethod
    def _compact(value: str) -> str:
        text = re.sub(r"\s+", " ", value or "").strip()
        if not text:
            return "-"
        return text[:90] + "..." if len(text) > 90 else text

    @staticmethod
    def _value_or_dash(value: str) -> str:
        text = str(value or "").strip()
        return text if text else "-"
