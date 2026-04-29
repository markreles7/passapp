import threading
import tkinter as tk
from tkinter import ttk

from app_config import load_config
from audit_viewer import AuditViewerWindow
from core.audit import log_audit_event
from core.dashboard_service import ERROR as DASHBOARD_ERROR
from core.dashboard_service import OK as DASHBOARD_OK
from core.dashboard_service import WARNING as DASHBOARD_WARNING
from core.dashboard_service import collect_dashboard_snapshot
from core.diagnostics import ERROR, OK, WARNING, run_diagnostics
from contatti_utili import ContattiUtiliWindow
from ospitalita_stranieri import OspitalitaStranieriFrame
from pass_invalidi import PassInvalidiFrame
from report_mensile import ReportMensileWindow
from segnalazioni import SegnalazioniFrame

APP_CONFIG = load_config()
UI_CONFIG = APP_CONFIG["ui"]
THEME = UI_CONFIG["theme"]
MODULES = UI_CONFIG["modules"]
WINDOW = UI_CONFIG["window"]

BG = THEME["bg"]
SURFACE = THEME["surface"]
BORDER = THEME["border"]
ACCENT = THEME["accent"]
ACCENT_DARK = THEME["accent_dark"]
SUCCESS = THEME["success"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]


class MainMenuFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.dashboard_cards = {}
        self.dashboard_status_var = tk.StringVar(value="Dashboard non aggiornata")
        self._dashboard_loading = False
        self._build_ui()

    def on_show(self):
        self.controller.title(UI_CONFIG["main_title"])

    def _build_ui(self):
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True, padx=24, pady=18)

        header = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")

        title_wrap = tk.Frame(header, bg=SURFACE)
        title_wrap.pack(fill="x", padx=24, pady=16)

        badge = tk.Label(
            title_wrap,
            text="SU",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 16, "bold"),
            width=2,
            padx=6,
            pady=4,
        )
        badge.pack(side="left", padx=(0, 12))

        title_box = tk.Frame(title_wrap, bg=SURFACE)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text=UI_CONFIG["dashboard_title"],
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text=UI_CONFIG["dashboard_subtitle"],
            bg=SURFACE,
            fg=ACCENT,
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(2, 0))

        tk.Label(
            title_box,
            text=UI_CONFIG["dashboard_description"],
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(6, 0))

        actions = tk.Frame(title_wrap, bg=SURFACE)
        actions.pack(side="right", padx=(12, 0))

        tk.Button(
            actions,
            text="Aggiorna dashboard",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=14,
            pady=9,
            command=self.refresh_dashboard,
        ).pack(side="left")

        tk.Button(
            actions,
            text="Report mensile",
            bg=SUCCESS,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT_DARK,
            padx=14,
            pady=9,
            command=self._show_monthly_report,
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            actions,
            text="Contatti utili",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            padx=14,
            pady=9,
            command=self._show_contacts,
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            actions,
            text="Verifica configurazione",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            padx=14,
            pady=9,
            command=self._show_diagnostics,
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            actions,
            text="Storico modifiche",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=BORDER,
            padx=14,
            pady=9,
            command=self._show_audit_viewer,
        ).pack(side="left", padx=(10, 0))

        cards = tk.Frame(shell, bg=BG)
        cards.pack(fill="both", expand=True, pady=(14, 0))

        self._module_card(cards, MODULES["pass_invalidi"], "PassInvalidiFrame", "pass_invalidi")
        self._module_card(cards, MODULES["segnalazioni"], "SegnalazioniFrame", "segnalazioni")
        self._module_card(cards, MODULES["ospitalita"], "OspitalitaStranieriFrame", "ospitalita")

        tk.Label(
            shell,
            textvariable=self.dashboard_status_var,
            bg=BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(8, 0))

        self.refresh_dashboard()

    def _module_card(self, parent, config, frame_name, dashboard_key):
        card = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x", pady=8)

        inner = tk.Frame(card, bg=SURFACE)
        inner.pack(fill="x", padx=22, pady=16)

        top = tk.Frame(inner, bg=SURFACE)
        top.pack(fill="x")
        tk.Label(
            top,
            text=config["icon"],
            bg=config["accent"],
            fg="white",
            font=("Segoe UI", 12, "bold"),
            width=2,
            padx=4,
            pady=3,
        ).pack(side="left", padx=(0, 10))

        tk.Label(
            top,
            text=config["menu_title"],
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(side="left")

        tk.Label(
            inner,
            text=config["menu_description"],
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(8, 12))

        body = tk.Frame(inner, bg=SURFACE)
        body.pack(fill="x")

        metrics_frame = tk.Frame(body, bg=SURFACE)
        metrics_frame.pack(side="left", fill="x", expand=True)

        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(
            inner,
            textvariable=detail_var,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
            wraplength=760,
            justify="left",
        )
        detail_label.pack(anchor="w", pady=(10, 0))

        tk.Button(
            body,
            text="Apri Modulo",
            bg=config["accent"],
            fg="white",
            font=("Segoe UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=config["accent_dark"],
            padx=18,
            pady=10,
            command=lambda: self.controller.show_frame(frame_name),
        ).pack(side="right", anchor="n", padx=(18, 0))

        self.dashboard_cards[dashboard_key] = {
            "metrics_frame": metrics_frame,
            "detail_var": detail_var,
        }
        self._render_card_metrics(dashboard_key, (("Stato", "Caricamento..."),), "")

    def refresh_dashboard(self):
        if self._dashboard_loading:
            return
        self._dashboard_loading = True
        self.dashboard_status_var.set("Aggiornamento dashboard in corso...")
        for key in self.dashboard_cards:
            self._render_card_metrics(key, (("Stato", "Caricamento..."),), "")

        def worker():
            try:
                snapshot = collect_dashboard_snapshot()
            except Exception as exc:
                detail = str(exc)
                self.after(0, lambda: self._dashboard_failed(detail))
                return
            self.after(0, lambda: self._apply_dashboard_snapshot(snapshot))

        threading.Thread(target=worker, daemon=True).start()

    def _apply_dashboard_snapshot(self, snapshot):
        self._dashboard_loading = False
        for key, card in snapshot.cards.items():
            detail = card.detail
            if detail:
                detail = f"{card.status}: {detail}"
            else:
                detail = card.status
            self._render_card_metrics(key, card.metrics, detail)
        updated_at = snapshot.updated_at.strftime("%d/%m/%Y %H:%M:%S")
        self.dashboard_status_var.set(f"Ultimo aggiornamento dashboard: {updated_at}")

    def _dashboard_failed(self, detail):
        self._dashboard_loading = False
        self.dashboard_status_var.set("Errore aggiornamento dashboard.")
        for key in self.dashboard_cards:
            self._render_card_metrics(key, (("Stato", "Errore lettura"),), detail)

    def _render_card_metrics(self, key, metrics, detail):
        card_state = self.dashboard_cards.get(key)
        if not card_state:
            return
        metrics_frame = card_state["metrics_frame"]
        for child in metrics_frame.winfo_children():
            child.destroy()
        for label, value in metrics:
            row = tk.Frame(metrics_frame, bg=SURFACE)
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=f"{label}:",
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=("Segoe UI", 10),
                width=22,
                anchor="w",
            ).pack(side="left")
            tk.Label(
                row,
                text=str(value),
                bg=SURFACE,
                fg=self._metric_color(value),
                font=("Segoe UI", 10, "bold"),
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(side="left", fill="x", expand=True)
        card_state["detail_var"].set(detail)

    @staticmethod
    def _metric_color(value):
        text = str(value)
        if text.startswith(DASHBOARD_ERROR) or text == "Errore lettura":
            return "#B3261E"
        if text.startswith(DASHBOARD_WARNING):
            return "#9A5E0C"
        if text.startswith(DASHBOARD_OK):
            return "#1E7A4D"
        return TEXT

    def _show_diagnostics(self):
        log_audit_event("sistema", "diagnostics", "system", None, "Diagnostica configurazione eseguita")
        win = tk.Toplevel(self)
        win.title("Verifica configurazione")
        win.configure(bg=BG)
        win.geometry("860x480")
        win.minsize(720, 360)
        win.transient(self.winfo_toplevel())

        wrap = tk.Frame(win, bg=BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=16)

        tk.Label(
            wrap,
            text="Verifica configurazione",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")

        tree_frame = tk.Frame(wrap, bg=BG)
        tree_frame.pack(fill="both", expand=True, pady=(12, 10))

        tree = ttk.Treeview(tree_frame, columns=("status", "check", "detail"), show="headings", height=14)
        tree.heading("status", text="Esito")
        tree.heading("check", text="Controllo")
        tree.heading("detail", text="Dettaglio")
        tree.column("status", width=110, anchor="center", stretch=False)
        tree.column("check", width=210, anchor="w", stretch=False)
        tree.column("detail", width=500, anchor="w")
        tree.tag_configure(OK, foreground="#1E7A4D")
        tree.tag_configure(WARNING, foreground="#9A5E0C")
        tree.tag_configure(ERROR, foreground="#B3261E")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for item in run_diagnostics():
            tree.insert("", "end", values=(item.status, item.name, item.detail), tags=(item.status,))

        tk.Button(
            wrap,
            text="Chiudi",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=ACCENT,
            padx=18,
            pady=8,
            command=win.destroy,
        ).pack(anchor="e")

    def _show_monthly_report(self):
        ReportMensileWindow(self)

    def _show_audit_viewer(self):
        AuditViewerWindow(self)

    def _show_contacts(self):
        ContattiUtiliWindow(self)


class DesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(UI_CONFIG["main_title"])
        self.geometry(f"{WINDOW['width']}x{WINDOW['height']}")
        self.minsize(WINDOW["min_width"], WINDOW["min_height"])
        self.configure(bg=BG)

        self.screen_host = tk.Frame(self, bg=BG)
        self.screen_host.pack(fill="both", expand=True)

        self.frame_classes = {
            "MainMenuFrame": MainMenuFrame,
            "PassInvalidiFrame": PassInvalidiFrame,
            "SegnalazioniFrame": SegnalazioniFrame,
            "OspitalitaStranieriFrame": OspitalitaStranieriFrame,
        }
        self.frames = {}
        self.show_frame("MainMenuFrame")

    def show_frame(self, frame_name):
        if frame_name not in self.frames:
            frame_class = self.frame_classes[frame_name]
            if frame_name == "PassInvalidiFrame":
                self.frames[frame_name] = frame_class(self.screen_host, self, show_back_button=True)
            else:
                self.frames[frame_name] = frame_class(self.screen_host, self)
        target = self.frames[frame_name]
        for frame in self.frames.values():
            frame.pack_forget()
        target.pack(fill="both", expand=True)
        if hasattr(target, "on_show"):
            target.on_show()


def main():
    app = DesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
