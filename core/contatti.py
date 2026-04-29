from __future__ import annotations

import csv
import datetime as dt
import json
import os
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app_config import resolve_path
from core.contatti_seed import INITIAL_CONTACTS

CONTATTI_FILE = resolve_path("data/contatti.json")
CONTATTI_BACKUP_DIR = resolve_path("data/backups/contatti")
CONTATTI_CATEGORIE = (
    "Comune",
    "Polizia Locale",
    "Ufficio tecnico",
    "Segnalazioni e manutenzioni",
    "Servizi sociali",
    "Protocollo",
    "Tributi",
    "Emergenza",
    "Forze di Polizia",
    "Sanità",
    "Farmacia",
    "Ambiente e rifiuti",
    "Provincia",
    "Prefettura",
    "Questura",
    "Vigili del Fuoco",
    "Protezione Civile",
    "Altro",
)
CATEGORY_ALIASES = {
    "Ufficio Tecnico": "Ufficio tecnico",
    "Servizi Sociali": "Servizi sociali",
    "ASL/ATS": "Sanità",
    "Ditta manutenzione": "Segnalazioni e manutenzioni",
    "Ditta segnaletica": "Segnalazioni e manutenzioni",
    "Ditta rimozione": "Segnalazioni e manutenzioni",
    "Ufficio interno": "Comune",
    "Anagrafe": "Comune",
    "Regione": "Altro",
    "Scuola": "Servizi sociali",
}
EMAIL_RE = re.compile(r"^[^@\s;]+@[^@\s;]+\.[^@\s;]+$")


@dataclass
class Contatto:
    id: str
    nome: str
    categoria: str = "Altro"
    referente: str = ""
    telefono: str = ""
    cellulare: str = ""
    email: str = ""
    pec: str = ""
    indirizzo: str = ""
    orari: str = ""
    note: str = ""
    tags: list[str] | None = None
    fonte: str = ""
    data_creazione: str = ""
    data_ultima_modifica: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Contatto | None:
        contact_id = str(raw.get("id", "")).strip()
        if not contact_id or contact_id == "0":
            return None
        nome = str(raw.get("nome", "")).strip()
        if not nome:
            return None
        return cls(
            id=contact_id,
            nome=nome,
            categoria=normalize_categoria(str(raw.get("categoria", "Altro"))),
            referente=str(raw.get("referente", "")).strip(),
            telefono=normalize_phone(str(raw.get("telefono", ""))),
            cellulare=normalize_phone(str(raw.get("cellulare", ""))),
            email=str(raw.get("email", "")).strip(),
            pec=str(raw.get("pec", "")).strip(),
            indirizzo=str(raw.get("indirizzo", "")).strip(),
            orari=str(raw.get("orari", raw.get("orari_note", ""))).strip(),
            note=str(raw.get("note", raw.get("note_operative", ""))).strip(),
            tags=normalize_tags(raw.get("tags", [])),
            fonte=str(raw.get("fonte", "")).strip(),
            data_creazione=str(raw.get("data_creazione", "")).strip(),
            data_ultima_modifica=str(raw.get("data_ultima_modifica", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tags"] = normalize_tags(self.tags)
        return payload


def load_contatti(path: Path = CONTATTI_FILE) -> tuple[list[Contatto], str | None]:
    imported, warning = seed_contacts_if_empty(path)
    if warning:
        return [], warning
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        backup = backup_malformed_file(path)
        return [], f"File contatti non valido. Backup creato: {backup}"
    except OSError as exc:
        return [], f"File contatti non leggibile: {exc}"
    contatti, format_warning = contacts_from_payload(payload)
    warning_text = f"Importati {imported} contatti iniziali." if imported else format_warning
    return sort_contatti(contatti), warning_text


def save_contatti(contatti: list[Contatto], path: Path = CONTATTI_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="contatti_", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"contatti": [item.to_dict() for item in contatti]}, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            backup_contacts_file(path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def seed_contacts_if_empty(path: Path = CONTATTI_FILE) -> tuple[int, str | None]:
    if path.exists() and path.stat().st_size > 0:
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except json.JSONDecodeError:
            backup = backup_malformed_file(path)
            return 0, f"File contatti non valido. Backup creato: {backup}. Il file originale non e stato sovrascritto."
        except OSError as exc:
            return 0, f"File contatti non leggibile: {exc}"
        contatti, warning = contacts_from_payload(payload)
        if contatti or warning:
            return 0, warning
    seed = build_seed_contacts()
    save_contatti(seed, path)
    return len(seed), None


def add_contact(contatto: Contatto, path: Path = CONTATTI_FILE) -> Contatto:
    contatti, warning = load_contatti(path)
    if warning and "non valido" in warning.lower():
        raise ValueError(warning)
    if not contatto.id or contatto.id == "0":
        contatto.id = generate_contact_id(contatti)
    if any(item.id == contatto.id for item in contatti):
        raise ValueError(f"ID contatto duplicato: {contatto.id}")
    stamp_contact(contatto, created=True)
    contatti.append(contatto)
    save_contatti(sort_contatti(contatti), path)
    return contatto


def update_contact(contatto: Contatto, path: Path = CONTATTI_FILE) -> Contatto:
    contatti, warning = load_contatti(path)
    if warning and "non valido" in warning.lower():
        raise ValueError(warning)
    for idx, current in enumerate(contatti):
        if current.id == contatto.id:
            if not contatto.data_creazione:
                contatto.data_creazione = current.data_creazione
            stamp_contact(contatto, created=False)
            contatti[idx] = contatto
            save_contatti(sort_contatti(contatti), path)
            return contatto
    raise ValueError("Contatto non trovato.")


def upsert_contatto(contatto: Contatto, path: Path = CONTATTI_FILE) -> Contatto:
    if not contatto.id or contatto.id == "0":
        return add_contact(contatto, path)
    contatti, _warning = load_contatti(path)
    if any(item.id == contatto.id for item in contatti):
        return update_contact(contatto, path)
    return add_contact(contatto, path)


def delete_contatto(contatto_id: str, path: Path = CONTATTI_FILE) -> bool:
    contatti, _warning = load_contatti(path)
    kept = [item for item in contatti if item.id != str(contatto_id)]
    if len(kept) == len(contatti):
        return False
    save_contatti(kept, path)
    return True


def search_contacts(contatti: list[Contatto], query: str = "") -> list[Contatto]:
    return filter_contacts(contatti, query=query)


def filter_contacts(
    contatti: list[Contatto],
    query: str = "",
    categoria: str = "Tutte",
    tag: str = "Tutti",
) -> list[Contatto]:
    needle = query.strip().lower()
    tag_needle = tag.strip().lower()
    out = []
    for contact in contatti:
        if categoria != "Tutte" and contact.categoria != categoria:
            continue
        if tag_needle and tag_needle != "tutti" and tag_needle not in [item.lower() for item in normalize_tags(contact.tags)]:
            continue
        haystack = " ".join(
            [
                contact.nome,
                contact.categoria,
                contact.referente,
                contact.telefono,
                contact.cellulare,
                contact.email,
                contact.pec,
                contact.indirizzo,
                contact.orari,
                contact.note,
                contact.fonte,
                " ".join(normalize_tags(contact.tags)),
            ]
        ).lower()
        if needle and needle not in haystack:
            continue
        out.append(contact)
    return out


def filter_contatti(contatti: list[Contatto], query: str = "", categoria: str = "Tutte", tag: str = "Tutti") -> list[Contatto]:
    return filter_contacts(contatti, query=query, categoria=categoria, tag=tag)


def validate_contatto(contatto: Contatto) -> tuple[bool, str, bool]:
    if not contatto.nome.strip():
        return False, "Il nome ente/ufficio/ditta e obbligatorio.", False
    if contatto.categoria not in CONTATTI_CATEGORIE:
        return False, "Categoria non valida.", False
    invalid_emails = [value for value in split_addresses(contatto.email) if not is_valid_email(value)]
    invalid_pec = [value for value in split_addresses(contatto.pec) if not is_valid_email(value)]
    if invalid_emails or invalid_pec:
        return True, "Uno o piu indirizzi email/PEC hanno un formato da verificare.", True
    has_recapito = bool(contatto.telefono.strip() or contatto.email.strip() or contatto.pec.strip())
    if not has_recapito:
        return True, "Nessun telefono, email o PEC inserito.", True
    return True, "", False


def export_contatti_csv(contatti: list[Contatto], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Nome", "Categoria", "Referente", "Telefono", "Cellulare", "Email", "PEC", "Indirizzo", "Orari", "Note", "Tags", "Fonte"])
        for item in contatti:
            writer.writerow([
                item.nome,
                item.categoria,
                item.referente,
                item.telefono,
                item.cellulare,
                item.email,
                item.pec,
                item.indirizzo,
                item.orari,
                item.note,
                ", ".join(normalize_tags(item.tags)),
                item.fonte,
            ])
    return path


def export_contatti_txt(contatti: list[Contatto], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["CONTATTI UTILI", ""]
    for item in contatti:
        lines.extend(
            [
                f"{item.nome} ({item.categoria})",
                f"Referente: {item.referente or '-'}",
                f"Telefono: {item.telefono or '-'}",
                f"Cellulare: {item.cellulare or '-'}",
                f"Email: {item.email or '-'}",
                f"PEC: {item.pec or '-'}",
                f"Indirizzo: {item.indirizzo or '-'}",
                f"Orari: {item.orari or '-'}",
                f"Note: {item.note or '-'}",
                f"Tags: {', '.join(normalize_tags(item.tags)) or '-'}",
                f"Fonte: {item.fonte or '-'}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def export_contacts_txt(contatti: list[Contatto], path: Path) -> Path:
    return export_contatti_txt(contatti, path)


def export_contacts_csv(contatti: list[Contatto], path: Path) -> Path:
    return export_contatti_csv(contatti, path)


def backup_contacts_file(path: Path = CONTATTI_FILE) -> Path | None:
    if not path.exists():
        return None
    backup_dir = backup_dir_for(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def backup_malformed_file(path: Path) -> Path:
    backup_dir = backup_dir_for(path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{path.stem}_malformed_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    shutil.copy2(path, backup)
    return backup


def backup_dir_for(path: Path) -> Path:
    try:
        if path.resolve() == CONTATTI_FILE.resolve():
            return CONTATTI_BACKUP_DIR
    except OSError:
        pass
    return path.parent / "backups" / "contatti"


def contacts_from_payload(payload: Any) -> tuple[list[Contatto], str | None]:
    items = payload.get("contatti", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return [], "Formato contatti non valido: lista mancante."
    contacts = [contact for item in items if isinstance(item, dict) for contact in [Contatto.from_dict(item)] if contact]
    return contacts, None


def build_seed_contacts() -> list[Contatto]:
    now = now_timestamp()
    contacts: list[Contatto] = []
    seen: set[str] = set()
    for raw in INITIAL_CONTACTS:
        contact = Contatto.from_dict({**raw, "data_creazione": now, "data_ultima_modifica": now})
        if contact and contact.id not in seen:
            contacts.append(contact)
            seen.add(contact.id)
    return contacts


def stamp_contact(contatto: Contatto, *, created: bool) -> None:
    now = now_timestamp()
    if created or not contatto.data_creazione:
        contatto.data_creazione = now
    contatto.data_ultima_modifica = now
    contatto.categoria = normalize_categoria(contatto.categoria)
    contatto.telefono = normalize_phone(contatto.telefono)
    contatto.cellulare = normalize_phone(contatto.cellulare)
    contatto.tags = normalize_tags(contatto.tags)


def generate_contact_id(contatti: list[Contatto]) -> str:
    existing = {item.id for item in contatti}
    while True:
        candidate = f"contatto-{uuid4().hex[:8]}"
        if candidate not in existing:
            return candidate


def next_contatto_id(contatti: list[Contatto]) -> str:
    return generate_contact_id(contatti)


def normalize_categoria(value: str) -> str:
    text = str(value or "").strip() or "Altro"
    text = CATEGORY_ALIASES.get(text, text)
    return text if text in CONTATTI_CATEGORIE else "Altro"


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_tags = re.split(r"[,;]", value)
    elif isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = []
    seen: set[str] = set()
    tags: list[str] = []
    for raw in raw_tags:
        tag = str(raw).strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
    return tags


def available_tags(contatti: list[Contatto]) -> tuple[str, ...]:
    tags = sorted({tag for item in contatti for tag in normalize_tags(item.tags)}, key=str.lower)
    return tuple(tags)


def normalize_phone(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^\d+ /]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_addresses(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[;,]", str(value or "")) if item.strip()]


def is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(str(value or "").strip()))


def sort_contatti(contatti: list[Contatto]) -> list[Contatto]:
    return sorted(contatti, key=lambda item: (item.nome.lower(), item.id))


def now_timestamp() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


load_contacts = load_contatti
save_contacts = save_contatti
delete_contact = delete_contatto
filter_contacts_alias = filter_contatti
backup_contacts_file_alias = backup_contacts_file
