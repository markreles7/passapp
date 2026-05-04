from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app_config import load_config, resolve_path
from core.fascicoli import list_attachments, relative_to_path
from core.sopralluoghi import Sopralluogo

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
SEGNALAZIONI_PDF_DIR = resolve_path(PATHS["segnalazioni_pdf_dir"])


def safe_pdf_filename(value: str) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip())
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("._") or "sopralluogo"


def build_pdf_payload(segnalazione, item: Sopralluogo) -> dict[str, Any]:
    data_seg = "/".join(
        part
        for part in (
            str(getattr(segnalazione, "giorno", "")),
            str(getattr(segnalazione, "mese", "")),
            str(getattr(segnalazione, "anno", "")),
        )
        if part
    )
    data_ora = item.data_sopralluogo
    if item.ora_sopralluogo:
        data_ora = f"{data_ora} - {item.ora_sopralluogo}"

    attachments = list_attachments(int(getattr(segnalazione, "numero_progressivo")))
    photos = []
    documents = []
    for attachment in attachments:
        path = relative_to_path(attachment.relative_path)
        entry = {
            "nome_file": attachment.nome_file,
            "path": str(path),
            "tipo": attachment.tipo,
            "origine": attachment_origin_text(attachment),
            "descrizione": attachment.descrizione,
        }
        if attachment.tipo == "foto" and path.exists():
            photos.append(entry)
        elif path.exists():
            documents.append(entry)

    return {
        "segnalazione_numero": str(getattr(segnalazione, "numero_progressivo")),
        "segnalazione_data": value_or_dash(data_seg),
        "segnalante": value_or_dash(getattr(segnalazione, "nominativo", "")),
        "descrizione": value_or_dash(getattr(segnalazione, "descrizione_segnalazione", "")),
        "indirizzo_segnalazione": value_or_dash(getattr(segnalazione, "indirizzo", "")),
        "id_sopralluogo": str(item.id_sopralluogo),
        "stato": value_or_dash(item.stato),
        "data_ora": value_or_dash(data_ora),
        "luogo": value_or_dash(item.luogo),
        "operatori": value_or_dash(item.operatori),
        "esito": value_or_dash(item.esito),
        "note": value_or_dash(item.note_operative),
        "foto": "Si" if item.presenza_foto_allegati else "No",
        "atti": "Si" if item.ulteriori_atti else "No",
        "ufficio": value_or_dash(item.ufficio_destinatario),
        "foto_items": photos,
        "documenti": documents,
    }


def render_sopralluogo_pdf(segnalazione, item: Sopralluogo, output_pdf: Path) -> Path:
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pdf_payload(segnalazione, item)
    ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)
$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param([object]$Selection, [string]$Text, [int]$Size = 9, [bool]$Bold = $false, [int]$Alignment = 0, [int]$SpaceAfter = 3)
    $Selection.ParagraphFormat.Alignment = $Alignment
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

function Add-Info {
    param([object]$Selection, [string]$Label, [string]$Value)
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = 9
    $Selection.Font.Bold = 1
    $Selection.TypeText($Label)
    $Selection.Font.Bold = 0
    $Selection.TypeText($Value)
    $Selection.TypeParagraph()
}

function Add-PageBreak {
    param([object]$Selection)
    $Selection.InsertBreak(7)
}

function Add-Photo {
    param([object]$Selection, [object]$Word, [object]$Photo)
    if (-not (Test-Path ([string]$Photo.path))) { return }
    try {
        $shape = $Selection.InlineShapes.AddPicture([string]$Photo.path, $false, $true)
        $maxWidth = $Word.CentimetersToPoints(15.5)
        $maxHeight = $Word.CentimetersToPoints(9)
        if ($shape.Width -gt $maxWidth) {
            $ratio = $maxWidth / $shape.Width
            $shape.Width = $maxWidth
            $shape.Height = $shape.Height * $ratio
        }
        if ($shape.Height -gt $maxHeight) {
            $ratio = $maxHeight / $shape.Height
            $shape.Height = $maxHeight
            $shape.Width = $shape.Width * $ratio
        }
        $Selection.TypeParagraph()
        Add-Paragraph -Selection $Selection -Text ("Foto: " + [string]$Photo.nome_file + " - " + [string]$Photo.origine) -Size 8 -SpaceAfter 6
    } catch {
        Add-Paragraph -Selection $Selection -Text ("Foto non inserita: " + [string]$Photo.nome_file) -Size 8 -SpaceAfter 4
    }
}

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Add()
    $sel = $word.Selection
    $pageSetup = $doc.PageSetup
    $pageSetup.TopMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.BottomMargin = $word.CentimetersToPoints(1.2)
    $pageSetup.LeftMargin = $word.CentimetersToPoints(1.4)
    $pageSetup.RightMargin = $word.CentimetersToPoints(1.4)

    Add-Paragraph -Selection $sel -Text "COMUNE DI PEGOGNAGA" -Size 12 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "Polizia Locale" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text "VERBALE DI SOPRALLUOGO" -Size 13 -Bold $true -Alignment 1 -SpaceAfter 8

    Add-Paragraph -Selection $sel -Text "Dati segnalazione" -Size 10 -Bold $true -SpaceAfter 2
    Add-Info -Selection $sel -Label "Segnalazione n.: " -Value $payload.segnalazione_numero
    Add-Info -Selection $sel -Label "Data ricezione: " -Value $payload.segnalazione_data
    Add-Info -Selection $sel -Label "Segnalante: " -Value $payload.segnalante
    Add-Info -Selection $sel -Label "Luogo segnalato: " -Value $payload.indirizzo_segnalazione
    Add-Info -Selection $sel -Label "Oggetto: " -Value $payload.descrizione
    Add-Paragraph -Selection $sel -Text "" -SpaceAfter 4

    Add-Paragraph -Selection $sel -Text "Dati sopralluogo" -Size 10 -Bold $true -SpaceAfter 2
    Add-Info -Selection $sel -Label "ID sopralluogo: " -Value $payload.id_sopralluogo
    Add-Info -Selection $sel -Label "Stato: " -Value $payload.stato
    Add-Info -Selection $sel -Label "Data/Ora: " -Value $payload.data_ora
    Add-Info -Selection $sel -Label "Luogo: " -Value $payload.luogo
    Add-Info -Selection $sel -Label "Operatore/i: " -Value $payload.operatori
    Add-Info -Selection $sel -Label "Esito: " -Value $payload.esito
    Add-Info -Selection $sel -Label "Note operative: " -Value $payload.note
    Add-Info -Selection $sel -Label "Foto/allegati: " -Value $payload.foto
    Add-Info -Selection $sel -Label "Ulteriori atti: " -Value $payload.atti
    Add-Info -Selection $sel -Label "Ufficio destinatario: " -Value $payload.ufficio
    Add-Paragraph -Selection $sel -Text "" -SpaceAfter 4

    Add-Paragraph -Selection $sel -Text "Verbale operativo" -Size 10 -Bold $true -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text ("In data " + $payload.data_ora + " l'operatore/gli operatori indicati hanno effettuato il sopralluogo presso il luogo sopra riportato, in relazione alla segnalazione n. " + $payload.segnalazione_numero + ".") -Size 9 -SpaceAfter 3
    Add-Paragraph -Selection $sel -Text ("Esito sintetico: " + $payload.esito) -Size 9 -SpaceAfter 3
    Add-Paragraph -Selection $sel -Text ("Note operative: " + $payload.note) -Size 9 -SpaceAfter 3
    Add-Paragraph -Selection $sel -Text ("Necessita di ulteriori atti: " + $payload.atti + ". Ufficio destinatario: " + $payload.ufficio + ".") -Size 9 -SpaceAfter 3

    Add-PageBreak -Selection $sel
    Add-Paragraph -Selection $sel -Text "SCHEDA FOTOGRAFICA" -Size 12 -Bold $true -Alignment 1 -SpaceAfter 8
    $photos = @($payload.foto_items)
    if ($photos.Count -eq 0) {
        Add-Paragraph -Selection $sel -Text "Nessuna foto presente nel fascicolo digitale al momento della generazione." -Size 9 -SpaceAfter 3
    } else {
        foreach ($photo in $photos) {
            Add-Photo -Selection $sel -Word $word -Photo $photo
        }
    }

    $documents = @($payload.documenti)
    if ($documents.Count -gt 0) {
        Add-PageBreak -Selection $sel
        Add-Paragraph -Selection $sel -Text "DOCUMENTI E ALLEGATI PRESENTI NEL FASCICOLO" -Size 12 -Bold $true -Alignment 1 -SpaceAfter 8
        foreach ($document in $documents) {
            Add-Paragraph -Selection $sel -Text ("- " + [string]$document.nome_file + " (" + [string]$document.tipo + ", " + [string]$document.origine + ")") -Size 9 -SpaceAfter 2
        }
        Add-Paragraph -Selection $sel -Text "I documenti sono elencati come allegati presenti nel fascicolo digitale; non vengono incorporati nel PDF del verbale." -Size 8 -SpaceAfter 2
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
    with tempfile.TemporaryDirectory(prefix="passapp_sopr_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_path = tmp_path / "payload.json"
        script_path = tmp_path / "scheda_sopralluogo.ps1"
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
            raise RuntimeError((result.stderr or result.stdout or "Errore sconosciuto").strip())
    if not output_pdf.exists():
        raise RuntimeError("Il file PDF non e stato creato.")
    return output_pdf


def attachment_origin_text(attachment) -> str:
    origin = str(attachment.origine or "segnalazione")
    if attachment.sopralluogo_id:
        origin = f"{origin} #{attachment.sopralluogo_id}"
    return origin


def value_or_dash(value: str) -> str:
    text = str(value or "").strip()
    return text if text else "-"
