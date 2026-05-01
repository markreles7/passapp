from __future__ import annotations

from pathlib import Path

from segnalazioni import Segnalazione, SegnalazioniFrame


def safe_pdf_filename(value: str) -> str:
    return SegnalazioniFrame._safe_filename(value)


def build_pdf_payload(seg: Segnalazione) -> dict[str, str]:
    exporter = SegnalazioniFrame.__new__(SegnalazioniFrame)
    return exporter._build_doc_payload(seg)


def render_segnalazione_pdf(payload: dict[str, str], output_pdf: Path) -> Path:
    exporter = SegnalazioniFrame.__new__(SegnalazioniFrame)
    exporter._render_pdf_report(payload, output_pdf)
    return output_pdf
