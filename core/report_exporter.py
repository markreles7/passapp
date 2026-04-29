from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from app_config import load_config, resolve_path
from core.logging_utils import setup_module_logger
from core.powershell import check_office_com
from core.report_service import MonthlyReport

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
REPORTS_DIR = resolve_path(PATHS.get("report_mensili_dir", "documenti/report_mensili"))
LOG_FILE = resolve_path(PATHS["log_file"])
logger = setup_module_logger(__name__, LOG_FILE)


def monthly_report_base_path(report: MonthlyReport, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / f"report_mensile_{report.year}_{report.month:02d}"


def export_monthly_report_txt(report: MonthlyReport, reports_dir: Path = REPORTS_DIR) -> Path:
    path = monthly_report_base_path(report, reports_dir).with_suffix(".txt")
    path.write_text(report.text, encoding="utf-8")
    return path


def export_monthly_report_pdf(report: MonthlyReport, reports_dir: Path = REPORTS_DIR) -> Path:
    available, detail = check_office_com("Word.Application")
    if not available:
        raise RuntimeError(f"Microsoft Word non disponibile: {detail}")
    path = monthly_report_base_path(report, reports_dir).with_suffix(".pdf")
    _render_pdf_with_word(report, path)
    return path


def _render_pdf_with_word(report: MonthlyReport, output_pdf: Path) -> None:
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)
$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param([object]$Selection, [string]$Text, [int]$Size = 10, [bool]$Bold = $false, [int]$SpaceAfter = 3)
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Add()
    $sel = $word.Selection
    $pageSetup = $doc.PageSetup
    $pageSetup.TopMargin = $word.CentimetersToPoints(1.4)
    $pageSetup.BottomMargin = $word.CentimetersToPoints(1.4)
    $pageSetup.LeftMargin = $word.CentimetersToPoints(1.6)
    $pageSetup.RightMargin = $word.CentimetersToPoints(1.6)

    $lines = $payload.text -split "`n"
    foreach ($line in $lines) {
        $trim = $line.TrimEnd()
        if ($trim.Length -eq 0) {
            Add-Paragraph -Selection $sel -Text "" -Size 8 -SpaceAfter 1
        } elseif ($trim -eq $trim.ToUpper() -and $trim.Length -gt 3 -and -not $trim.StartsWith("-")) {
            Add-Paragraph -Selection $sel -Text $trim -Size 12 -Bold $true -SpaceAfter 4
        } else {
            Add-Paragraph -Selection $sel -Text $trim -Size 10 -SpaceAfter 2
        }
    }

    $doc.ExportAsFixedFormat($PdfPath, 17)
    $doc.Close($false)
    $doc = $null
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
    with tempfile.TemporaryDirectory(prefix="passapp_report_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_path = tmp_path / "payload.json"
        script_path = tmp_path / "report_pdf.ps1"
        payload_path.write_text(json.dumps({"text": report.text}, ensure_ascii=False), encoding="utf-8")
        script_path.write_text(ps_script, encoding="utf-8")
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-PdfPath",
                str(output_pdf),
                "-PayloadPath",
                str(payload_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode != 0:
            logger.error("Errore esportazione PDF report: %s", result.stderr or result.stdout)
            raise RuntimeError((result.stderr or result.stdout or "Errore sconosciuto").strip())
    if not output_pdf.exists():
        raise RuntimeError("Il file PDF non e stato creato.")
