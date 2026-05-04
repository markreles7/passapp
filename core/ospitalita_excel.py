from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from core.text_utils import display_text, normalize_basic


def extract_year_from_text(text: str) -> int:
    years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", str(text or ""))]
    return max(years) if years else -1


def compact_values(*values) -> str:
    parts: list[str] = []
    for value in values:
        text = display_text(value).strip()
        if not text or normalize_basic(text) in {"-", "—"}:
            continue
        if text not in parts:
            parts.append(text)
    return " | ".join(parts) if parts else "-"


def split_display_name_address(text: str) -> tuple[str, str]:
    raw = display_text(text).strip()
    if not raw:
        return "", ""
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return raw, ""


def record_progressivo_int(record: dict) -> int | None:
    nums = re.findall(r"\d+", str(record.get("progressivo", "")))
    if not nums:
        return None
    try:
        return int(nums[0])
    except ValueError:
        return None


def is_blankish(value) -> bool:
    return normalize_basic(value) in {"", "-", "—", "none", "nan"}


def is_empty_slot(record: dict) -> bool:
    fields = (
        record.get("protocollo", ""),
        record.get("data_presentazione", ""),
        record.get("denunciante_dichiarante", ""),
        record.get("cittadino_ospitato", ""),
        record.get("tipo_comunicazione", ""),
        record.get("indirizzo", ""),
    )
    return all(is_blankish(value) for value in fields)


def find_record_by_progressivo(records: list[dict], progressivo: str, source_name: str | None = None) -> dict | None:
    try:
        target = int(progressivo)
    except (TypeError, ValueError):
        return None

    source_ref = (source_name or "").strip()
    for record in records:
        if source_ref and str(record.get("source", "")).strip() != source_ref:
            continue
        if record_progressivo_int(record) == target:
            return record
    return None


def reserve_progressivo_slot(records: list[dict], source_name: str) -> tuple[str, dict | None, dict | None, str]:
    source_ref = source_name.strip()
    numeric_records: list[tuple[int, dict]] = []
    for record in records:
        if source_ref and str(record.get("source", "")).strip() != source_ref:
            continue
        progressivo = record_progressivo_int(record)
        if progressivo is not None:
            numeric_records.append((progressivo, record))

    for progressivo, record in sorted(numeric_records, key=lambda item: item[0]):
        if record.get("_pending"):
            continue
        if is_empty_slot(record):
            return str(progressivo), record, dict(record), "update_slot"

    max_progressivo = max((progressivo for progressivo, _ in numeric_records), default=0)
    return str(max_progressivo + 1), None, None, "append"


def upsert_pending_record(pending_records: list[dict], pending: dict) -> None:
    source = str(pending.get("source", "")).strip()
    progressivo = str(pending.get("progressivo", "")).strip()
    for idx, existing in enumerate(pending_records):
        if (
            str(existing.get("source", "")).strip() == source
            and str(existing.get("progressivo", "")).strip() == progressivo
        ):
            if existing.get("original_snapshot") and not pending.get("original_snapshot"):
                pending["original_snapshot"] = existing.get("original_snapshot")
            pending_records[idx] = pending
            return
    pending_records.append(pending)


def build_pending_payload(pending_records: list[dict]) -> list[dict]:
    payload = []
    for record in pending_records:
        item = {
            "progressivo": str(record.get("progressivo", "")),
            "protocollo": str(record.get("protocollo", "")),
            "data": str(record.get("data", "")),
            "denunciante_nome": str(record.get("denunciante_nome", "")),
            "denunciante_indirizzo": str(record.get("denunciante_indirizzo", "")),
            "straniero_nome": str(record.get("straniero_nome", "")),
            "straniero_indirizzo": str(record.get("straniero_indirizzo", "")),
            "motivo": str(record.get("motivo", "")),
            "indirizzo_ospitalita": str(record.get("indirizzo_ospitalita", "")),
        }
        mode = str(record.get("mode", ""))
        if mode:
            item["mode"] = mode
        payload.append(item)
    return payload


def write_pending_with_excel_com(workbook_path: Path, pending_records: list[dict]) -> None:
    payload = build_pending_payload(pending_records)
    ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$WorkbookPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)
$ErrorActionPreference = "Stop"
$items = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
$excel = $null
$wb = $null
$ws = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $wb = $excel.Workbooks.Open($WorkbookPath)
    $ws = $wb.Worksheets.Item(1)
    foreach ($item in $items) {
        $targetTop = $null
        $prog = [string]$item.progressivo

        $usedStart = $ws.UsedRange.Row
        $usedEnd = $ws.UsedRange.Row + $ws.UsedRange.Rows.Count - 1
        for ($r = $usedStart; $r -le $usedEnd; $r++) {
            $value = [string]$ws.Cells.Item($r, 1).Text
            if ([string]::IsNullOrWhiteSpace($value)) { continue }
            if ($value.Trim() -eq $prog.Trim()) {
                $targetTop = $r
                break
            }
        }

        if ($targetTop -eq $null) {
            if ([string]$item.mode -eq "delete_existing") {
                continue
            }
            $targetTop = $usedEnd + 1
            $ws.Cells.Item($targetTop, 1).Value2 = $prog
        }

        $mergeRows = 1
        try {
            if ($ws.Cells.Item($targetTop, 1).MergeCells) {
                $mergeRows = $ws.Cells.Item($targetTop, 1).MergeArea.Rows.Count
            }
        } catch {}
        if ($mergeRows -lt 2) { $mergeRows = 2 }
        $targetBottom = $targetTop + $mergeRows - 1

        if ([string]$item.mode -eq "delete_existing") {
            $ws.Range($ws.Cells.Item($targetTop, 1), $ws.Cells.Item($targetBottom, 6)).ClearContents()
            continue
        }

        $ws.Cells.Item($targetTop, 2).Value2 = [string]$item.protocollo
        $ws.Cells.Item($targetTop, 3).Value2 = [string]$item.data
        $ws.Cells.Item($targetTop, 4).Value2 = [string]$item.denunciante_nome
        $ws.Cells.Item($targetBottom, 4).Value2 = [string]$item.denunciante_indirizzo
        $ws.Cells.Item($targetTop, 5).Value2 = [string]$item.straniero_nome
        $ws.Cells.Item($targetBottom, 5).Value2 = [string]$item.straniero_indirizzo
        $ws.Cells.Item($targetTop, 6).Value2 = [string]$item.motivo
        $ws.Cells.Item($targetBottom, 6).Value2 = [string]$item.indirizzo_ospitalita
    }

    $wb.Save()
}
finally {
    if ($wb -ne $null) { $wb.Close($true) }
    if ($excel -ne $null) { $excel.Quit() }
}
"""
    with tempfile.TemporaryDirectory(prefix="passapp_ospitalita_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_path = tmp_path / "rows.json"
        script_path = tmp_path / "append.ps1"
        payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        script_path.write_text(ps_script, encoding="utf-8")
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-WorkbookPath",
                str(workbook_path),
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
            details = (result.stderr or result.stdout or "Errore sconosciuto").strip()
            raise RuntimeError(details)
