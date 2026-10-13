from __future__ import annotations

import datetime
import re
import json
import os
import shutil
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
    from app_config import resolve_path
    neutral = resolve_path("templates/autorizzazione_pass_invalidi.doc")
    candidate = resolve_path(auth_template_path)
    legacy_names = {"tesserino disabili guida.doc", "modello autorizzazione.doc"}
    if neutral.exists() and (not candidate.exists() or candidate.name.casefold() in legacy_names):
        return neutral
    if candidate.exists():
        return candidate

    docs_dir = resolve_path(auth_docs_dir)
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
    date_rilascio = parse_date(record.get("rilascio"))
    if date_rilascio is not None:
        return date_rilascio.year
    year_from_source = extract_year_from_text(str(record.get("source", "")))
    if year_from_source > 0:
        return year_from_source
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
        if numero and not re.search(rf"\bn\.?\s*{re.escape(numero)}\b", base_n):
            continue
        if year and year not in base_n:
            continue
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
    release_date: datetime.date | None = None,
    issue_date: datetime.date | None = None,
) -> dict[str, object]:
    numero = record_numero_int(record)
    if numero is None:
        raise ValueError("Numero autorizzazione non valido.")
    sesso_clean = str(sesso or "").strip().upper()
    if sesso_clean not in {"F", "M"}:
        raise ValueError("Sesso non valido.")
    released = release_date or parse_date(record.get("rilascio")) or protocol_date
    created = issue_date or datetime.date.today()
    if data_scadenza < released:
        raise ValueError("La scadenza precede la data di rilascio.")
    if not all(str(value).strip() for value in (protocol_number, cognome, nome, luogo_nascita, comune_residenza, indirizzo_residenza)):
        raise ValueError("Dati dell'autorizzazione incompleti.")
    return {
        "auth_number": numero,
        "year": released.year,
        "release_date": released.strftime("%d/%m/%Y"),
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
        "issue_date": created.strftime("%d/%m/%Y"),
    }


def default_expiry(protocol_date: datetime.date, birth_date: datetime.date | None, fallback: datetime.date) -> datetime.date:
    if birth_date is None:
        return fallback
    return compute_authorization_expiry(protocol_date, birth_date)


def authorization_payload_for_record(record: dict) -> dict:
    protocol_date = parse_date(record.get("protocol_date"))
    release_date = parse_date(record.get("rilascio"))
    birth_date = parse_date(record.get("nato_il"))
    expiry_date = parse_date(record.get("scadenza"))
    if any(value is None for value in (protocol_date, release_date, birth_date, expiry_date)):
        raise ValueError("Completa data protocollo, rilascio, nascita e scadenza prima di creare l'autorizzazione.")
    return build_authorization_payload(
        record, protocol_number=str(record.get("protocol_number", "")), protocol_date=protocol_date,
        sesso=str(record.get("sesso", "")), cognome=str(record.get("cognome", "")),
        nome=str(record.get("nome_proprio", "")), luogo_nascita=str(record.get("luogo_nascita", "")),
        data_nascita=birth_date, comune_residenza=str(record.get("comune_residenza", "")),
        indirizzo_residenza=str(record.get("indirizzo", "")), data_scadenza=expiry_date,
        comune_emissione="PEGOGNAGA", release_date=release_date,
        issue_date=parse_date(record.get("issue_date")) or datetime.date.today(),
    )


def authorization_replacements(payload: dict) -> dict[str, str]:
    intro = "Alla Sig.ra" if payload["sigla"] == "Sig.ra" else "Al Sig."
    return {
        "AUTORIZZAZIONE_NUMERO": f"N. {payload['auth_number']}/{payload['year']}",
        "RILASCIO_VALIDITA": f"Rilascio del {payload['release_date']} Validità sino {payload['expiry_date']}",
        "PROTOCOLLO_RICHIESTA": f"prot. n. {payload['protocol_number']} del {payload['protocol_date']}",
        "DESTINATARIO": f"{intro} {payload['cognome']} {payload['nome']}",
        "NATO_NATA": str(payload["nato_word"]),
        "LUOGO_NASCITA": str(payload["birth_place"]),
        "DATA_NASCITA": str(payload["birth_date"]),
        "COMUNE_RESIDENZA": str(payload["residence_city"]),
        "INDIRIZZO_RESIDENZA": str(payload["residence_address"]),
        "DATA_DOCUMENTO": str(payload["issue_date"]),
    }


WORD_FILL_SCRIPT = r"""
param([string]$TemplatePath, [string]$OutputPath, [string]$PayloadPath)
$ErrorActionPreference = "Stop"
$replacements = Get-Content -LiteralPath $PayloadPath -Raw -Encoding UTF8 | ConvertFrom-Json
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $doc = $word.Documents.Open($TemplatePath, $false, $true)
    # Validate the entire template before changing any field.
    foreach ($entry in $replacements.PSObject.Properties) {
        $token = '{{' + $entry.Name + '}}'
        $search = $doc.Content.Duplicate
        $search.Find.ClearFormatting()
        $search.Find.Text = $token
        $search.Find.MatchWildcards = $false
        $search.Find.Wrap = 0
        $count = 0
        while ($search.Find.Execute()) { $count++; $search.Collapse(0) }
        if ($count -ne 1) { throw ("Campo modello mancante o duplicato: " + $entry.Name) }
    }
    foreach ($entry in $replacements.PSObject.Properties) {
        $search = $doc.Content.Duplicate
        $search.Find.ClearFormatting()
        $search.Find.Text = '{{' + $entry.Name + '}}'
        $search.Find.MatchWildcards = $false
        $search.Find.Wrap = 0
        if (-not $search.Find.Execute()) { throw ("Campo modello non trovato: " + $entry.Name) }
        $search.Text = [string]$entry.Value
        $search.HighlightColorIndex = 0
    }
    if ([string]$doc.Content.Text -match '\{\{[A-Z_]+\}\}') { throw "Modello contenente campi non compilati." }
    $format = if ([System.IO.Path]::GetExtension($OutputPath) -eq '.docx') { 16 } else { 0 }
    $doc.SaveAs2($OutputPath, $format)
} finally {
    if ($doc) { $doc.Close(0) }
    if ($word) { $word.Quit() }
}
"""


def generate_authorization_doc_with_word(template_path: Path, output_path: Path, payload: dict, *, overwrite: bool = False) -> Path:
    template_path, output_path = Path(template_path), Path(output_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"Modello non trovato: {template_path}")
    if template_path.resolve() == output_path.resolve():
        raise ValueError("Il documento di uscita non puo coincidere con il modello.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Autorizzazione gia esistente: {output_path.name}. Usa Apri autorizzazione.")
    if output_path.suffix.lower() not in {".doc", ".docx"}:
        raise ValueError("Formato autorizzazione non supportato.")
    replacements = authorization_replacements(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="passapp_auth_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        script_path = tmp_path / "create_auth.ps1"
        payload_path = tmp_path / "fields.json"
        script_path.write_text(WORD_FILL_SCRIPT, encoding="utf-8-sig")
        payload_path.write_text(json.dumps(replacements, ensure_ascii=True), encoding="utf-8")
        fd, temp_name = tempfile.mkstemp(prefix="pass_auth_", suffix=output_path.suffix, dir=output_path.parent)
        os.close(fd)
        temporary = Path(temp_name)
        temporary.unlink()
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path),
                 "-TemplatePath", str(template_path.resolve()), "-OutputPath", str(temporary.resolve()),
                 "-PayloadPath", str(payload_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or "Compilazione Word non riuscita.").strip())
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError("Word non ha creato il documento richiesto.")
            if overwrite:
                if output_path.exists():
                    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    shutil.copy2(output_path, output_path.with_name(f"{output_path.stem}_{stamp}.bak"))
                os.replace(temporary, output_path)
            else:
                # Windows rename refuses an existing destination, including a file
                # created by another operator while Word was generating this one.
                if output_path.exists():
                    raise FileExistsError(f"Autorizzazione gia esistente: {output_path.name}")
                os.rename(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)
    return output_path
