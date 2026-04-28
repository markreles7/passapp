from __future__ import annotations

import os
import subprocess


def run_powershell_command(command: str, timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def check_office_com(app_name: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Controllo disponibile solo su Windows."

    command = (
        f"$app=$null; try {{ $app = New-Object -ComObject {app_name}; "
        "$app.Quit(); exit 0 } catch { exit 1 }"
    )
    try:
        result = run_powershell_command(command, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"Controllo non riuscito: {exc}"

    if result.returncode == 0:
        return True, "Automazione COM disponibile."
    details = (result.stderr or result.stdout or "COM non disponibile").strip()
    return False, details
