from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from core.file_state import FileSnapshot, capture_file_snapshot


@dataclass(frozen=True)
class WorkcopyResult:
    path: Path
    snapshot: FileSnapshot
    removed_old_copies: int


def cleanup_old_workcopies(
    directory: str | Path,
    *,
    prefixes: tuple[str, ...],
    max_age_days: int = 30,
    allowed_suffixes: tuple[str, ...] = (".xls", ".xlsx"),
) -> int:
    root = Path(directory)
    if not root.exists():
        return 0

    cutoff = time.time() - (max_age_days * 24 * 60 * 60)
    removed = 0
    for candidate in root.iterdir():
        if not candidate.is_file():
            continue
        if prefixes and not candidate.name.startswith(prefixes):
            continue
        if candidate.suffix.lower() not in allowed_suffixes:
            continue
        try:
            if candidate.stat().st_mtime >= cutoff:
                continue
            candidate.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def create_working_copy(
    source_path: str | Path,
    directory: str | Path,
    *,
    prefix: str,
    default_suffix: str = ".xlsx",
    cleanup_prefixes: tuple[str, ...] | None = None,
    max_age_days: int = 30,
) -> WorkcopyResult:
    source = Path(source_path)
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    prefixes = cleanup_prefixes if cleanup_prefixes is not None else (prefix,)
    removed = cleanup_old_workcopies(root, prefixes=prefixes, max_age_days=max_age_days)

    suffix = source.suffix or default_suffix
    fd, temp_name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(root))
    os.close(fd)
    temp_path = Path(temp_name)
    shutil.copy2(source, temp_path)
    snapshot = capture_file_snapshot(source)
    return WorkcopyResult(path=temp_path, snapshot=snapshot, removed_old_copies=removed)
