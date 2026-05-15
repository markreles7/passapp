from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def page_header(title: str, subtitle: str = "") -> QWidget:
    header = QWidget()
    layout = QVBoxLayout(header)
    layout.setContentsMargins(0, 0, 0, 14)
    layout.setSpacing(4)

    title_label = QLabel(title)
    title_label.setObjectName("PageTitle")
    layout.addWidget(title_label)

    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("PageSubtitle")
        layout.addWidget(subtitle_label)

    return header


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header(title, subtitle))

        card = QFrame()
        card.setObjectName("Card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        message = QLabel("Pagina disponibile come area minima nella versione Qt. Le funzioni dedicate verranno completate qui.")
        message.setObjectName("Muted")
        message.setWordWrap(True)
        card_layout.addWidget(message)
        layout.addWidget(card)
        layout.addStretch(1)


class MetricRow(QWidget):
    def __init__(self, label: str, value: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(12)

        label_widget = QLabel(label)
        label_widget.setObjectName("Muted")
        value_widget = QLabel(value)
        value_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_widget.setWordWrap(True)

        layout.addWidget(label_widget, 1)
        layout.addWidget(value_widget, 1)
