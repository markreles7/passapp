from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app_config import load_config, resolve_path
from core.fascicoli import list_attachments, relative_to_path
from core.gemini_verbale import generate_photo_caption_with_ai, prepare_sopralluogo_verbale
from core.sopralluoghi import Sopralluogo

APP_CONFIG = load_config()
PATHS = APP_CONFIG["paths"]
SEGNALAZIONI_PDF_DIR = resolve_path(PATHS["segnalazioni_pdf_dir"])
VERBALE_SOPRALLUOGO_TEMPLATE = resolve_path(PATHS.get("verbale_sopralluogo_template", "templates/verbale_sopralluogo.doc"))
PHOTO_CAPTION_FALLBACK = "Foto allegata al sopralluogo."


def safe_pdf_filename(value: str) -> str:
    text = re.sub(r"\s+", "_", str(value or "").strip())
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("._") or "sopralluogo"


def build_verbale_recipients(ufficio: str) -> list[str]:
    text = str(ufficio or "").strip()
    normalized = _normalize_text(text)
    recipients: list[str] = []
    if not text or "polizia locale" in normalized:
        recipients.extend(["AL COMANDANTE DEL SERVIZIO DI POLIZIA LOCALE", "Sede"])
    if "tecnico" in normalized:
        recipients.extend(["AL RESPONSABILE DEL SETTORE TECNICO", "Sede"])
    if not recipients and text and text != "-":
        if normalized.startswith(("al ", "alla ", "all'", "a ")):
            recipients.extend([text.upper(), "Sede"])
        else:
            recipients.extend([f"A {text}", "Sede"])
    return recipients or ["AL COMANDANTE DEL SERVIZIO DI POLIZIA LOCALE", "Sede"]


def build_verbale_subject(payload: dict[str, Any]) -> str:
    seg_num = value_or_dash(payload.get("segnalazione_numero", ""))
    luogo = value_or_dash(payload.get("luogo", "") or payload.get("indirizzo_segnalazione", ""))
    categoria = value_or_dash(payload.get("categoria", ""))
    descrizione = compact_subject_text(str(payload.get("descrizione", "")))
    if categoria != "-" and luogo != "-":
        return f"Sopralluogo per segnalazione {categoria.lower()} in {luogo} - segnalazione n. {seg_num}"
    if descrizione != "-" and luogo != "-":
        return f"Sopralluogo per segnalazione in {luogo}: {descrizione} - n. {seg_num}"
    if luogo != "-":
        return f"Sopralluogo relativo alla segnalazione n. {seg_num} in {luogo}"
    return f"Sopralluogo relativo alla segnalazione n. {seg_num}"


def compact_subject_text(value: str, max_length: int = 90) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return "-"
    text = text.rstrip(".")
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(" ", 1)[0].rstrip(" ,.;:") + "..."


def build_pdf_payload(segnalazione, item: Sopralluogo, registry_path: Path | None = None) -> dict[str, Any]:
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

    attachments = list_attachments(int(getattr(segnalazione, "numero_progressivo")), registry_path=registry_path) if registry_path else list_attachments(int(getattr(segnalazione, "numero_progressivo")))
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
        "categoria": value_or_dash(getattr(segnalazione, "categoria", "")),
        "priorita": value_or_dash(getattr(segnalazione, "priorita", "")),
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
        "data_generazione": dt.date.today().strftime("%d/%m/%Y"),
        "oggetto_verbale": "",
        "foto_count": str(len(photos)),
        "documenti_count": str(len(documents)),
        "allegati_count": str(len(photos) + len(documents)),
        "firma_operatori": value_or_dash(item.operatori),
    }


def enrich_photo_descriptions_with_ai(payload: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or load_config(force_reload=True)
    for photo in payload.get("foto_items", []):
        if not isinstance(photo, dict):
            continue
        current_description = str(photo.get("descrizione") or "").strip()
        if current_description:
            photo["descrizione"] = current_description
            continue
        generated = generate_photo_caption_with_ai(photo.get("path", ""), payload, config=config)
        photo["descrizione"] = generated or PHOTO_CAPTION_FALLBACK
    return payload


def render_sopralluogo_pdf(segnalazione, item: Sopralluogo, output_pdf: Path) -> Path:
    output_pdf = Path(output_pdf)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    payload = build_pdf_payload(segnalazione, item)
    config = load_config(force_reload=True)
    payload["oggetto_verbale"] = build_verbale_subject(payload)
    payload["destinatari"] = build_verbale_recipients(payload.get("ufficio", ""))
    enrich_photo_descriptions_with_ai(payload, config=config)
    payload["verbale_generato"], payload["testo_generato_da"] = prepare_sopralluogo_verbale(payload, config=config)
    if VERBALE_SOPRALLUOGO_TEMPLATE.exists():
        return render_sopralluogo_pdf_from_template(VERBALE_SOPRALLUOGO_TEMPLATE, payload, output_pdf)
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

function Add-Section {
    param([object]$Selection, [string]$Text)
    Add-Paragraph -Selection $Selection -Text $Text -Size 10 -Bold $true -SpaceAfter 1
    Add-Paragraph -Selection $Selection -Text "________________________________________________________________________________" -Size 6 -SpaceAfter 4
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
        $caption = [string]$Photo.descrizione
        if ($caption -eq "") { $caption = "Foto allegata al sopralluogo." }
        Add-Paragraph -Selection $Selection -Text $caption -Size 9 -Alignment 1 -SpaceAfter 8
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

    Add-Paragraph -Selection $sel -Text "COMUNE DI PEGOGNAGA" -Size 13 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "Polizia Locale" -Size 10 -Bold $true -Alignment 1 -SpaceAfter 1
    Add-Paragraph -Selection $sel -Text "VERBALE DI SOPRALLUOGO" -Size 14 -Bold $true -Alignment 1 -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text ("Generato il " + $payload.data_generazione) -Size 8 -Alignment 1 -SpaceAfter 8

    Add-Section -Selection $sel -Text "Oggetto"
    Add-Paragraph -Selection $sel -Text $payload.oggetto_verbale -Size 9 -SpaceAfter 4

    Add-Section -Selection $sel -Text "Dati segnalazione"
    Add-Info -Selection $sel -Label "Segnalazione n.: " -Value $payload.segnalazione_numero
    Add-Info -Selection $sel -Label "Data ricezione: " -Value $payload.segnalazione_data
    Add-Info -Selection $sel -Label "Segnalante: " -Value $payload.segnalante
    Add-Info -Selection $sel -Label "Luogo segnalato: " -Value $payload.indirizzo_segnalazione
    Add-Info -Selection $sel -Label "Oggetto: " -Value $payload.descrizione

    Add-Section -Selection $sel -Text "Dati sopralluogo"
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

    Add-Section -Selection $sel -Text "Verbale operativo"
    Add-Paragraph -Selection $sel -Text ([string]$payload.verbale_generato) -Size 9 -SpaceAfter 6

    Add-Section -Selection $sel -Text "Riepilogo allegati"
    Add-Info -Selection $sel -Label "Foto nel fascicolo: " -Value $payload.foto_count
    Add-Info -Selection $sel -Label "Documenti/allegati: " -Value $payload.documenti_count
    Add-Info -Selection $sel -Label "Totale allegati richiamati: " -Value $payload.allegati_count
    Add-Paragraph -Selection $sel -Text "Il presente verbale richiama gli allegati presenti nel fascicolo digitale della segnalazione alla data di generazione." -Size 8 -SpaceAfter 8

    Add-Section -Selection $sel -Text "Sottoscrizione"
    Add-Paragraph -Selection $sel -Text "Letto, confermato e sottoscritto." -Size 9 -SpaceAfter 10
    Add-Paragraph -Selection $sel -Text "L'operatore / Gli operatori" -Size 9 -Bold $true -SpaceAfter 2
    Add-Paragraph -Selection $sel -Text $payload.firma_operatori -Size 9 -SpaceAfter 12
    Add-Paragraph -Selection $sel -Text "Firma: ________________________________________________" -Size 9 -SpaceAfter 4

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


def _normalize_text(value: str) -> str:
    text = str(value or "").lower()
    replacements = {
        "à": "a",
        "è": "e",
        "é": "e",
        "ì": "i",
        "ò": "o",
        "ù": "u",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def render_sopralluogo_pdf_from_template(template_path: Path, payload: dict[str, Any], output_pdf: Path) -> Path:
    ps_script = r"""
param(
    [Parameter(Mandatory = $true)][string]$TemplatePath,
    [Parameter(Mandatory = $true)][string]$PdfPath,
    [Parameter(Mandatory = $true)][string]$PayloadPath
)
$ErrorActionPreference = "Stop"
$payload = Get-Content -Path $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json

function Add-Paragraph {
    param([object]$Selection, [string]$Text, [int]$Size = 10, [bool]$Bold = $false, [int]$Alignment = 0, [int]$SpaceAfter = 4)
    $Selection.ParagraphFormat.Alignment = $Alignment
    $Selection.ParagraphFormat.SpaceAfter = $SpaceAfter
    $Selection.Font.Name = "Calibri"
    $Selection.Font.Size = $Size
    $Selection.Font.Bold = if ($Bold) { 1 } else { 0 }
    $Selection.TypeText($Text)
    $Selection.TypeParagraph()
}

function Add-LongText {
    param([object]$Selection, [string]$Text, [int]$Size = 10, [int]$SpaceAfter = 6)
    $normalized = ([string]$Text).Replace("`r`n", "`n").Replace("`r", "`n")
    $parts = $normalized -split "`n`n"
    foreach ($part in $parts) {
        $clean = $part.Trim()
        if ($clean -ne "") {
            Add-Paragraph -Selection $Selection -Text $clean -Size $Size -SpaceAfter $SpaceAfter
        }
    }
}

function Add-PageBreak {
    param([object]$Selection)
    $Selection.InsertBreak(7)
}

function Replace-Token {
    param([object]$Document, [string]$Token, [string]$Value)
    $range = $Document.Content
    $find = $range.Find
    $find.ClearFormatting()
    $find.Replacement.ClearFormatting()
    [void]$find.Execute($Token, $false, $true, $false, $false, $false, $true, 1, $false, $Value, 2)
}

function Select-Placeholder {
    param([object]$Document, [object]$Word, [string]$Token, [bool]$AppendIfMissing = $true)
    $range = $Document.Content
    $find = $range.Find
    $find.ClearFormatting()
    if ($find.Execute($Token, $false, $true, $false, $false, $false, $true, 1)) {
        $range.Text = ""
        $range.Select()
        return $true
    }
    if (-not $AppendIfMissing) {
        return $false
    }
    $end = $Document.Range($Document.Content.End - 1, $Document.Content.End - 1)
    $end.Select()
    $Word.Selection.TypeParagraph()
    return $false
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
        $caption = [string]$Photo.descrizione
        if ($caption -eq "") { $caption = [string]$Photo.nome_file }
        Add-Paragraph -Selection $Selection -Text $caption -Size 9 -Alignment 1 -SpaceAfter 8
    } catch {
        Add-Paragraph -Selection $Selection -Text ("Foto non inserita: " + [string]$Photo.nome_file) -Size 8 -SpaceAfter 4
    }
}

$word = $null
$doc = $null
$workDoc = [System.IO.Path]::ChangeExtension($PdfPath, ".doc")
try {
    Copy-Item -Path $TemplatePath -Destination $workDoc -Force
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open($workDoc)
    $clearRange = $doc.Range()
    [void]$clearRange.Delete()
    $doc.Range(0, 0).Select()
    $sel = $word.Selection

    Add-Paragraph -Selection $sel -Text "Prot." -Size 10 -SpaceAfter 12
    foreach ($destinatario in @($payload.destinatari)) {
        Add-Paragraph -Selection $sel -Text ([string]$destinatario) -Size 10 -Alignment 2 -SpaceAfter 1
    }
    Add-Paragraph -Selection $sel -Text "" -Size 10 -SpaceAfter 10
    Add-Paragraph -Selection $sel -Text ("OGGETTO: " + $payload.oggetto_verbale) -Size 10 -Bold $true -SpaceAfter 8
    Add-LongText -Selection $sel -Text ([string]$payload.verbale_generato) -Size 10 -SpaceAfter 7
    Add-Paragraph -Selection $sel -Text "Gli Operatori di Polizia Locale" -Size 10 -Alignment 1 -SpaceAfter 8
    Add-Paragraph -Selection $sel -Text ([string]$payload.firma_operatori + " _______________________________") -Size 10 -Alignment 1 -SpaceAfter 4

    Add-PageBreak -Selection $sel
    Add-Paragraph -Selection $sel -Text "Documentazione fotografica" -Size 11 -Bold $true -SpaceAfter 6
    $photos = @($payload.foto_items)
    if ($photos.Count -eq 0) {
        Add-Paragraph -Selection $sel -Text "Nessuna foto presente nel fascicolo digitale al momento della generazione." -Size 9 -SpaceAfter 4
    }
    foreach ($photo in $photos) {
        Add-Photo -Selection $sel -Word $word -Photo $photo
    }

    $documents = @($payload.documenti)
    if ($documents.Count -gt 0) {
        Add-PageBreak -Selection $sel
        Add-Paragraph -Selection $sel -Text "Allegati richiamati" -Size 11 -Bold $true -SpaceAfter 6
        Add-Paragraph -Selection $sel -Text ("Foto: " + $payload.foto_count + " - Documenti: " + $payload.documenti_count) -Size 9 -SpaceAfter 4
        foreach ($document in $documents) {
            Add-Paragraph -Selection $sel -Text ("- " + [string]$document.nome_file + " (" + [string]$document.tipo + ", " + [string]$document.origine + ")") -Size 9 -SpaceAfter 2
        }
    }

    $doc.Save()
    $doc.ExportAsFixedFormat($PdfPath, 17)
    $doc.Close($false)
    $doc = $null
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
    with tempfile.TemporaryDirectory(prefix="passapp_sopr_template_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        payload_path = tmp_path / "payload.json"
        script_path = tmp_path / "verbale_sopralluogo_template.ps1"
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
                "-TemplatePath",
                str(template_path),
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
