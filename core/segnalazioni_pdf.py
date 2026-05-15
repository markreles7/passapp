from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from core.gemini_verbale import prepare_segnalazione_pdf
from core.segnalazioni import MODALITA_OPZIONI, Segnalazione, repair_mojibake


def safe_pdf_filename(value: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", str(value or "").strip())
    safe = re.sub(r"\s+", "_", safe)
    return safe[:80] if safe else "segnalazione"


def build_pdf_payload(seg: Segnalazione) -> dict[str, str]:
    stato_label = "In corso" if seg.stato == "in_corso" else "Archiviata"
    anno = repair_mojibake(seg.anno)
    mese = repair_mojibake(seg.mese)
    giorno = repair_mojibake(seg.giorno)
    ora = repair_mojibake(seg.ora)
    data_ora = f"{giorno}/{mese}/{anno} - {ora}".strip(" -") if all((anno, mese, giorno, ora)) else "-"

    def value_or_dash(value: str) -> str:
        text = repair_mojibake(value)
        return text if text else "-"

    return {
        "numero": str(seg.numero_progressivo),
        "anno": value_or_dash(anno),
        "stato": stato_label,
        "data_ora_ricezione": data_ora,
        "nominativo": value_or_dash(seg.nominativo),
        "residenza": value_or_dash(seg.residenza),
        "indirizzo": value_or_dash(seg.indirizzo),
        "telefono": value_or_dash(seg.telefono),
        "modalita": value_or_dash(seg.modalita_segnalazione) if seg.modalita_segnalazione else MODALITA_OPZIONI[0],
        "categoria": value_or_dash(seg.categoria),
        "priorita": value_or_dash(seg.priorita),
        "stato_lavorazione": value_or_dash(seg.stato_lavorazione),
        "ricevente": value_or_dash(seg.ricevente),
        "descrizione": value_or_dash(seg.descrizione_segnalazione),
        "agente": value_or_dash(seg.agente_verificatore),
        "data_accertamento": value_or_dash(seg.data_verifica or dt.date.today().strftime("%d/%m/%Y")),
        "verifica": value_or_dash(seg.verifica_effettuata),
        "riferimento": f"{seg.numero_progressivo}/{value_or_dash(anno)}",
    }


def render_segnalazione_pdf(
    payload: dict[str, Any],
    output_pdf: Path,
    *,
    include_raw_fields: bool = False,
) -> Path:
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["include_raw_fields"] = bool(include_raw_fields)
    payload["testo_segnalazione_generato"], payload["testo_generato_da"] = prepare_segnalazione_pdf(payload)
    ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)

$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param(
        [object]$Selection,
        [string]$Text,
        [int]$Size = 9,
        [bool]$Bold = $false,
        [int]$Alignment = 0,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = $Alignment
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

function Add-LeftRightLine {
    param(
        [object]$Selection,
        [string]$LeftText,
        [string]$RightText,
        [double]$RightTab,
        [int]$Size = 9,
        [bool]$BoldLeft = $false,
        [bool]$BoldRight = $false,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = 0
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.ParagraphFormat.TabStops.ClearAll()
    $null = $Selection.ParagraphFormat.TabStops.Add($RightTab, 2, 0)
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($BoldLeft) { 1 } else { 0 }
    $Selection.TypeText($LeftText)
    $Selection.TypeText("`t")
    $Selection.Font.Bold = if ($BoldRight) { 1 } else { 0 }
    $Selection.TypeText($RightText)
    $Selection.TypeParagraph()
}

function Add-InfoLine {
    param(
        [object]$Selection,
        [string]$LabelLeft,
        [string]$ValueLeft,
        [double]$MidTab,
        [string]$LabelRight = "",
        [string]$ValueRight = "",
        [int]$Size = 9,
        [int]$SpaceAfter = 2
    )
    $Selection.ParagraphFormat.Alignment = 0
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.ParagraphFormat.TabStops.ClearAll()
    if (-not [string]::IsNullOrWhiteSpace($LabelRight)) {
        $null = $Selection.ParagraphFormat.TabStops.Add($MidTab, 0, 0)
    }
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = 1
    $Selection.TypeText($LabelLeft)
    $Selection.Font.Bold = 0
    $Selection.TypeText($ValueLeft)
    if (-not [string]::IsNullOrWhiteSpace($LabelRight)) {
        $Selection.TypeText("`t")
        $Selection.Font.Bold = 1
        $Selection.TypeText($LabelRight)
        $Selection.Font.Bold = 0
        $Selection.TypeText($ValueRight)
    }
    $Selection.TypeParagraph()
}

function Compact-Text {
    param([string]$Text, [int]$MaxLength = 0)
    if ([string]::IsNullOrWhiteSpace($Text) -or $Text -eq "-") {
        return "-"
    }
    $clean = (($Text -replace "`r?`n", " ") -replace "\s{2,}", " ").Trim()
    if ($MaxLength -gt 0 -and $clean.Length -gt $MaxLength) {
        $suffix = " [testo completo in PassApp]"
        $limit = [Math]::Max(1, $MaxLength - $suffix.Length)
        return $clean.Substring(0, $limit).TrimEnd() + $suffix
    }
    return $clean
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Add()
    $sel = $word.Selection
    $pageSetup = $doc.PageSetup

    $pageSetup.TopMargin = $word.CentimetersToPoints(1.1)
    $pageSetup.BottomMargin = $word.CentimetersToPoints(1.0)
    $pageSetup.LeftMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.RightMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.HeaderDistance = $word.CentimetersToPoints(0.5)
    $pageSetup.FooterDistance = $word.CentimetersToPoints(0.5)

    $usableWidth = $pageSetup.PageWidth - $pageSetup.LeftMargin - $pageSetup.RightMargin
    $midTab = [Math]::Round($usableWidth * 0.53, 0)
    $rightTab = [Math]::Round($usableWidth, 0)

    $numero = Compact-Text -Text $payload.numero -MaxLength 20
    $stato = Compact-Text -Text $payload.stato -MaxLength 30
    $riferimento = Compact-Text -Text $payload.riferimento -MaxLength 30
    $ricezione = Compact-Text -Text $payload.data_ora_ricezione -MaxLength 40
    $nominativo = Compact-Text -Text $payload.nominativo -MaxLength 85
    $residenza = Compact-Text -Text $payload.residenza -MaxLength 85
    $indirizzo = Compact-Text -Text $payload.indirizzo -MaxLength 110
    $telefono = Compact-Text -Text $payload.telefono -MaxLength 30
    $modalita = Compact-Text -Text $payload.modalita -MaxLength 30
    $categoria = Compact-Text -Text $payload.categoria -MaxLength 45
    $priorita = Compact-Text -Text $payload.priorita -MaxLength 20
    $statoLavorazione = Compact-Text -Text $payload.stato_lavorazione -MaxLength 45
    $ricevente = Compact-Text -Text $payload.ricevente -MaxLength 60
    $descrizione = Compact-Text -Text $payload.descrizione -MaxLength 650
    $testoSegnalazione = [string]$payload.testo_segnalazione_generato
    $agente = Compact-Text -Text $payload.agente -MaxLength 60
    $dataAccertamento = Compact-Text -Text $payload.data_accertamento -MaxLength 30
    $verifica = Compact-Text -Text $payload.verifica -MaxLength 340
    $includeRawFields = $false
    if ($null -ne $payload.include_raw_fields) {
        $includeRawFields = [System.Convert]::ToBoolean($payload.include_raw_fields)
    }

    $footerRange = $doc.Sections.Item(1).Footers.Item(1).Range
    $footerRange.Text = "Documento generato automaticamente da PassApp."
    $footerRange.ParagraphFormat.Alignment = 1
    $footerRange.Font.Name = "Calibri"
    $footerRange.Font.Size = 8
    $footerRange.Font.Bold = 0

    Add-Paragraph -Selection $sel -Text "COMUNE DI PEGOGNAGA" -Size 11 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "Polizia Locale" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "RELAZIONE DI SEGNALAZIONE" -Size 12 -Bold $true -Alignment 1 -SpaceAfter 6

    Add-LeftRightLine -Selection $sel -LeftText ("Pratica n. " + $numero + " - Stato: " + $stato) -RightText ("Rif.: " + $riferimento) -RightTab $rightTab -Size 9 -BoldLeft $true -BoldRight $true -SpaceAfter 5
    Add-InfoLine -Selection $sel -LabelLeft "Data/Ora ricezione: " -ValueLeft $ricezione -MidTab $midTab -LabelRight "Modalita': " -ValueRight $modalita -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Categoria: " -ValueLeft $categoria -MidTab $midTab -LabelRight "Priorita': " -ValueRight $priorita -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Stato lavorazione: " -ValueLeft $statoLavorazione -MidTab $midTab -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Segnalante: " -ValueLeft $nominativo -MidTab $midTab -LabelRight "Operatore ricevente: " -ValueRight $ricevente -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Residenza: " -ValueLeft $residenza -MidTab $midTab -LabelRight "Telefono: " -ValueRight $telefono -Size 9 -SpaceAfter 2
    Add-InfoLine -Selection $sel -LabelLeft "Indirizzo: " -ValueLeft $indirizzo -MidTab $midTab -Size 9 -SpaceAfter 5

    Add-Paragraph -Selection $sel -Text "RELAZIONE DESCRITTIVA DELLA SEGNALAZIONE" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 3
    Add-Paragraph -Selection $sel -Text $testoSegnalazione -Size 10 -SpaceAfter 7

    if ($includeRawFields) {
        Add-Paragraph -Selection $sel -Text "ALLEGATO INTERNO - DATI ORIGINALI REGISTRATI" -Size 9 -Bold $true -SpaceAfter 3
        Add-Paragraph -Selection $sel -Text "CONTENUTO ORIGINALE REGISTRATO" -Size 9 -Bold $true -SpaceAfter 2
        Add-Paragraph -Selection $sel -Text $descrizione -Size 9 -SpaceAfter 5
        Add-Paragraph -Selection $sel -Text "ATTIVITA' DI ACCERTAMENTO" -Size 9 -Bold $true -SpaceAfter 2
        Add-Paragraph -Selection $sel -Text ("Agente accertatore: " + $agente + "    Data accertamento: " + $dataAccertamento) -Size 9 -SpaceAfter 2
        Add-Paragraph -Selection $sel -Text ("Riscontro registrato in app: " + $verifica) -Size 9 -SpaceAfter 5
    }

    Add-Paragraph -Selection $sel -Text "Firma operatore ricevente: ____________________" -Size 9 -Alignment 2 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text "Firma agente accertatore: ____________________" -Size 9 -Alignment 2 -SpaceAfter 0

    $doc.ExportAsFixedFormat($PdfPath, 17)
    $doc.Close($false)
    $doc = $null
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
    with tempfile.TemporaryDirectory(prefix="passapp_segn_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_path = tmp_path / "payload.json"
        script_path = tmp_path / "export.ps1"

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
            details = (result.stderr or result.stdout or "Errore sconosciuto").strip()
            raise RuntimeError(details)

    if not output_pdf.exists():
        raise RuntimeError("Il file PDF non e stato creato.")
    return output_pdf
