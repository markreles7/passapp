from __future__ import annotations

import datetime
import re
import subprocess
import tempfile
from pathlib import Path

from core.dates import parse_date
from core.pass_invalidi_excel import compute_authorization_expiry, record_numero_int, split_cognome_nome
from core.text_utils import normalize_for_match


def extract_year_from_text(text: str) -> int:
    years = [int(match.group(0)) for match in re.finditer(r"(?:19|20)\d{2}", str(text or ""))]
    return max(years) if years else -1


def resolve_authorization_template(auth_template_path: str | Path, auth_docs_dir: str | Path) -> Path | None:
    candidate = Path(auth_template_path)
    if candidate.exists():
        return candidate

    docs_dir = Path(auth_docs_dir)
    if not docs_dir.exists():
        return None

    preferred_patterns = (
        "*Guida*.doc",
        "*guida*.doc",
        "*Template*.doc",
        "*template*.doc",
        "*Guida*.docx",
        "*guida*.docx",
        "*Template*.docx",
        "*template*.docx",
    )
    for pattern in preferred_patterns:
        matches = sorted(docs_dir.glob(pattern))
        if matches:
            return matches[0]

    candidates = sorted(list(docs_dir.glob("*.doc")) + list(docs_dir.glob("*.docx")))
    for path in candidates:
        normalized = normalize_for_match(path.stem)
        if "autoriz" not in normalized:
            continue
        if re.search(r"\bn\.?\s*\d+\b", normalized):
            continue
        return path
    return None


def authorization_year_for_record(record: dict) -> int:
    year_from_source = extract_year_from_text(str(record.get("source", "")))
    if year_from_source > 0:
        return year_from_source
    date_rilascio = parse_date(record.get("rilascio"))
    if date_rilascio is not None:
        return date_rilascio.year
    return datetime.date.today().year


def find_authorization_doc_for_record(record: dict, auth_docs_dir: str | Path) -> Path | None:
    docs_dir = Path(auth_docs_dir)
    if not docs_dir.exists():
        return None

    cognome = str(record.get("cognome", "")).strip()
    nome = str(record.get("nome_proprio", "")).strip()
    if not cognome and not nome:
        cognome, nome = split_cognome_nome(record.get("nome", ""))
    numero = str(record.get("numero", "")).strip()
    year = str(authorization_year_for_record(record))
    cognome_n = normalize_for_match(cognome)
    nome_n = normalize_for_match(nome)

    candidates = sorted(list(docs_dir.glob("*.doc")) + list(docs_dir.glob("*.docx")))
    for path in candidates:
        base_n = normalize_for_match(path.stem)
        if "autoriz" not in base_n:
            continue
        if cognome_n and cognome_n not in base_n:
            continue
        if nome_n and nome_n not in base_n:
            continue
        if numero and numero not in base_n:
            continue
        if year and year not in base_n:
            continue
        return path

    for path in candidates:
        base_n = normalize_for_match(path.stem)
        if "autoriz" in base_n and numero and numero in base_n:
            return path
    return None


def clean_filename_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(value or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "Senza nome"


def build_authorization_output_path(
    docs_dir: str | Path,
    template_path: str | Path,
    *,
    cognome: str,
    nome: str,
    numero: int,
    year: int,
) -> Path:
    stem = f"{clean_filename_part(cognome.upper())} {clean_filename_part(nome.title())} Autoriz. disabili n. {numero} {year}"
    return Path(docs_dir) / f"{stem}{Path(template_path).suffix}"


def build_authorization_payload(
    record: dict,
    *,
    protocol_number: str,
    protocol_date: datetime.date,
    sesso: str,
    cognome: str,
    nome: str,
    luogo_nascita: str,
    data_nascita: datetime.date,
    comune_residenza: str,
    indirizzo_residenza: str,
    data_scadenza: datetime.date,
    comune_emissione: str,
) -> dict[str, object]:
    numero = record_numero_int(record)
    if numero is None:
        raise ValueError("Numero autorizzazione non valido.")
    sesso_clean = str(sesso or "").strip().upper()
    if sesso_clean not in {"F", "M"}:
        raise ValueError("Sesso non valido.")
    return {
        "auth_number": numero,
        "year": protocol_date.year,
        "release_date": protocol_date.strftime("%d/%m/%Y"),
        "expiry_date": data_scadenza.strftime("%d/%m/%Y"),
        "protocol_number": protocol_number,
        "protocol_date": protocol_date.strftime("%d/%m/%Y"),
        "sigla": "Sig.ra" if sesso_clean == "F" else "Sig.",
        "cognome": cognome.upper(),
        "nome": nome.title(),
        "nato_word": "nata" if sesso_clean == "F" else "nato",
        "birth_place": luogo_nascita,
        "birth_date": data_nascita.strftime("%d/%m/%Y"),
        "residence_city": comune_residenza,
        "residence_address": indirizzo_residenza,
        "issue_city": comune_emissione,
        "issue_date": datetime.date.today().strftime("%d/%m/%Y"),
    }


def default_expiry(protocol_date: datetime.date, birth_date: datetime.date | None, fallback: datetime.date) -> datetime.date:
    if birth_date is None:
        return fallback
    return compute_authorization_expiry(protocol_date, birth_date)


def generate_authorization_doc_with_word(template_path: Path, output_path: Path, payload: dict) -> Path:
    ps_script = r"""
param(
    [Parameter(Mandatory=$true)][string]$TemplatePath,
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [Parameter(Mandatory=$true)][string]$AuthNumber,
    [Parameter(Mandatory=$true)][string]$Year,
    [Parameter(Mandatory=$true)][string]$ReleaseDate,
    [Parameter(Mandatory=$true)][string]$ExpiryDate,
    [Parameter(Mandatory=$true)][string]$ProtocolNumber,
    [Parameter(Mandatory=$true)][string]$ProtocolDate,
    [Parameter(Mandatory=$true)][string]$Sigla,
    [Parameter(Mandatory=$true)][string]$Cognome,
    [Parameter(Mandatory=$true)][string]$Nome,
    [Parameter(Mandatory=$true)][string]$NatoWord,
    [Parameter(Mandatory=$true)][string]$BirthPlace,
    [Parameter(Mandatory=$true)][string]$BirthDate,
    [Parameter(Mandatory=$true)][string]$ResidenceCity,
    [Parameter(Mandatory=$true)][string]$ResidenceAddress,
    [Parameter(Mandatory=$true)][string]$IssueCity,
    [Parameter(Mandatory=$true)][string]$IssueDate
)
$ErrorActionPreference = "Stop"
Copy-Item -LiteralPath $TemplatePath -Destination $OutputPath -Force
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open($OutputPath)

    function Set-ParagraphLine([object]$Doc, [string]$Pattern, [string]$NewText) {
        foreach ($par in $Doc.Paragraphs) {
            $line = [string]$par.Range.Text
            $line = $line -replace "[`r`a]", ""
            $line = $line.Trim()
            if ($line -match $Pattern) {
                $par.Range.Text = $NewText + "`r"
                return $par
            }
        }
        return $null
    }

    $null = Set-ParagraphLine $doc "AUTORIZZAZIONE\s*N\." ("AUTORIZZAZIONE N. {0}/{1}" -f $AuthNumber, $Year)
    $null = Set-ParagraphLine $doc "Rilascio del .*Validit" ("Rilascio del {0} Validita sino {1}" -f $ReleaseDate, $ExpiryDate)
    $vistaPar = Set-ParagraphLine $doc "Vista la richiesta prot\." ("Vista la richiesta prot. n. {0} del {1}" -f $ProtocolNumber, $ProtocolDate)
    if ($vistaPar -ne $null) {
        $vistaPar.Range.Font.Bold = 0
        $start = $vistaPar.Range.Start
        $vistaRange = $doc.Range($start, $start + 5)
        $vistaRange.Font.Bold = 1
    }
    $intro = if ($Sigla -eq "Sig.ra") { "Alla" } else { "Al" }
    $sigLine = ("{0} {1} {2} {3} {4} a {5} il {6} residente a {7} in {8}" -f $intro, $Sigla, $Cognome, $Nome, $NatoWord, $BirthPlace, $BirthDate, $ResidenceCity, $ResidenceAddress)
    $null = Set-ParagraphLine $doc "^(Al|Alla)\s+(Sig\.|Sig\.ra|Sig.ra|Sig)\b" $sigLine
    $null = Set-ParagraphLine $doc "PEGOGNAGA\s+il" ("{0} il {1}" -f $IssueCity.ToUpper(), $IssueDate)

    $doc.Save()
}
finally {
    if ($doc -ne $null) { $doc.Close() }
    if ($word -ne $null) { $word.Quit() }
}
"""
    with tempfile.TemporaryDirectory(prefix="passapp_auth_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_path = tmp_path / "create_auth.ps1"
        script_path.write_text(ps_script, encoding="utf-8")
        args = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-TemplatePath", str(template_path),
            "-OutputPath", str(output_path),
            "-AuthNumber", str(payload["auth_number"]),
            "-Year", str(payload["year"]),
            "-ReleaseDate", str(payload["release_date"]),
            "-ExpiryDate", str(payload["expiry_date"]),
            "-ProtocolNumber", str(payload["protocol_number"]),
            "-ProtocolDate", str(payload["protocol_date"]),
            "-Sigla", str(payload["sigla"]),
            "-Cognome", str(payload["cognome"]),
            "-Nome", str(payload["nome"]),
            "-NatoWord", str(payload["nato_word"]),
            "-BirthPlace", str(payload["birth_place"]),
            "-BirthDate", str(payload["birth_date"]),
            "-ResidenceCity", str(payload["residence_city"]),
            "-ResidenceAddress", str(payload["residence_address"]),
            "-IssueCity", str(payload["issue_city"]),
            "-IssueDate", str(payload["issue_date"]),
        ]
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "Errore sconosciuto").strip()
            raise RuntimeError(details)
    return output_path
