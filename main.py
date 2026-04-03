import tkinter as tk

from app_config import load_config
from ospitalita_stranieri import OspitalitaStranieriFrame
from pass_invalidi import PassInvalidiFrame
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
TEXT = THEME["text"]
TEXT_MUTED = THEME["text_muted"]


class MainMenuFrame(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=BG)
        self.controller = controller
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

        cards = tk.Frame(shell, bg=BG)
        cards.pack(fill="both", expand=True, pady=(14, 0))

        self._module_card(cards, MODULES["pass_invalidi"], "PassInvalidiFrame")
        self._module_card(cards, MODULES["segnalazioni"], "SegnalazioniFrame")
        self._module_card(cards, MODULES["ospitalita"], "OspitalitaStranieriFrame")

    def _module_card(self, parent, config, frame_name):
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

        tk.Button(
            inner,
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
        ).pack(anchor="w")


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
