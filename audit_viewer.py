from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app_config import load_config
from core.audit import read_audit_events

APP_CONFIG = load_config()
THEME = APP_CONFIG["ui"]["theme"]

BG = THEME["bg"]
BG2 = THEME["bg2"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = THEME["accent"]
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

        self._build_ui()
        self._load_events()

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        tk.Label(header, text="Storico modifiche", bg=SURFACE, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(
            side="left", padx=16, pady=12
        )
        tk.Button(
            header,
            text="Aggiorna",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=8,
            command=self._load_events,
        ).pack(side="right", padx=(0, 16), pady=12)

        filters = tk.Frame(shell, bg=BG)
        filters.pack(fill="x", pady=(10, 8))
        self.module_combo = ttk.Combobox(filters, textvariable=self.var_module, state="readonly", width=18)
        self.module_combo.pack(side="left")
        ttk.Combobox(filters, textvariable=self.var_result, state="readonly", values=("Tutti", "success", "error"), width=12).pack(
            side="left", padx=(8, 0)
        )
        tk.Entry(filters, textvariable=self.var_query, bg=SURFACE, fg=TEXT, relief="solid", bd=1, font=("Segoe UI", 10)).pack(
            side="left", fill="x", expand=True, padx=(8, 0), ipady=4
        )
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
        for event in self.events:
            if module_filter != "Tutti" and event.get("module") != module_filter:
                continue
            if result_filter != "Tutti" and event.get("result") != result_filter:
                continue
            haystack = " ".join(str(event.get(key, "")) for key in ("module", "action", "description", "entity_id")).lower()
            if query and query not in haystack:
                continue
            self.tree.insert(
                "",
                "end",
                values=(
                    event.get("timestamp", ""),
                    event.get("module", ""),
                    event.get("action", ""),
                    event.get("description", ""),
                    event.get("result", ""),
                ),
            )
