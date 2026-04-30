from __future__ import annotations

import datetime as dt
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from app_config import load_config, resolve_path
from core.audit import log_audit_event
from core.logging_utils import setup_module_logger
from core.report_exporter import export_monthly_report_pdf, export_monthly_report_txt
from core.report_service import DEFAULT_MODULES, MONTH_NAMES, MonthlyReport, build_monthly_report

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
UI_CONFIG = APP_CONFIG["ui"]
THEME = UI_CONFIG["theme"]

BG = THEME["bg"]
BG2 = THEME["bg2"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = THEME["accent"]
ACCENT_DARK = THEME["accent_dark"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]
SUCCESS = THEME["success"]
DANGER = THEME["danger"]

LOG_FILE = resolve_path(PATHS["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)

MODULE_LABELS = {
    "pass_invalidi": "Pass Invalidi",
    "segnalazioni": "Segnalazioni",
    "ospitalita": "Ospitalita",
    "sopralluoghi": "Sopralluoghi",
}


class ReportMensileWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Report mensile")
        self.configure(bg=BG)
        self.geometry("920x680")
        self.minsize(760, 520)
        self.transient(parent.winfo_toplevel())

        today = dt.date.today()
        self.var_month = tk.StringVar(value=f"{today.month:02d} - {MONTH_NAMES[today.month]}")
        self.var_year = tk.StringVar(value=str(today.year))
        self.module_vars = {key: tk.BooleanVar(value=True) for key in DEFAULT_MODULES}
        self.status_var = tk.StringVar(value="Report non generato")
        self.current_report: MonthlyReport | None = None
        self._working = False

        self._build_ui()

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        tk.Label(title_box, text="Report mensile", bg=SURFACE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            title_box,
            text="Riepilogo attivita per mese e moduli selezionati.",
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

        controls = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        controls.pack(fill="x", pady=(12, 10))
        inner = tk.Frame(controls, bg=SURFACE)
        inner.pack(fill="x", padx=14, pady=12)

        tk.Label(inner, text="Mese", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        months = [f"{month:02d} - {name}" for month, name in MONTH_NAMES.items()]
        ttk.Combobox(inner, textvariable=self.var_month, values=months, state="readonly", width=18).grid(
            row=1, column=0, sticky="w", pady=(2, 0)
        )

        tk.Label(inner, text="Anno", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).grid(
            row=0, column=1, sticky="w", padx=(14, 0)
        )
        years = [str(year) for year in range(dt.date.today().year - 5, dt.date.today().year + 2)]
        ttk.Combobox(inner, textvariable=self.var_year, values=years, width=10).grid(
            row=1, column=1, sticky="w", padx=(14, 0), pady=(2, 0)
        )

        modules = tk.Frame(inner, bg=SURFACE)
        modules.grid(row=0, column=2, rowspan=2, sticky="w", padx=(20, 0))
        tk.Label(modules, text="Moduli", bg=SURFACE, fg=TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        checks = tk.Frame(modules, bg=SURFACE)
        checks.pack(anchor="w", pady=(3, 0))
        for key in DEFAULT_MODULES:
            tk.Checkbutton(
                checks,
                text=MODULE_LABELS[key],
                variable=self.module_vars[key],
                bg=SURFACE,
                fg=TEXT,
                activebackground=SURFACE,
                selectcolor=SURFACE,
            ).pack(side="left", padx=(0, 8))

        actions = tk.Frame(shell, bg=BG)
        actions.pack(fill="x", pady=(0, 10))
        self._button(actions, "Anteprima report", ACCENT, self.preview_report).pack(side="left")
        self._button(actions, "Esporta TXT", SUCCESS, self.export_txt).pack(side="left", padx=(8, 0))
        self.btn_export_pdf = self._button(actions, "Esporta PDF", DANGER, self.export_pdf)
        self.btn_export_pdf.pack(side="left", padx=(8, 0))
        tk.Label(actions, textvariable=self.status_var, bg=BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(12, 0))

        preview_wrap = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        preview_wrap.pack(fill="both", expand=True)
        self.preview = tk.Text(
            preview_wrap,
            bg=SURFACE,
            fg=TEXT,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
            padx=12,
            pady=12,
        )
        self.preview.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(preview_wrap, orient="vertical", command=self.preview.yview)
        vsb.pack(side="right", fill="y")
        self.preview.configure(yscrollcommand=vsb.set)

    def _button(self, parent, text, color, command):
        return tk.Button(
            parent,
            text=text,
            bg=color,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=14,
            pady=9,
            command=command,
        )

    def preview_report(self):
        if self._working:
            return
        month, year, modules = self._selection()
        if not modules:
            messagebox.showinfo("Moduli richiesti", "Seleziona almeno un modulo.", parent=self)
            return
        self._working = True
        self.status_var.set("Generazione anteprima in corso...")

        def worker():
            try:
                report = build_monthly_report(month, year, modules)
            except Exception as exc:
                detail = str(exc)
                self.after(0, lambda: self._generation_failed(detail))
                return
            self.after(0, lambda: self._set_report(report))

        threading.Thread(target=worker, daemon=True).start()

    def export_txt(self):
        if self.current_report is None:
            self.preview_report()
            messagebox.showinfo("Anteprima richiesta", "Genera prima l'anteprima, poi riesegui l'esportazione TXT.", parent=self)
            return
        try:
            path = export_monthly_report_txt(self.current_report)
        except Exception as exc:
            logger.exception("Errore esportazione TXT report mensile")
            log_audit_event("sistema", "export_report_txt", "report_mensile", None, "Esportazione TXT report mensile non riuscita", result="error", error=str(exc))
            messagebox.showerror("Esportazione non riuscita", f"Impossibile esportare il TXT.\n\n{exc}", parent=self)
            return
        log_audit_event(
            "sistema",
            "export_report_txt",
            "report_mensile",
            f"{self.current_report.year}-{self.current_report.month:02d}",
            "Esportato report mensile TXT",
        )
        self.status_var.set(f"TXT esportato: {path}")
        messagebox.showinfo("TXT esportato", f"Report salvato in:\n{path}", parent=self)

    def export_pdf(self):
        if self._working:
            return
        if self.current_report is None:
            self.preview_report()
            messagebox.showinfo("Anteprima richiesta", "Genera prima l'anteprima, poi riesegui l'esportazione PDF.", parent=self)
            return
        report = self.current_report
        self._working = True
        self.btn_export_pdf.config(state="disabled", text="PDF in corso...")
        self.status_var.set("Esportazione PDF in corso. Puoi lasciare aperta la finestra.")

        def worker():
            try:
                path = export_monthly_report_pdf(report)
            except Exception as exc:
                detail = str(exc)
                self.after(0, lambda: self._pdf_failed(detail))
                return
            self.after(0, lambda: self._pdf_done(path, report))

        threading.Thread(target=worker, daemon=True).start()

    def _selection(self) -> tuple[int, int, tuple[str, ...]]:
        month = int(self.var_month.get().split(" ", 1)[0])
        year = int(self.var_year.get().strip())
        modules = tuple(key for key, var in self.module_vars.items() if var.get())
        return month, year, modules

    def _set_report(self, report: MonthlyReport):
        self._working = False
        self.current_report = report
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", report.text)
        self.preview.configure(state="normal")
        self.status_var.set("Anteprima aggiornata")

    def _generation_failed(self, detail: str):
        self._working = False
        self.status_var.set("Errore generazione report")
        logger.error("Errore generazione report mensile: %s", detail)
        messagebox.showerror("Report non generato", f"Impossibile generare il report.\n\n{detail}", parent=self)

    def _pdf_done(self, path, report: MonthlyReport):
        self._working = False
        self.btn_export_pdf.config(state="normal", text="Esporta PDF")
        log_audit_event(
            "sistema",
            "export_report_pdf",
            "report_mensile",
            f"{report.year}-{report.month:02d}",
            "Esportato report mensile PDF",
        )
        self.status_var.set(f"PDF esportato: {path}")
        messagebox.showinfo("PDF esportato", f"Report salvato in:\n{path}", parent=self)

    def _pdf_failed(self, detail: str):
        self._working = False
        self.btn_export_pdf.config(state="normal", text="Esporta PDF")
        logger.error("Errore esportazione PDF report mensile: %s", detail)
        log_audit_event(
            "sistema",
            "export_report_pdf",
            "report_mensile",
            None,
            "Esportazione PDF report mensile non riuscita",
            result="error",
            error=detail,
        )
        self.status_var.set("Esportazione PDF non riuscita")
        messagebox.showerror("Esportazione non riuscita", f"Impossibile esportare il PDF.\n\n{detail}", parent=self)
