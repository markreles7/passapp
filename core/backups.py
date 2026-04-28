from __future__ import annotations

import datetime
import re
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_ROOT = PROJECT_ROOT / "data" / "backups"


class BackupError(RuntimeError):
    """Raised when a safety backup cannot be created."""


def _clean_filename_stem(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._-")
    return cleaned or "registro"


def create_excel_backup(
    source_path: str | Path,
    category: str,
    *,
    backup_root: str | Path = DEFAULT_BACKUP_ROOT,
    timestamp: datetime.datetime | None = None,
) -> Path:
    source = Path(source_path)
    when = timestamp or datetime.datetime.now()
    stamp = when.strftime("%Y%m%d_%H%M%S")
    clean_stem = _clean_filename_stem(source.stem)
    clean_category = _clean_filename_stem(category)
    destination_dir = Path(backup_root) / clean_category
    destination = destination_dir / f"{clean_stem}_{stamp}{source.suffix}"

    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        counter = 1
        while destination.exists():
            destination = destination_dir / f"{clean_stem}_{stamp}_{counter}{source.suffix}"
            counter += 1
        shutil.copy2(source, destination)
    except OSError as exc:
        raise BackupError(f"Backup del file originale non riuscito: {source} ({exc})") from exc

    return destination
