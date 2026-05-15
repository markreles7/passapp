from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget


NAV_ITEMS = (
    ("dashboard", "SU", "Dashboard"),
    ("pass_invalidi", "PI", "Pass Invalidi"),
    ("segnalazioni", "SC", "Segnalazioni"),
    ("sopralluoghi", "SP", "Sopralluoghi"),
    ("accertamenti_anagrafici", "AA", "Accertamenti Anagrafici"),
    ("ospitalita", "OS", "Ospitalita"),
    ("report", "RM", "Report mensile"),
    ("contatti", "CT", "Contatti utili"),
    ("configurazione", "CF", "Configurazione"),
    ("diagnostica", "VC", "Diagnostica"),
    ("audit", "AU", "Storico modifiche"),
)


class Sidebar(QFrame):
    selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(252)
        self.buttons: dict[str, QPushButton] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(10)

        title = QLabel("PassApp")
        title.setObjectName("SidebarTitle")
        title.setStyleSheet("font-size: 20pt; font-weight: 700;")
        subtitle = QLabel("Polizia Locale")
        subtitle.setObjectName("SidebarSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        for key, icon, label in NAV_ITEMS:
            button = QPushButton(f"{icon}   {label}")
            button.setObjectName("NavButton")
            button.setProperty("active", "false")
            button.clicked.connect(lambda _checked=False, item_key=key: self.selected.emit(item_key))
            layout.addWidget(button)
            self.buttons[key] = button

        layout.addStretch(1)

        footer = QLabel("Ufficio Servizi Comunali")
        footer.setObjectName("SidebarSubtitle")
        layout.addWidget(footer)

    def set_active(self, key: str) -> None:
        for item_key, button in self.buttons.items():
            button.setProperty("active", "true" if item_key == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
