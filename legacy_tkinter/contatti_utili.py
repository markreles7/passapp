from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import webbrowser

from app_config import load_config, resolve_path
from core.audit import log_audit_event
from core.contatti import (
    CONTATTI_CATEGORIE,
    Contatto,
    available_tags,
    delete_contatto,
    export_contatti_csv,
    export_contatti_txt,
    filter_contatti,
    load_contatti,
    upsert_contatto,
    validate_contatto,
)
from core.logging_utils import setup_module_logger
from ui_motion import debounce

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
THEME = APP_CONFIG["ui"]["theme"]
CONTATTI_UI = APP_CONFIG["ui"]["modules"]["contatti"]

BG = THEME["bg"]
BG2 = THEME["bg2"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = CONTATTI_UI["accent"]
ACCENT_DARK = CONTATTI_UI["accent_dark"]
SUCCESS = THEME["success"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]
DANGER = THEME["danger"]

LOG_FILE = resolve_path(PATHS["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)


class ContattiUtiliFrame(tk.Frame):
    def __init__(self, parent, controller=None, show_close_button=False, close_command=None):
        super().__init__(parent)
        self.controller = controller
        self.show_close_button = show_close_button
        self.close_command = close_command
        self.configure(bg=BG)

        self.contatti: list[Contatto] = []
        self.selected_id: str | None = None
        self.var_search = tk.StringVar()
        self.var_filter_categoria = tk.StringVar(value="Tutte")
        self.var_filter_tag = tk.StringVar(value="Tutti")
        self.status_var = tk.StringVar()
        self.form_vars = {
            "nome": tk.StringVar(),
            "categoria": tk.StringVar(value="Altro"),
            "referente": tk.StringVar(),
            "telefono": tk.StringVar(),
            "cellulare": tk.StringVar(),
            "email": tk.StringVar(),
            "pec": tk.StringVar(),
            "indirizzo": tk.StringVar(),
            "orari": tk.StringVar(),
            "tags": tk.StringVar(),
            "fonte": tk.StringVar(),
        }

        self._debounced_refresh_tree = debounce(self, 250, self._refresh_tree)
        self.var_search.trace_add("write", self._debounced_refresh_tree)
        self.var_filter_categoria.trace_add("write", self._debounced_refresh_tree)
        self.var_filter_tag.trace_add("write", self._debounced_refresh_tree)

        self._setup_styles()
        self._build_ui()
        self._load()

    def on_show(self):
        if self.controller is not None:
            self.controller.title("Contatti utili - Polizia Locale")

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Contatti.Treeview",
            background=SURFACE,
            fieldbackground=SURFACE,
            foreground=TEXT,
            rowheight=30,
            font=("Segoe UI", 10),
            bordercolor=BORDER,
        )
        style.configure(
            "Contatti.Treeview.Heading",
            background=BG2,
            foreground=TEXT_MUTED,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
        )
        style.map("Contatti.Treeview", background=[("selected", "#DDEBFF")], foreground=[("selected", TEXT)])

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        tk.Label(title_box, text="Contatti utili / Uffici", bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            title_box,
            text="Rubrica operativa per uffici, enti e riferimenti comunali.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))
        if self.show_close_button:
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
                command=self.close_command or self.destroy,
            ).pack(side="right", padx=16, pady=12)

        split = tk.PanedWindow(shell, orient="horizontal", sashrelief="flat", bd=0, bg=BG, sashwidth=8)
        split.pack(fill="both", expand=True, pady=(12, 0))
        left = tk.Frame(split, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        right = tk.Frame(split, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        split.add(left, minsize=560, stretch="always")
        split.add(right, minsize=340, stretch="always")

        self._build_list_panel(left)
        self._build_form_panel(right)

    def _build_list_panel(self, parent):
        filters = tk.Frame(parent, bg=SURFACE)
        filters.pack(fill="x", padx=12, pady=(12, 8))
        tk.Entry(filters, textvariable=self.var_search, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, ipady=5
        )
        ttk.Combobox(
            filters,
            textvariable=self.var_filter_categoria,
            values=("Tutte",) + CONTATTI_CATEGORIE,
            state="readonly",
            width=22,
        ).pack(side="left", padx=(8, 0))
        self.cbo_tag = ttk.Combobox(
            filters,
            textvariable=self.var_filter_tag,
            values=("Tutti",),
            state="readonly",
            width=22,
        )
        self.cbo_tag.pack(side="left", padx=(8, 0))

        table_wrap = tk.Frame(parent, bg=SURFACE)
        table_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        vsb = ttk.Scrollbar(table_wrap, orient="vertical")
        vsb.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            table_wrap,
            columns=("nome", "categoria", "telefono", "email", "pec", "indirizzo"),
            show="headings",
            yscrollcommand=vsb.set,
            selectmode="browse",
            style="Contatti.Treeview",
        )
        for col, label, width in (
            ("nome", "Nome", 190),
            ("categoria", "Categoria", 130),
            ("telefono", "Telefono", 105),
            ("email", "Email", 145),
            ("pec", "PEC", 145),
            ("indirizzo", "Indirizzo", 190),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_selected())
        vsb.config(command=self.tree.yview)

        actions = tk.Frame(parent, bg=SURFACE)
        actions.pack(fill="x", padx=12, pady=(0, 12))
        self._button(actions, "Nuovo", ACCENT, self._new_contact).pack(side="left")
        self._button(actions, "Modifica", "#355C7D", self._load_selected).pack(side="left", padx=(6, 0))
        self._button(actions, "Elimina", DANGER, self._delete_selected).pack(side="left", padx=(6, 0))
        self._button(actions, "Copia telefono", BG2, lambda: self._copy_field("telefono"), fg=TEXT_MUTED).pack(side="left", padx=(6, 0))
        self._button(actions, "Copia email", BG2, lambda: self._copy_field("email"), fg=TEXT_MUTED).pack(side="left", padx=(6, 0))
        self._button(actions, "Copia PEC", BG2, lambda: self._copy_field("pec"), fg=TEXT_MUTED).pack(side="left", padx=(6, 0))
        self._button(actions, "Esporta TXT", SUCCESS, lambda: self._export_contacts(".txt")).pack(side="left", padx=(6, 0))
        self._button(actions, "Esporta CSV", SUCCESS, lambda: self._export_contacts(".csv")).pack(side="left", padx=(6, 0))
        tk.Label(parent, textvariable=self.status_var, bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", padx=12, pady=(0, 8)
        )

    def _build_form_panel(self, parent):
        tk.Label(parent, text="Scheda contatto", bg=SURFACE, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", padx=12, pady=(12, 8)
        )
        form = tk.Frame(parent, bg=SURFACE)
        form.pack(fill="both", expand=True, padx=12)

        self._entry(form, "Nome ente/ufficio/ditta", self.form_vars["nome"])
        self._combo(form, "Categoria", self.form_vars["categoria"], CONTATTI_CATEGORIE)
        self._entry(form, "Referente", self.form_vars["referente"])
        self._entry(form, "Telefono", self.form_vars["telefono"])
        self._entry(form, "Cellulare", self.form_vars["cellulare"])
        self._entry(form, "Email", self.form_vars["email"])
        self._entry(form, "PEC", self.form_vars["pec"])
        self._entry(form, "Indirizzo", self.form_vars["indirizzo"])
        self._entry(form, "Orari", self.form_vars["orari"])
        self._entry(form, "Tags", self.form_vars["tags"])
        self._entry(form, "Fonte", self.form_vars["fonte"])
        tk.Label(form, text="Note", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(8, 2))
        self.txt_note = tk.Text(form, height=5, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10), wrap="word")
        self.txt_note.pack(fill="x")

        footer = tk.Frame(parent, bg=SURFACE)
        footer.pack(fill="x", padx=12, pady=12)
        self._button(footer, "Salva", ACCENT, self._save_form).pack(side="left")
        self._button(footer, "Apri email", SUCCESS, self._open_email).pack(side="left", padx=(8, 0))
        self._button(footer, "Annulla", BG2, self._new_contact, fg=TEXT_MUTED).pack(side="left", padx=(8, 0))

    def _entry(self, parent, label, variable):
        tk.Label(parent, text=label, bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
        tk.Entry(parent, textvariable=variable, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10)).pack(fill="x", ipady=4)

    def _combo(self, parent, label, variable, values):
        tk.Label(parent, text=label, bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
        ttk.Combobox(parent, textvariable=variable, values=values, state="readonly").pack(fill="x")

    def _button(self, parent, text, color, command, fg="white"):
        return tk.Button(
            parent,
            text=text,
            bg=color,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=10,
            pady=7,
            command=command,
        )

    def _load(self):
        self.contatti, warning = load_contatti()
        if warning:
            if warning.startswith("Importati "):
                log_audit_event("contatti", "seed", "contatti", None, warning)
                self.status_var.set(warning)
            else:
                logger.warning(warning)
                messagebox.showwarning("Archivio contatti", warning, parent=self)
        self.cbo_tag.config(values=("Tutti",) + available_tags(self.contatti))
        self._refresh_tree()
        self._new_contact()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for item in filter_contatti(self.contatti, self.var_search.get(), self.var_filter_categoria.get(), self.var_filter_tag.get()):
            self.tree.insert(
                "",
                "end",
                iid=str(item.id),
                values=(item.nome, item.categoria, item.telefono, item.email, item.pec, item.indirizzo),
            )
        self.status_var.set(f"Contatti visualizzati: {len(self.tree.get_children())}")

    def _new_contact(self):
        self.selected_id = None
        for key, var in self.form_vars.items():
            var.set("Altro" if key == "categoria" else "")
        self.txt_note.delete("1.0", "end")

    def _selected_contact(self) -> Contatto | None:
        selected = self.tree.selection()
        if not selected:
            return None
        selected_id = selected[0]
        for item in self.contatti:
            if item.id == selected_id:
                return item
        return None

    def _load_selected(self):
        item = self._selected_contact()
        if item is None:
            return
        self.selected_id = item.id
        self.form_vars["nome"].set(item.nome)
        self.form_vars["categoria"].set(item.categoria)
        self.form_vars["referente"].set(item.referente)
        self.form_vars["telefono"].set(item.telefono)
        self.form_vars["cellulare"].set(item.cellulare)
        self.form_vars["email"].set(item.email)
        self.form_vars["pec"].set(item.pec)
        self.form_vars["indirizzo"].set(item.indirizzo)
        self.form_vars["orari"].set(item.orari)
        self.form_vars["tags"].set(", ".join(item.tags or []))
        self.form_vars["fonte"].set(item.fonte)
        self.txt_note.delete("1.0", "end")
        self.txt_note.insert("1.0", item.note)

    def _save_form(self):
        item = Contatto(
            id=self.selected_id or 0,
            nome=self.form_vars["nome"].get().strip(),
            categoria=self.form_vars["categoria"].get().strip() or "Altro",
            referente=self.form_vars["referente"].get().strip(),
            telefono=self.form_vars["telefono"].get().strip(),
            cellulare=self.form_vars["cellulare"].get().strip(),
            email=self.form_vars["email"].get().strip(),
            pec=self.form_vars["pec"].get().strip(),
            indirizzo=self.form_vars["indirizzo"].get().strip(),
            orari=self.form_vars["orari"].get().strip(),
            note=self.txt_note.get("1.0", "end").strip(),
            tags=[item.strip() for item in self.form_vars["tags"].get().split(",") if item.strip()],
            fonte=self.form_vars["fonte"].get().strip(),
        )
        valid, warning, soft_warning = validate_contatto(item)
        if not valid:
            messagebox.showwarning("Dati non validi", warning, parent=self)
            return
        if soft_warning and not messagebox.askyesno("Recapiti mancanti", f"{warning}\n\nSalvare comunque?", parent=self):
            return
        action = "update" if item.id else "create"
        try:
            saved = upsert_contatto(item)
        except Exception as exc:
            logger.exception("Errore salvataggio contatto")
            messagebox.showerror("Salvataggio non riuscito", f"Impossibile salvare il contatto.\n\n{exc}", parent=self)
            return
        log_audit_event("contatti", action, "contatto", str(saved.id), "Creato contatto" if action == "create" else "Modificato contatto")
        self._load()
        if self.tree.exists(str(saved.id)):
            self.tree.selection_set(str(saved.id))
            self.tree.focus(str(saved.id))

    def _delete_selected(self):
        item = self._selected_contact()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un contatto da eliminare.", parent=self)
            return
        if not messagebox.askyesno("Conferma eliminazione", f"Eliminare il contatto '{item.nome}'?", parent=self):
            return
        if delete_contatto(item.id):
            log_audit_event("contatti", "delete", "contatto", str(item.id), "Eliminato contatto")
        self._load()

    def _copy_field(self, field: str):
        item = self._selected_contact()
        if item is None:
            messagebox.showinfo("Selezione richiesta", "Seleziona un contatto.", parent=self)
            return
        value = getattr(item, field, "")
        if not value:
            messagebox.showinfo("Dato mancante", f"Il campo {field} e vuoto.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        self.status_var.set(f"{field} copiato negli appunti")

    def _open_email(self):
        email = self.form_vars["email"].get().strip() or self.form_vars["pec"].get().strip()
        if not email:
            messagebox.showinfo("Email mancante", "Inserisci o seleziona un indirizzo email/PEC.", parent=self)
            return
        webbrowser.open(f"mailto:{email}")

    def _export_contacts(self, extension: str):
        if not self.contatti:
            messagebox.showinfo("Nessun dato", "Non ci sono contatti da esportare.", parent=self)
            return
        default_dir = resolve_path("documenti")
        default_dir.mkdir(parents=True, exist_ok=True)
        filetypes = [("TXT", "*.txt")] if extension == ".txt" else [("CSV", "*.csv")]
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Esporta contatti",
            initialdir=str(default_dir),
            initialfile=f"contatti_utili{extension}",
            defaultextension=extension,
            filetypes=filetypes,
        )
        if not path:
            return
        out_path = Path(path)
        try:
            if out_path.suffix.lower() == ".txt":
                export_contatti_txt(self.contatti, out_path)
            else:
                export_contatti_csv(self.contatti, out_path)
        except Exception as exc:
            logger.exception("Errore esportazione contatti")
            messagebox.showerror("Esportazione non riuscita", f"Impossibile esportare i contatti.\n\n{exc}", parent=self)
            return
        log_audit_event("contatti", "export", "contatti", None, "Esportata lista contatti", extra={"format": out_path.suffix.lower()})
        if os.name == "nt":
            try:
                os.startfile(out_path)  # type: ignore[attr-defined]
            except OSError:
                pass
        messagebox.showinfo("Esportazione completata", f"Contatti esportati in:\n{out_path}", parent=self)


class ContattiUtiliWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Contatti utili")
        self.configure(bg=BG)
        self.geometry("1120x680")
        self.minsize(900, 520)
        self.transient(parent.winfo_toplevel())
        frame = ContattiUtiliFrame(self, show_close_button=True, close_command=self.destroy)
        frame.pack(fill="both", expand=True)
