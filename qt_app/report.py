from __future__ import annotations

import datetime as dt

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.audit import log_audit_event
from core.report_exporter import export_monthly_report_txt
from core.report_service import DEFAULT_MODULES, MONTH_NAMES, MonthlyReport
from qt_app.widgets import page_header
from qt_app.workers import ReportBuildWorker, ReportPdfWorker


MODULE_LABELS = {
    "pass_invalidi": "Pass Invalidi",
    "segnalazioni": "Segnalazioni",
    "ospitalita": "Ospitalita",
    "sopralluoghi": "Sopralluoghi",
}


class ReportPage(QWidget):
    def __init__(self, config: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.current_report: MonthlyReport | None = None
        self.thread: QThread | None = None
        self.worker = None
        self.module_checks: dict[str, QCheckBox] = {}

        today = dt.date.today()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(page_header("Report mensile", "Riepilogo attivita per mese e moduli selezionati."))

        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(18, 18, 18, 18)
        controls_layout.setSpacing(14)

        controls = QGridLayout()
        controls.setHorizontalSpacing(14)
        controls.setVerticalSpacing(8)

        controls.addWidget(QLabel("Mese"), 0, 0)
        self.month_combo = QComboBox()
        self.month_combo.addItems([f"{month:02d} - {name}" for month, name in MONTH_NAMES.items()])
        self.month_combo.setCurrentIndex(today.month - 1)
        controls.addWidget(self.month_combo, 1, 0)

        controls.addWidget(QLabel("Anno"), 0, 1)
        self.year_combo = QComboBox()
        years = [str(year) for year in range(today.year - 5, today.year + 2)]
        self.year_combo.addItems(years)
        self.year_combo.setCurrentText(str(today.year))
        controls.addWidget(self.year_combo, 1, 1)

        controls.addWidget(QLabel("Moduli"), 0, 2)
        modules_row = QHBoxLayout()
        for key in DEFAULT_MODULES:
            check = QCheckBox(MODULE_LABELS[key])
            check.setChecked(True)
            self.module_checks[key] = check
            modules_row.addWidget(check)
        modules_row.addStretch(1)
        controls.addLayout(modules_row, 1, 2)
        controls.setColumnStretch(2, 1)
        controls_layout.addLayout(controls)

        actions = QHBoxLayout()
        self.preview_button = QPushButton("Anteprima report")
        self.preview_button.clicked.connect(self.preview_report)
        self.txt_button = QPushButton("Esporta TXT")
        self.txt_button.clicked.connect(self.export_txt)
        self.pdf_button = QPushButton("Esporta PDF")
        self.pdf_button.clicked.connect(self.export_pdf)
        self.pdf_button.setProperty("danger", "true")
        actions.addWidget(self.preview_button)
        actions.addWidget(self.txt_button)
        actions.addWidget(self.pdf_button)
        actions.addStretch(1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(150)
        self.progress.hide()
        actions.addWidget(self.progress)
        controls_layout.addLayout(actions)

        self.status = QLabel("Report non generato")
        self.status.setObjectName("Muted")
        controls_layout.addWidget(self.status)
        layout.addWidget(controls_card)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.preview.setPlaceholderText("Genera l'anteprima per visualizzare il report.")
        self.preview.setStyleSheet('font-family: "Consolas"; font-size: 10pt;')
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_card, 1)

    def preview_report(self) -> None:
        if self.thread is not None:
            return
        month, year, modules = self._selection()
        if not modules:
            QMessageBox.information(self, "Moduli richiesti", "Seleziona almeno un modulo.")
            return
        self._set_working(True)
        self.status.setText("Generazione anteprima in corso...")

        self.thread = QThread(self)
        self.worker = ReportBuildWorker(month, year, modules)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._set_report)
        self.worker.failed.connect(self._generation_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def export_txt(self) -> None:
        if self.current_report is None:
            QMessageBox.information(self, "Anteprima richiesta", "Genera prima l'anteprima, poi riesegui l'esportazione TXT.")
            self.preview_report()
            return
        try:
            path = export_monthly_report_txt(self.current_report)
        except Exception as exc:
            log_audit_event(
                "sistema",
                "export_report_txt",
                "report_mensile",
                None,
                "Esportazione TXT report mensile non riuscita",
                result="error",
                error=str(exc),
            )
            QMessageBox.critical(self, "Esportazione non riuscita", f"Impossibile esportare il TXT.\n\n{exc}")
            return
        log_audit_event(
            "sistema",
            "export_report_txt",
            "report_mensile",
            f"{self.current_report.year}-{self.current_report.month:02d}",
            "Esportato report mensile TXT",
        )
        self.status.setText(f"TXT esportato: {path}")
        QMessageBox.information(self, "TXT esportato", f"Report salvato in:\n{path}")

    def export_pdf(self) -> None:
        if self.thread is not None:
            return
        if self.current_report is None:
            QMessageBox.information(self, "Anteprima richiesta", "Genera prima l'anteprima, poi riesegui l'esportazione PDF.")
            self.preview_report()
            return
        self._set_working(True, pdf=True)
        self.status.setText("Esportazione PDF in corso...")

        self.thread = QThread(self)
        self.worker = ReportPdfWorker(self.current_report)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self._pdf_done)
        self.worker.failed.connect(self._pdf_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self._thread_finished)
        self.thread.start()

    def _selection(self) -> tuple[int, int, tuple[str, ...]]:
        month = int(self.month_combo.currentText().split(" ", 1)[0])
        year = int(self.year_combo.currentText().strip())
        modules = tuple(key for key, check in self.module_checks.items() if check.isChecked())
        return month, year, modules

    def _set_report(self, report: MonthlyReport) -> None:
        self.current_report = report
        self.preview.setPlainText(report.text)
        self.status.setText("Anteprima aggiornata")

    def _generation_failed(self, detail: str) -> None:
        self.status.setText("Errore generazione report")
        QMessageBox.critical(self, "Report non generato", f"Impossibile generare il report.\n\n{detail}")

    def _pdf_done(self, path, report: MonthlyReport) -> None:
        log_audit_event(
            "sistema",
            "export_report_pdf",
            "report_mensile",
            f"{report.year}-{report.month:02d}",
            "Esportato report mensile PDF",
        )
        self.status.setText(f"PDF esportato: {path}")
        QMessageBox.information(self, "PDF esportato", f"Report salvato in:\n{path}")

    def _pdf_failed(self, detail: str) -> None:
        log_audit_event(
            "sistema",
            "export_report_pdf",
            "report_mensile",
            None,
            "Esportazione PDF report mensile non riuscita",
            result="error",
            error=detail,
        )
        self.status.setText("Esportazione PDF non riuscita")
        QMessageBox.critical(self, "Esportazione non riuscita", f"Impossibile esportare il PDF.\n\n{detail}")

    def _thread_finished(self) -> None:
        self._set_working(False)
        self.thread = None
        self.worker = None

    def _set_working(self, working: bool, pdf: bool = False) -> None:
        self.preview_button.setEnabled(not working)
        self.txt_button.setEnabled(not working)
        self.pdf_button.setEnabled(not working)
        self.pdf_button.setText("PDF in corso..." if working and pdf else "Esporta PDF")
        self.progress.setVisible(working)
        self.setCursor(Qt.WaitCursor if working else Qt.ArrowCursor)
