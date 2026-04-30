import re
import tkinter as tk
from tkinter import messagebox, ttk

from app_config import load_config
from audit_viewer import AuditViewerWindow
from config_setup import ConfigurazioneInizialeFrame
from core.audit import log_audit_event
from core.dashboard_service import ERROR as DASHBOARD_ERROR
from core.dashboard_service import OK as DASHBOARD_OK
from core.dashboard_service import WARNING as DASHBOARD_WARNING
from core.dashboard_service import collect_dashboard_snapshot
from core.diagnostics import ERROR, OK, WARNING as DIAGNOSTIC_WARNING, run_diagnostics
from contatti_utili import ContattiUtiliFrame
from ospitalita_stranieri import OspitalitaStranieriFrame
from pass_invalidi import PassInvalidiFrame
from report_mensile import ReportMensileWindow
from segnalazioni import SegnalazioniFrame
from sopralluoghi import SopralluoghiOverviewFrame
from ui_style import (
    APP_BG,
    CARD_BG,
    CARD_BORDER,
    PRIMARY,
    SECONDARY,
    SIDEBAR_ACTIVE,
    SIDEBAR_BG,
    TEXT_DIM,
    apply_ttk_style,
    create_card,
    create_primary_button,
    create_sidebar,
    create_stat_box,
    create_status_badge,
    set_sidebar_collapsed,
)
from ui_motion import (
    hide_loading_feedback,
    run_background_task,
    set_busy_state,
    show_loading_feedback,
)

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
WARNING = THEME["warning"]
DANGER = THEME["danger"]
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]

SIDEBAR_ITEMS = (
    {"key": "MainMenuFrame", "label": "Dashboard", "icon": "SU"},
    {"key": "PassInvalidiFrame", "label": "Pass Invalidi", "icon": "PI"},
    {"key": "SegnalazioniFrame", "label": "Segnalazioni", "icon": "SC"},
    {"key": "Sopralluoghi", "label": "Sopralluoghi", "icon": "SP"},
    {"key": "OspitalitaStranieriFrame", "label": "Ospitalita", "icon": "OS"},
    {"key": "Report", "label": "Report mensile", "icon": "RM"},
    {"key": "Contatti", "label": "Contatti utili", "icon": "CT"},
    {"key": "ConfigurazioneInizialeFrame", "label": "Configurazione", "icon": "CF"},
    {"key": "Diagnostics", "label": "Verifica configurazione", "icon": "VC"},
    {"key": "Audit", "label": "Storico modifiche", "icon": "AU"},
)

GEOMETRY_RE = re.compile(
    r"^(?P<width>\d+)x(?P<height>\d+)(?P<x>[+-]\d+)?(?P<y>[+-]\d+)?$"
)


def _parse_geometry(value):
    if not isinstance(value, str):
        return None
    match = GEOMETRY_RE.match(value.strip())
    if not match:
        return None
    width = int(match.group("width"))
    height = int(match.group("height"))
    x_value = match.group("x")
    y_value = match.group("y")
    x_pos = int(x_value) if x_value is not None else None
    y_pos = int(y_value) if y_value is not None else None
    return width, height, x_pos, y_pos


def _geometry_fits_screen(
    width,
    height,
    x_pos,
    y_pos,
    max_width,
    max_height,
    screen_width,
    screen_height,
):
    if width <= 0 or height <= 0 or width > max_width or height > max_height:
        return False
    if x_pos is None or y_pos is None:
        return True
    return (
        x_pos >= 0
        and y_pos >= 0
        and x_pos + width <= screen_width
        and y_pos + height <= screen_height
    )


def apply_responsive_geometry(root):
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    max_width = max(1, int(screen_width * 0.94))
    max_height = max(1, int(screen_height * 0.92))

    if screen_width > 1920 or screen_height > 1080:
        preferred_width = max(WINDOW["width"], 1440)
        preferred_height = max(WINDOW["height"], 900)
    else:
        preferred_width = WINDOW["width"]
        preferred_height = WINDOW["height"]

    width = min(preferred_width, max_width)
    height = min(preferred_height, max_height)
    x_pos = (screen_width - width) // 2
    y_pos = (screen_height - height) // 2

    saved_geometry = WINDOW.get("saved_geometry") or WINDOW.get("geometry")
    parsed_geometry = _parse_geometry(saved_geometry)
    if parsed_geometry:
        saved_width, saved_height, saved_x, saved_y = parsed_geometry
        min_saved_width = min(WINDOW["min_width"], max_width)
        min_saved_height = min(WINDOW["min_height"], max_height)
        saved_geometry_is_valid = (
            saved_width >= min_saved_width
            and saved_height >= min_saved_height
            and _geometry_fits_screen(
                saved_width,
                saved_height,
                saved_x,
                saved_y,
                max_width,
                max_height,
                screen_width,
                screen_height,
            )
        )
        if saved_geometry_is_valid:
            width = saved_width
            height = saved_height
            x_pos = saved_x if saved_x is not None else (screen_width - width) // 2
            y_pos = saved_y if saved_y is not None else (screen_height - height) // 2

    min_width = min(width, max_width, max(720, min(WINDOW["min_width"], width)))
    min_height = min(height, max_height, max(520, min(WINDOW["min_height"], height)))
    x_pos = max(0, min(x_pos, screen_width - width))
    y_pos = max(0, min(y_pos, screen_height - height))

    root.minsize(min_width, min_height)
    root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")


class MainMenuFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
        self.dashboard_cards = {}
        self.dashboard_status_var = tk.StringVar(value="Dashboard non aggiornata")
        self._dashboard_loading = False
        self.refresh_button = None
        self.loading_feedback = None
        self._mousewheel_binding_id = None
        self._build_ui()

    def on_show(self):
        self.controller.title(UI_CONFIG["main_title"])

    def on_hide(self):
        self._unbind_mousewheel()

    def _build_ui(self):
        self.scroll_canvas = tk.Canvas(self, bg=APP_BG, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        shell = tk.Frame(self.scroll_canvas, bg=APP_BG)
        self.scroll_window = self.scroll_canvas.create_window((0, 0), window=shell, anchor="nw")
        self.scroll_canvas.bind("<Configure>", self._sync_scroll_width)
        shell.bind("<Configure>", self._sync_scroll_region)
        self.scroll_canvas.bind("<Enter>", self._bind_mousewheel)
        self.scroll_canvas.bind("<Leave>", self._unbind_mousewheel)

        content = tk.Frame(shell, bg=APP_BG)
        content.pack(fill="both", expand=True, padx=28, pady=24)

        header = tk.Frame(content, bg=APP_BG)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=APP_BG)
        title_box.pack(side="left", fill="x", expand=True)

        tk.Label(
            title_box,
            text=UI_CONFIG["dashboard_title"],
            bg=APP_BG,
            fg=TEXT,
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text="Benvenuto nel sistema di gestione dei servizi comunali.",
            bg=APP_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(10, 0))

        actions = tk.Frame(header, bg=APP_BG)
        actions.pack(side="right", padx=(20, 0))

        self.refresh_button = create_primary_button(actions, "Aggiorna dashboard", self.refresh_dashboard)
        self.refresh_button.pack(side="left")
        create_primary_button(actions, "Report mensile", self._show_monthly_report, SUCCESS).pack(
            side="left", padx=(10, 0)
        )
        self.loading_slot = tk.Frame(actions, bg=APP_BG)
        self.loading_slot.pack(side="left", padx=(10, 0))

        overview_shell, overview = create_card(content, padx=18, pady=16)
        overview_shell.pack(fill="x", pady=(24, 18))
        tk.Label(
            overview,
            text="i",
            bg="#DBEAFE",
            fg=PRIMARY,
            font=("Segoe UI", 15, "bold"),
            width=2,
            padx=5,
            pady=3,
        ).pack(side="left", padx=(0, 14))
        overview_text = tk.Frame(overview, bg=CARD_BG)
        overview_text.pack(side="left", fill="x", expand=True)
        tk.Label(
            overview_text,
            text="Panoramica rapida",
            bg=CARD_BG,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            overview_text,
            text="Tutti i moduli sono monitorati dalla dashboard operativa.",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))
        create_status_badge(overview, "Sistema operativo", "ok").pack(side="right", padx=(16, 0))

        cards = tk.Frame(content, bg=APP_BG)
        cards.pack(fill="both", expand=True)
        for column in range(3):
            cards.columnconfigure(column, weight=1, uniform="dashboard_cards")

        self._module_card(cards, MODULES["pass_invalidi"], "PassInvalidiFrame", "pass_invalidi", 0)
        self._module_card(cards, MODULES["segnalazioni"], "SegnalazioniFrame", "segnalazioni", 1)
        self._module_card(cards, MODULES["ospitalita"], "OspitalitaStranieriFrame", "ospitalita", 2)

        tk.Label(
            content,
            textvariable=self.dashboard_status_var,
            bg=APP_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(14, 0))

        self.refresh_dashboard()

    def _sync_scroll_width(self, event):
        self.scroll_canvas.itemconfigure(self.scroll_window, width=event.width)

    def _sync_scroll_region(self, _event=None):
        self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all"))

    def _bind_mousewheel(self, _event=None):
        if self._mousewheel_binding_id is None:
            self._mousewheel_binding_id = self.scroll_canvas.bind_all(
                "<MouseWheel>", self._on_mousewheel, add="+"
            )

    def _unbind_mousewheel(self, _event=None):
        if self._mousewheel_binding_id is not None:
            self.scroll_canvas.unbind_class(
                "all", "<MouseWheel>", self._mousewheel_binding_id
            )
            self._mousewheel_binding_id = None

    def _on_mousewheel(self, event):
        self.scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _module_card(self, parent, config, frame_name, dashboard_key, column):
        accent = config["accent"]
        card, inner = create_card(parent, padx=18, pady=18)
        card.grid(row=0, column=column, sticky="nsew", padx=8, pady=8)

        top = tk.Frame(inner, bg=CARD_BG)
        top.pack(fill="x")
        tk.Label(
            top,
            text=config["icon"],
            bg=accent,
            fg="white",
            font=("Segoe UI", 13, "bold"),
            width=2,
            padx=7,
            pady=6,
        ).pack(side="left", padx=(0, 10))

        title_box = tk.Frame(top, bg=CARD_BG)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text=config["menu_title"],
            bg=CARD_BG,
            fg=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")

        tk.Label(
            title_box,
            text=config["menu_description"],
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(5, 0))

        metrics_frame = tk.Frame(inner, bg=CARD_BG)
        metrics_frame.pack(fill="x", pady=(22, 16))
        metrics_frame.columnconfigure(0, weight=1)
        metrics_frame.columnconfigure(1, weight=1)

        file_box = tk.Frame(inner, bg=CARD_BG)
        file_box.pack(fill="x", pady=(0, 12))
        tk.Frame(file_box, bg=CARD_BORDER, height=1).pack(fill="x", pady=(0, 12))
        tk.Label(
            file_box,
            text="File dati",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w")
        file_var = tk.StringVar(value="Caricamento...")
        tk.Label(
            file_box,
            textvariable=file_var,
            bg=CARD_BG,
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
            wraplength=260,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        status_row = tk.Frame(inner, bg=CARD_BG)
        status_row.pack(fill="x", pady=(0, 16))
        badge = create_status_badge(status_row, "Caricamento", "info")
        badge.pack(side="left")

        detail_var = tk.StringVar(value="")
        detail_label = tk.Label(
            status_row,
            textvariable=detail_var,
            bg=CARD_BG,
            fg=TEXT_DIM,
            font=("Segoe UI", 8),
            wraplength=190,
            justify="left",
        )
        detail_label.pack(side="left", fill="x", expand=True, padx=(10, 0))
        inner.bind(
            "<Configure>",
            lambda event, detail=detail_label: detail.configure(
                wraplength=max(120, event.width - 150)
            ),
        )

        create_primary_button(
            inner,
            text="Apri Modulo",
            color=accent,
            command=lambda: self.controller.show_frame(frame_name),
        ).pack(fill="x", side="bottom")

        self.dashboard_cards[dashboard_key] = {
            "metrics_frame": metrics_frame,
            "file_var": file_var,
            "detail_var": detail_var,
            "badge": badge,
            "accent": accent,
        }
        self._render_card_metrics(dashboard_key, (("Stato", "Caricamento..."),), "")

    def refresh_dashboard(self):
        if self._dashboard_loading:
            return
        self._set_dashboard_busy(True)
        self.dashboard_status_var.set("Aggiornamento dashboard in corso...")
        for key in self.dashboard_cards:
            self._render_card_metrics(key, (("Stato", "Caricamento..."),), "")

        run_background_task(
            self,
            collect_dashboard_snapshot,
            self._apply_dashboard_snapshot,
            lambda exc: self._dashboard_failed(str(exc)),
        )

    def _set_dashboard_busy(self, busy):
        self._dashboard_loading = busy
        if self.refresh_button is not None:
            self.refresh_button.configure(
                state="disabled" if busy else "normal",
                text="Aggiornamento..." if busy else "Aggiorna dashboard",
            )
        set_busy_state(self.winfo_toplevel(), busy)
        if busy and self.loading_feedback is None:
            self.loading_feedback = show_loading_feedback(self.loading_slot, "Aggiornamento")
            self.loading_feedback.pack(side="left")
        elif not busy and self.loading_feedback is not None:
            hide_loading_feedback(self.loading_feedback)
            self.loading_feedback = None

    def _apply_dashboard_snapshot(self, snapshot):
        self._set_dashboard_busy(False)
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
        self._set_dashboard_busy(False)
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
        display_metrics = []
        file_value = "Non disponibile"
        for label, value in metrics:
            if label.lower() in {"ultimo file", "file dati"}:
                file_value = str(value)
            else:
                display_metrics.append((label, value))

        accent = card_state["accent"]
        for index, (label, value) in enumerate(display_metrics):
            box = create_stat_box(metrics_frame, label, value, accent)
            box.grid(row=index // 2, column=index % 2, sticky="nsew", padx=4, pady=4)

        status_text, status_kind = self._status_badge_from_metrics(metrics, detail)
        badge = card_state["badge"]
        badge.configure(
            text=status_text,
            bg={"ok": "#DCFCE7", "warning": "#FEF3C7", "error": "#FEE2E2", "info": "#DBEAFE"}[status_kind],
            fg={"ok": SUCCESS, "warning": WARNING, "error": DANGER, "info": ACCENT}[status_kind],
        )
        card_state["file_var"].set(file_value)
        card_state["detail_var"].set(detail)

    def _status_badge_from_metrics(self, metrics, detail):
        metric_text = " ".join(str(value) for _label, value in metrics)
        if "Errore" in metric_text or detail.startswith(DASHBOARD_ERROR):
            return "Errore", "error"
        if "ATTENZIONE" in metric_text or detail.startswith(DASHBOARD_WARNING):
            return "Attenzione", "warning"
        if "Caricamento" in metric_text:
            return "Caricamento", "info"
        return "OK", "ok"

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
        win.configure(bg=APP_BG)
        win.geometry("860x480")
        win.minsize(720, 360)
        win.transient(self.winfo_toplevel())

        wrap = tk.Frame(win, bg=APP_BG)
        wrap.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(wrap, bg=APP_BG)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=APP_BG)
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="Verifica configurazione",
            bg=APP_BG,
            fg=TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="Controlli locali su configurazione, percorsi e dipendenze.",
            bg=APP_BG,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        tree_frame = tk.Frame(wrap, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        tree_frame.pack(fill="both", expand=True, pady=(12, 10))

        tree = ttk.Treeview(tree_frame, columns=("status", "check", "detail"), show="headings", height=14)
        tree.heading("status", text="Esito")
        tree.heading("check", text="Controllo")
        tree.heading("detail", text="Dettaglio")
        tree.column("status", width=110, anchor="center", stretch=False)
        tree.column("check", width=210, anchor="w", stretch=False)
        tree.column("detail", width=500, anchor="w")
        tree.tag_configure(OK, foreground="#1E7A4D")
        tree.tag_configure(DIAGNOSTIC_WARNING, foreground="#9A5E0C")
        tree.tag_configure(ERROR, foreground="#B3261E")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        vsb.pack(side="right", fill="y")

        def populate():
            tree.delete(*tree.get_children())
            for item in run_diagnostics():
                tree.insert("", "end", values=(item.status, item.name, item.detail), tags=(item.status,))

        populate()

        footer = tk.Frame(wrap, bg=APP_BG)
        footer.pack(fill="x")

        create_primary_button(footer, "Esegui verifica", populate).pack(side="right")
        tk.Button(
            footer,
            text="Chiudi",
            bg=SECONDARY,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground=CARD_BORDER,
            padx=18,
            pady=8,
            command=win.destroy,
        ).pack(side="right", padx=(0, 8))

    def _show_monthly_report(self):
        ReportMensileWindow(self)

    def _show_audit_viewer(self):
        AuditViewerWindow(self)

    def _show_contacts(self):
        self.controller.show_frame("Contatti")


class DesktopApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(UI_CONFIG["main_title"])
        apply_responsive_geometry(self)
        apply_ttk_style(self, ACCENT)
        self.configure(bg=APP_BG)
        self.active_sidebar_key = "MainMenuFrame"
        self.sidebar_buttons = {}
        self.sidebar_collapsed = False

        self.app_shell = tk.Frame(self, bg=APP_BG)
        self.app_shell.pack(fill="both", expand=True)

        self.sidebar, self.sidebar_buttons = create_sidebar(
            self.app_shell,
            SIDEBAR_ITEMS,
            self.active_sidebar_key,
            self._handle_sidebar_selection,
            self._toggle_sidebar,
        )
        self.sidebar.pack(side="left", fill="y")

        self.screen_host = tk.Frame(self.app_shell, bg=APP_BG)
        self.screen_host.pack(side="left", fill="both", expand=True)

        self.frame_classes = {
            "MainMenuFrame": MainMenuFrame,
            "PassInvalidiFrame": PassInvalidiFrame,
            "SegnalazioniFrame": SegnalazioniFrame,
            "Sopralluoghi": SopralluoghiOverviewFrame,
            "OspitalitaStranieriFrame": OspitalitaStranieriFrame,
            "Contatti": ContattiUtiliFrame,
            "ConfigurazioneInizialeFrame": ConfigurazioneInizialeFrame,
        }
        self.frames = {}
        self.show_frame("MainMenuFrame")

    def _handle_sidebar_selection(self, key):
        if key in self.frame_classes:
            self.show_frame(key)
            return
        if key == "Report":
            ReportMensileWindow(self)
            self._set_active_sidebar(key)
            return
        if key == "Diagnostics":
            self._show_diagnostics_window()
            self._set_active_sidebar(key)
            return
        if key == "Audit":
            AuditViewerWindow(self)
            self._set_active_sidebar(key)

    def _set_active_sidebar(self, key):
        self.active_sidebar_key = key
        for item_key, button in self.sidebar_buttons.items():
            active = item_key == key
            normal_bg = SIDEBAR_ACTIVE if active else SIDEBAR_BG
            hover_bg = SIDEBAR_ACTIVE if active else "#08264E"
            button.configure(
                bg=normal_bg,
                fg="white" if active else "#E5E7EB",
            )
            button._hover_normal_style = {"bg": normal_bg}
            button._hover_style = {"bg": hover_bg}
            button._pressed_style = {"bg": hover_bg}

    def _toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        set_sidebar_collapsed(self.sidebar, self.sidebar_collapsed)

    def show_frame(self, frame_name):
        try:
            if frame_name not in self.frames:
                frame_class = self.frame_classes[frame_name]
                if frame_name == "PassInvalidiFrame":
                    self.frames[frame_name] = frame_class(self.screen_host, self, show_back_button=True)
                else:
                    self.frames[frame_name] = frame_class(self.screen_host, self)
        except Exception as exc:
            messagebox.showerror(
                "Modulo non disponibile",
                f"Impossibile aprire il modulo richiesto.\n\nDettagli:\n{exc}",
                parent=self,
            )
            return
        target = self.frames[frame_name]
        for frame in self.frames.values():
            if frame is not target and hasattr(frame, "on_hide"):
                frame.on_hide()
            frame.pack_forget()
        target.pack(fill="both", expand=True)
        self._set_active_sidebar(frame_name)
        if hasattr(target, "on_show"):
            target.on_show()

    def _show_diagnostics_window(self):
        if "MainMenuFrame" not in self.frames:
            self.show_frame("MainMenuFrame")
        frame = self.frames["MainMenuFrame"]
        frame._show_diagnostics()


def main():
    app = DesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
