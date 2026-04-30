from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import load_config
from core.audit import read_audit_events
from ui_style import apply_ttk_style, create_primary_button

APP_CONFIG = load_config()
THEME = APP_CONFIG["ui"]["theme"]
AUDIT_UI = APP_CONFIG["ui"]["modules"]["audit"]

BG = THEME["bg"]
BG2 = THEME["bg2"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = AUDIT_UI["accent"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]


class AuditViewerWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Storico modifiche")
        self.configure(bg=BG)
        self.geometry("980x560")
        self.minsize(780, 420)
        self.transient(parent.winfo_toplevel())

        self.var_module = tk.StringVar(value="Tutti")
        self.var_result = tk.StringVar(value="Tutti")
        self.var_query = tk.StringVar()
        self.events: list[dict] = []

        apply_ttk_style(self, ACCENT)
        self._build_ui()
        self._load_events()

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        tk.Label(title_box, text="Storico modifiche", bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            title_box,
            text="Audit trail delle operazioni registrate.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))
        create_primary_button(header, "Aggiorna", self._load_events).pack(
            side="right", padx=(0, 16), pady=12
        )

        filters = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        filters.pack(fill="x", pady=(10, 8))
        tk.Label(filters, text="Modulo", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(
            side="left", padx=(12, 6)
        )
        self.module_combo = ttk.Combobox(filters, textvariable=self.var_module, state="readonly", width=18)
        self.module_combo.pack(side="left", pady=10)
        tk.Label(filters, text="Esito", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(
            side="left", padx=(10, 6)
        )
        ttk.Combobox(
            filters,
            textvariable=self.var_result,
            state="readonly",
            values=("Tutti", "success", "error"),
            width=12,
        ).pack(side="left", pady=10)
        tk.Entry(
            filters,
            textvariable=self.var_query,
            bg=SURFACE,
            fg=TEXT,
            relief="solid",
            bd=1,
            font=("Segoe UI", 10),
        ).pack(side="left", fill="x", expand=True, padx=(10, 12), ipady=5)
        self.var_module.trace_add("write", lambda *_: self._refresh())
        self.var_result.trace_add("write", lambda *_: self._refresh())
        self.var_query.trace_add("write", lambda *_: self._refresh())

        table_wrap = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        table_wrap.pack(fill="both", expand=True)
        vsb = ttk.Scrollbar(table_wrap, orient="vertical")
        vsb.pack(side="right", fill="y")
        self.tree = ttk.Treeview(
            table_wrap,
            columns=("timestamp", "module", "action", "description", "result"),
            show="headings",
            yscrollcommand=vsb.set,
        )
        for col, label, width in (
            ("timestamp", "Data/Ora", 150),
            ("module", "Modulo", 120),
            ("action", "Azione", 120),
            ("description", "Descrizione", 420),
            ("result", "Esito", 80),
        ):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.tag_configure("success", foreground="#198754")
        self.tree.tag_configure("warning", foreground="#D97706")
        self.tree.tag_configure("error", foreground="#B42318")
        self.tree.tag_configure("odd", background="#F9FAFB")
        vsb.config(command=self.tree.yview)

    def _load_events(self):
        self.events = list(reversed(read_audit_events(limit=2000)))
        modules = sorted({event.get("module", "") for event in self.events if event.get("module")})
        self.module_combo.configure(values=("Tutti",) + tuple(modules))
        self._refresh()

    def _refresh(self):
        module_filter = self.var_module.get()
        result_filter = self.var_result.get()
        query = self.var_query.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for index, event in enumerate(self.events):
            if module_filter != "Tutti" and event.get("module") != module_filter:
                continue
            if result_filter != "Tutti" and event.get("result") != result_filter:
                continue
            haystack = " ".join(
                str(event.get(key, ""))
                for key in ("module", "action", "description", "entity_id")
            ).lower()
            if query and query not in haystack:
                continue
            result = event.get("result", "")
            row_tags = [str(result or "success")]
            if index % 2:
                row_tags.append("odd")
            self.tree.insert(
                "",
                "end",
                values=(
                    event.get("timestamp", ""),
                    event.get("module", ""),
                    event.get("action", ""),
                    event.get("description", ""),
                    result,
                ),
                tags=tuple(row_tags),
            )
