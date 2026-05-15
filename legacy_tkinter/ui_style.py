from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ui_motion import bind_hover

SIDEBAR_BG = "#0B2E5F"
SIDEBAR_BG_DARK = "#08264E"
SIDEBAR_ACTIVE = "#2563EB"
APP_BG = "#F5F7FA"
APP_BG_ALT = "#EEF2F7"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#E5E7EB"
TEXT = "#1F2937"
TEXT_MUTED = "#6B7280"
TEXT_DIM = "#9CA3AF"
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
SUCCESS = "#198754"
WARNING = "#D97706"
DANGER = "#B42318"
SECONDARY = "#F3F4F6"
SHADOW = "#D8DEE8"


def _button_hover(color: str) -> str:
    return {
        PRIMARY: PRIMARY_DARK,
        SUCCESS: "#146C43",
        WARNING: "#B45309",
        DANGER: "#8E1F17",
        SECONDARY: CARD_BORDER,
        SIDEBAR_BG: SIDEBAR_BG_DARK,
        SIDEBAR_ACTIVE: "#1D4ED8",
    }.get(color, color)

MODULE_COLORS = {
    "pass_invalidi": ("#2563EB", "#1D4ED8"),
    "segnalazioni": ("#D97706", "#B45309"),
    "ospitalita": ("#198754", "#146C43"),
    "sopralluoghi": ("#4F46E5", "#3730A3"),
    "accertamenti_anagrafici": ("#7C3AED", "#5B21B6"),
    "report": ("#0F766E", "#115E59"),
    "contatti": ("#355C7D", "#28475F"),
    "audit": ("#475569", "#334155"),
}


def modern_theme() -> dict[str, str]:
    return {
        "bg": APP_BG,
        "bg2": APP_BG_ALT,
        "surface": CARD_BG,
        "border": CARD_BORDER,
        "accent": PRIMARY,
        "accent_dark": PRIMARY_DARK,
        "success": SUCCESS,
        "warning": WARNING,
        "danger": DANGER,
        "text": TEXT,
        "text_muted": TEXT_MUTED,
        "text_dim": TEXT_DIM,
        "sidebar": SIDEBAR_BG,
        "sidebar_dark": SIDEBAR_BG_DARK,
        "sidebar_active": SIDEBAR_ACTIVE,
        "secondary": SECONDARY,
        "shadow": SHADOW,
    }


def apply_ttk_style(widget, accent: str = PRIMARY, selected_bg: str = "#DBEAFE"):
    style = ttk.Style(widget)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Treeview",
        background=CARD_BG,
        fieldbackground=CARD_BG,
        foreground=TEXT,
        rowheight=34,
        font=("Segoe UI", 10),
        bordercolor=CARD_BORDER,
        relief="flat",
    )
    style.configure(
        "Treeview.Heading",
        background=APP_BG_ALT,
        foreground=TEXT_MUTED,
        font=("Segoe UI", 9, "bold"),
        relief="flat",
        bordercolor=CARD_BORDER,
        padding=(8, 7),
    )
    style.map(
        "Treeview",
        background=[("selected", selected_bg)],
        foreground=[("selected", TEXT)],
    )
    style.configure(
        "TCombobox",
        fieldbackground=CARD_BG,
        background=CARD_BG,
        foreground=TEXT,
        arrowcolor=accent,
        padding=(8, 5),
    )
    return style


def create_card(parent, bg: str = CARD_BG, padx: int = 16, pady: int = 14):
    shell = tk.Frame(parent, bg=SHADOW)
    card = tk.Frame(shell, bg=bg, highlightbackground=CARD_BORDER, highlightthickness=1)
    card.pack(fill="both", expand=True, padx=(0, 1), pady=(0, 1))
    inner = tk.Frame(card, bg=bg)
    inner.pack(fill="both", expand=True, padx=padx, pady=pady)
    return shell, inner


def create_header(parent, title: str, subtitle: str = "", icon: str = "SU", accent: str = PRIMARY):
    shell, inner = create_card(parent, padx=18, pady=14)
    title_wrap = tk.Frame(inner, bg=CARD_BG)
    title_wrap.pack(fill="x")
    tk.Label(
        title_wrap,
        text=icon,
        bg=accent,
        fg="white",
        font=("Segoe UI", 14, "bold"),
        width=2,
        padx=7,
        pady=5,
    ).pack(side="left", padx=(0, 12))
    text_box = tk.Frame(title_wrap, bg=CARD_BG)
    text_box.pack(side="left", fill="x", expand=True)
    tk.Label(text_box, text=title, bg=CARD_BG, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w")
    if subtitle:
        tk.Label(text_box, text=subtitle, bg=CARD_BG, fg=TEXT_MUTED, font=("Segoe UI", 10)).pack(
            anchor="w", pady=(4, 0)
        )
    return shell, inner


def create_primary_button(parent, text: str, command, color: str = PRIMARY):
    button = tk.Button(
        parent,
        text=text,
        bg=color,
        fg="white",
        activebackground=color,
        activeforeground="white",
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        cursor="hand2",
        padx=14,
        pady=9,
        command=command,
    )
    return bind_hover(
        button,
        {"bg": color},
        {"bg": _button_hover(color)},
        {"bg": _button_hover(color)},
    )


def create_secondary_button(parent, text: str, command):
    button = tk.Button(
        parent,
        text=text,
        bg=SECONDARY,
        fg=TEXT,
        activebackground=CARD_BORDER,
        activeforeground=TEXT,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        cursor="hand2",
        padx=14,
        pady=9,
        command=command,
    )
    return bind_hover(
        button,
        {"bg": SECONDARY},
        {"bg": CARD_BORDER},
        {"bg": "#D1D5DB"},
    )


def create_status_badge(parent, text: str, status: str = "ok"):
    colors = {
        "ok": ("#DCFCE7", SUCCESS),
        "warning": ("#FEF3C7", WARNING),
        "error": ("#FEE2E2", DANGER),
        "info": ("#DBEAFE", PRIMARY),
    }
    bg, fg = colors.get(status, colors["info"])
    return tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=("Segoe UI", 9, "bold"),
        padx=10,
        pady=5,
    )


def create_stat_box(parent, label: str, value: str = "-", accent: str = PRIMARY):
    box = tk.Frame(parent, bg=APP_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
    value_label = tk.Label(box, text=value, bg=APP_BG, fg=accent, font=("Segoe UI", 18, "bold"))
    value_label.pack(
        fill="x",
        padx=10,
        pady=(14, 2),
    )
    tk.Label(
        box,
        text=label,
        bg=APP_BG,
        fg=TEXT,
        font=("Segoe UI", 9),
        wraplength=105,
        justify="center",
    ).pack(fill="x", padx=10, pady=(0, 14))
    box._value_label = value_label
    return box


def create_toolbar(parent):
    toolbar = tk.Frame(parent, bg=APP_BG)
    toolbar.pack(fill="x")
    return toolbar


def create_section_title(parent, title: str, subtitle: str = ""):
    tk.Label(parent, text=title, bg=CARD_BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
    if subtitle:
        tk.Label(parent, text=subtitle, bg=CARD_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(
            anchor="w", pady=(3, 0)
        )


def create_sidebar(parent, items, active_key: str, on_select, on_toggle=None):
    sidebar = tk.Frame(parent, bg=SIDEBAR_BG, width=252)
    sidebar.pack_propagate(False)

    brand = tk.Frame(sidebar, bg=SIDEBAR_BG)
    brand.pack(fill="x", padx=18, pady=(24, 18))
    toggle = tk.Button(
        brand,
        text="<<",
        bg=SIDEBAR_BG_DARK,
        fg="white",
        activebackground=SIDEBAR_ACTIVE,
        activeforeground="white",
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        cursor="hand2",
        width=2,
        command=on_toggle,
    )
    bind_hover(toggle, {"bg": SIDEBAR_BG_DARK}, {"bg": SIDEBAR_ACTIVE})
    if on_toggle is not None:
        toggle.pack(side="right")
    brand_badge = tk.Label(
        brand,
        text="SU",
        bg=SIDEBAR_ACTIVE,
        fg="white",
        font=("Segoe UI", 16, "bold"),
        width=2,
        padx=8,
        pady=7,
    )
    brand_badge.pack(side="left", padx=(0, 12))
    brand_text = tk.Frame(brand, bg=SIDEBAR_BG)
    brand_text.pack(side="left", fill="x", expand=True)
    brand_labels = [
        tk.Label(brand_text, text="PassApp", bg=SIDEBAR_BG, fg="white", font=("Segoe UI", 18, "bold")),
        tk.Label(brand_text, text="Polizia Locale", bg=SIDEBAR_BG, fg="#DBEAFE", font=("Segoe UI", 10)),
    ]
    for label in brand_labels:
        label.pack(anchor="w")

    nav = tk.Frame(sidebar, bg=SIDEBAR_BG)
    nav.pack(fill="both", expand=True, padx=10)
    buttons = {}
    for item in items:
        key = item["key"]
        is_active = key == active_key
        btn = tk.Button(
            nav,
            text=f"{item['icon']}   {item['label']}",
            bg=SIDEBAR_ACTIVE if is_active else SIDEBAR_BG,
            fg="white" if is_active else "#E5E7EB",
            activebackground=SIDEBAR_ACTIVE,
            activeforeground="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            cursor="hand2",
            anchor="w",
            padx=18,
            pady=12,
            command=lambda item_key=key: on_select(item_key),
        )
        bind_hover(
            btn,
            {"bg": SIDEBAR_ACTIVE if is_active else SIDEBAR_BG},
            {"bg": SIDEBAR_ACTIVE if is_active else SIDEBAR_BG_DARK},
        )
        btn.pack(fill="x", pady=3)
        buttons[key] = btn

    footer = tk.Frame(sidebar, bg=SIDEBAR_BG)
    footer.pack(fill="x", padx=22, pady=24)
    footer_labels = [
        tk.Label(footer, text="Polizia Locale", bg=SIDEBAR_BG, fg="white", font=("Segoe UI", 10, "bold")),
        tk.Label(
            footer,
            text="Ufficio Servizi Comunali",
            bg=SIDEBAR_BG,
            fg="#BFDBFE",
            font=("Segoe UI", 9),
        ),
    ]
    footer_labels[0].pack(anchor="w")
    footer_labels[1].pack(anchor="w", pady=(3, 0))

    sidebar._expanded_width = 252
    sidebar._collapsed_width = 78
    sidebar._nav_items = items
    sidebar._nav_buttons = buttons
    sidebar._brand_text = brand_text
    sidebar._brand_labels = brand_labels
    sidebar._footer = footer
    sidebar._footer_labels = footer_labels
    sidebar._toggle_button = toggle
    sidebar._collapsed = False
    return sidebar, buttons


def set_sidebar_collapsed(sidebar, collapsed: bool, update_width: bool = True):
    sidebar._collapsed = collapsed
    if update_width:
        sidebar.configure(width=sidebar._collapsed_width if collapsed else sidebar._expanded_width)
    sidebar._toggle_button.configure(text=">>" if collapsed else "<<")

    if collapsed:
        sidebar._brand_text.pack_forget()
        sidebar._footer.pack_forget()
    else:
        if not sidebar._brand_text.winfo_manager():
            sidebar._brand_text.pack(side="left", fill="x", expand=True)
        if not sidebar._footer.winfo_manager():
            sidebar._footer.pack(fill="x", padx=22, pady=24)

    for item in sidebar._nav_items:
        button = sidebar._nav_buttons[item["key"]]
        button.configure(
            text=item["icon"] if collapsed else f"{item['icon']}   {item['label']}",
            anchor="center" if collapsed else "w",
            padx=8 if collapsed else 18,
        )
