from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot


REPO_DIR = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = REPO_DIR / "AGGIORNA_E_RIAVVIA.bat"


@dataclass(frozen=True)
class UpdateInfo:
    available: bool
    can_apply: bool
    message: str
    local_revision: str = ""
    remote_revision: str = ""
    upstream: str = "origin/main"


class UpdateCheckWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(check_for_updates())
        except Exception as exc:
            self.failed.emit(str(exc) or "Controllo aggiornamenti non riuscito.")


def check_for_updates() -> UpdateInfo:
    if not (REPO_DIR / ".git").exists():
        return UpdateInfo(False, False, "Cartella Git non trovata.")

    if not UPDATE_SCRIPT.exists():
        return UpdateInfo(False, False, "Script di aggiornamento non trovato.")

    upstream = _get_upstream()
    remote_name = upstream.split("/", 1)[0] if "/" in upstream else "origin"

    fetch = _run_git(["fetch", remote_name], timeout=45)
    if fetch.returncode != 0:
        return UpdateInfo(False, False, _clean_error(fetch.stderr) or "GitHub non raggiungibile.")

    local = _git_stdout(["rev-parse", "HEAD"])
    remote = _git_stdout(["rev-parse", upstream])
    if not local or not remote or local == remote:
        return UpdateInfo(False, False, "App gia aggiornata.", local, remote, upstream)

    if _has_tracked_local_changes():
        return UpdateInfo(
            True,
            False,
            "Aggiornamento disponibile, ma ci sono modifiche locali ai file dell'app. "
            "Salvale su GitHub o ripristinale prima di aggiornare automaticamente.",
            local,
            remote,
            upstream,
        )

    ancestor = _run_git(["merge-base", "--is-ancestor", "HEAD", upstream], timeout=20)
    if ancestor.returncode != 0:
        return UpdateInfo(
            True,
            False,
            "Aggiornamento disponibile, ma la cronologia locale e diversa da GitHub. "
            "Serve un controllo manuale prima di applicarlo.",
            local,
            remote,
            upstream,
        )

    return UpdateInfo(
        True,
        True,
        "E disponibile una nuova versione di PassApp. Vuoi aggiornare ora?",
        local,
        remote,
        upstream,
    )


def start_update_and_restart() -> None:
    if not UPDATE_SCRIPT.exists():
        raise OSError(f"Script di aggiornamento non trovato: {UPDATE_SCRIPT}")

    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", str(UPDATE_SCRIPT)],
        cwd=REPO_DIR,
        close_fds=True,
        creationflags=_creation_flags(),
    )


def _get_upstream() -> str:
    upstream = _git_stdout(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return upstream or "origin/main"


def _git_stdout(args: list[str]) -> str:
    result = _run_git(args, timeout=20)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _has_tracked_local_changes() -> bool:
    result = _run_git(["status", "--porcelain", "--untracked-files=no"], timeout=20)
    return bool(result.stdout.strip())


def _run_git(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=_creation_flags(),
    )


def _creation_flags() -> int:
    if sys.platform != "win32":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _clean_error(value: str) -> str:
    return " ".join(value.split())
