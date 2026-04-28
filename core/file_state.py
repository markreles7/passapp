from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileSnapshot:
    path: str
    size: int
    modified_ns: int


def capture_file_snapshot(path: str | Path) -> FileSnapshot:
    source = Path(path)
    stat = source.stat()
    return FileSnapshot(
        path=str(source),
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
    )


def file_matches_snapshot(snapshot: FileSnapshot | None) -> bool:
    if snapshot is None:
        return False
    try:
        current = capture_file_snapshot(snapshot.path)
    except OSError:
        return False
    return current.size == snapshot.size and current.modified_ns == snapshot.modified_ns
