from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from core.dashboard_service import collect_dashboard_snapshot
from core.report_exporter import export_monthly_report_pdf
from core.report_service import build_monthly_report
from qt_app.segnalazioni_pdf import render_segnalazione_pdf
from qt_app.sopralluoghi_pdf import render_sopralluogo_pdf


class DashboardWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(collect_dashboard_snapshot())
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class ReportBuildWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, month: int, year: int, modules: tuple[str, ...]):
        super().__init__()
        self.month = month
        self.year = year
        self.modules = modules

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(build_monthly_report(self.month, self.year, self.modules))
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class ReportPdfWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, report):
        super().__init__()
        self.report = report

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(export_monthly_report_pdf(self.report), self.report)
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class SegnalazionePdfWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, payload: dict[str, str], output_path):
        super().__init__()
        self.payload = payload
        self.output_path = output_path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(render_segnalazione_pdf(self.payload, self.output_path))
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class SopralluogoPdfWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, segnalazione, sopralluogo, output_path):
        super().__init__()
        self.segnalazione = segnalazione
        self.sopralluogo = sopralluogo
        self.output_path = output_path

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(render_sopralluogo_pdf(self.segnalazione, self.sopralluogo, self.output_path))
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class PassInvalidiLoadWorker(QObject):
    finished = Signal(object, object, object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            from pass_invalidi import carica_tutti

            records, files, errors = carica_tutti()
            self.finished.emit(records, files, errors)
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")


class OspitalitaLoadWorker(QObject):
    finished = Signal(object, object, object, object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            import os
            from ospitalita_stranieri import FOLDER_OSPITALITA, _extract_records, _list_input_files

            records: list[dict] = []
            errors: list[str] = []
            insights: list[str] = []
            files: list[str] = []
            if not os.path.isdir(FOLDER_OSPITALITA):
                errors.append("Percorso di rete non raggiungibile.")
            else:
                files = _list_input_files()
                for path in files:
                    try:
                        file_records, insight = _extract_records(path)
                        records.extend(file_records)
                        insights.append(insight)
                    except Exception as exc:
                        errors.append(f"{os.path.basename(path)}: {exc}")
            self.finished.emit(records, files, errors, insights)
        except Exception as exc:
            self.failed.emit(str(exc) or "Errore non specificato")
