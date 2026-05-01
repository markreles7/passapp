from __future__ import annotations

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_app.theme import status_colors
from qt_app.widgets import MetricRow, page_header
from qt_app.workers import DashboardWorker


class DashboardCard(QFrame):
    def __init__(self, title: str, accent: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.title = title
        self.badge = QLabel("In attesa")
        self.badge.setObjectName("Badge")
        self.detail = QLabel("")
        self.detail.setObjectName("Muted")
        self.detail.setWordWrap(True)
        self.metrics_layout = QVBoxLayout()
        self.metrics_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        top = QHBoxLayout()
        icon = QLabel(title[:2].upper())
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(38, 38)
        icon.setStyleSheet(f"background: {accent}; color: white; border-radius: 6px; font-weight: 700;")
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 12pt; font-weight: 700;")
        top.addWidget(icon)
        top.addWidget(title_label, 1)
        top.addWidget(self.badge)
        layout.addLayout(top)
        layout.addLayout(self.metrics_layout)
        layout.addWidget(self.detail)
        layout.addStretch(1)

    def set_loading(self) -> None:
        self._set_badge("Caricamento", "#DBEAFE", "#2D6BE4")
        self.detail.setText("")
        self._set_metrics((("Stato", "Caricamento..."),))

    def set_data(self, config: dict, card) -> None:
        bg, fg = status_colors(config, card.status)
        self._set_badge(card.status, bg, fg)
        self._set_metrics(card.metrics)
        self.detail.setText(card.detail)

    def _set_badge(self, text: str, bg: str, fg: str) -> None:
        self.badge.setText(text)
        self.badge.setStyleSheet(f"background: {bg}; color: {fg};")

    def _set_metrics(self, metrics) -> None:
        while self.metrics_layout.count():
            item = self.metrics_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for label, value in metrics:
            self.metrics_layout.addWidget(MetricRow(str(label), str(value)))


class DashboardPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.thread: QThread | None = None
        self.worker: DashboardWorker | None = None
        self.cards: dict[str, DashboardCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header_row = QHBoxLayout()
        header_row.addWidget(
            page_header(
                config["ui"]["dashboard_title"],
                "Versione Qt parallela: shell pronta, moduli in migrazione progressiva.",
            ),
            1,
        )
        self.refresh_button = QPushButton("Aggiorna")
        self.refresh_button.clicked.connect(self.refresh)
        header_row.addWidget(self.refresh_button)
        layout.addLayout(header_row)

        grid = QGridLayout()
        grid.setSpacing(14)
        modules = config["ui"]["modules"]
        for column, key in enumerate(("pass_invalidi", "segnalazioni", "ospitalita")):
            module = modules[key]
            card = DashboardCard(module["menu_title"], module["accent"])
            card._set_metrics((("Stato", "In attesa"),))
            grid.addWidget(card, 0, column)
            self.cards[key] = card
        layout.addLayout(grid)
        layout.addStretch(1)

        self.status = QLabel("Pronta per il primo aggiornamento.")
        self.status.setObjectName("Muted")
        layout.addWidget(self.status)

    def refresh(self) -> None:
        if self.thread is not None:
            return
        self.refresh_button.setEnabled(False)
        self.status.setText("Aggiornamento dashboard in corso...")
        for card in self.cards.values():
            card.set_loading()

        self.thread = QThread(self)
        self.worker = DashboardWorker()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._apply_snapshot)
        self.worker.failed.connect(self._show_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def _apply_snapshot(self, snapshot) -> None:
        for key, card_data in snapshot.cards.items():
            card = self.cards.get(key)
            if card is not None:
                card.set_data(self.config, card_data)
        self.status.setText(f"Ultimo aggiornamento: {snapshot.updated_at:%d/%m/%Y %H:%M:%S}")

    def _show_error(self, detail: str) -> None:
        self.status.setText(f"Errore aggiornamento dashboard: {detail}")

    def _thread_finished(self) -> None:
        self.refresh_button.setEnabled(True)
        self.thread = None
        self.worker = None
