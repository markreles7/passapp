from __future__ import annotations

import json

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from services.ai.audit import read_ai_interactions
from qt_app.widgets import page_header


class AIDiagnosticsPage(QWidget):
    """Technical ChatGPT audit view; MainWindow restricts this page to administrators."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(page_header("Diagnostica ChatGPT", "Vista tecnica riservata delle interazioni con ChatGPT."))
        row = QHBoxLayout()
        self.status = QLabel("")
        refresh = QPushButton("Aggiorna audit IA")
        refresh.clicked.connect(self.refresh)
        row.addWidget(self.status)
        row.addStretch(1)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.content = QPlainTextEdit()
        self.content.setReadOnly(True)
        layout.addWidget(self.content, 1)
        self.refresh()

    def refresh(self) -> None:
        events = read_ai_interactions()
        self.content.setPlainText("\n\n".join(json.dumps(item, ensure_ascii=False, indent=2) for item in reversed(events)))
        self.status.setText(f"Interazioni visualizzate: {len(events)}")
