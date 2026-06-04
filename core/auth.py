from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app_config import BASE_DIR


USER_STORE_PATH = BASE_DIR / "data" / "users.json"
ADMIN_USERNAME = "markreles7"
ADMIN_INITIAL_PASSWORD = "J0hn_W1ck.777"
ROLE_ADMIN = "admin"
ROLE_USER = "user"
PBKDF2_ITERATIONS = 260_000


class AuthError(ValueError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


def authenticate(username: str, password: str, *, store_path: Path = USER_STORE_PATH) -> AuthenticatedUser:
    store = ensure_user_store(store_path=store_path)
    record = _find_user(store, username)
    if record is None or not record.get("active", True):
        raise AuthError("Credenziali non valide.")

    if not _verify_password(password, record):
        raise AuthError("Credenziali non valide.")

    role = str(record.get("role") or ROLE_USER)
    if role == ROLE_ADMIN and not _admin_machine_allowed(record):
        raise AuthError("Accesso amministratore consentito solo dal PC di installazione.")

    return AuthenticatedUser(username=str(record["username"]), role=role)


def create_user(
    username: str,
    password: str,
    *,
    created_by: AuthenticatedUser,
    store_path: Path = USER_STORE_PATH,
) -> dict[str, Any]:
    if not created_by.is_admin:
        raise AuthError("Solo l'amministratore puo creare nuovi profili.")

    normalized_username = _validate_username(username)
    _validate_password(password)

    store = ensure_user_store(store_path=store_path)
    if _find_user(store, normalized_username) is not None:
        raise AuthError("Username gia presente.")

    record = _build_user_record(normalized_username, password, role=ROLE_USER)
    store.setdefault("users", []).append(record)
    _save_store(store, store_path)
    return _public_user(record)


def list_users(*, store_path: Path = USER_STORE_PATH) -> list[dict[str, Any]]:
    store = ensure_user_store(store_path=store_path)
    users = store.get("users", [])
    if not isinstance(users, list):
        return []
    return [_public_user(user) for user in users if isinstance(user, dict)]


def ensure_user_store(*, store_path: Path = USER_STORE_PATH) -> dict[str, Any]:
    store = _load_store(store_path)
    users = store.setdefault("users", [])
    if not isinstance(users, list):
        store["users"] = []
        users = store["users"]

    admin = _find_user(store, ADMIN_USERNAME)
    if admin is None:
        users.append(
            _build_user_record(
                ADMIN_USERNAME,
                ADMIN_INITIAL_PASSWORD,
                role=ROLE_ADMIN,
                allowed_machine_hash=_current_machine_hash(),
            )
        )
        _save_store(store, store_path)
    elif admin.get("role") == ROLE_ADMIN and not admin.get("allowed_machine_hash"):
        admin["allowed_machine_hash"] = _current_machine_hash()
        _save_store(store, store_path)

    return store


def _build_user_record(
    username: str,
    password: str,
    *,
    role: str,
    allowed_machine_hash: str | None = None,
) -> dict[str, Any]:
    salt = os.urandom(16)
    return {
        "username": username,
        "role": role,
        "active": True,
        "password_salt": base64.b64encode(salt).decode("ascii"),
        "password_hash": _hash_password(password, salt),
        "created_at": datetime.now(UTC).isoformat(),
        "allowed_machine_hash": allowed_machine_hash,
    }


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return base64.b64encode(digest).decode("ascii")


def _verify_password(password: str, record: dict[str, Any]) -> bool:
    try:
        salt = base64.b64decode(str(record["password_salt"]).encode("ascii"))
        expected = str(record["password_hash"])
    except (KeyError, ValueError):
        return False
    actual = _hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def _load_store(store_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(store_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"users": []}
    except (OSError, json.JSONDecodeError):
        return {"users": []}
    return payload if isinstance(payload, dict) else {"users": []}


def _save_store(store: dict[str, Any], store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _find_user(store: dict[str, Any], username: str) -> dict[str, Any] | None:
    normalized = username.strip().casefold()
    users = store.get("users", [])
    if not isinstance(users, list):
        return None
    for user in users:
        if isinstance(user, dict) and str(user.get("username", "")).casefold() == normalized:
            return user
    return None


def _validate_username(username: str) -> str:
    normalized = username.strip()
    if len(normalized) < 3:
        raise AuthError("Lo username deve contenere almeno 3 caratteri.")
    if any(char.isspace() for char in normalized):
        raise AuthError("Lo username non puo contenere spazi.")
    return normalized


def _validate_password(password: str) -> None:
    if len(password) < 8:
        raise AuthError("La password deve contenere almeno 8 caratteri.")


def _admin_machine_allowed(record: dict[str, Any]) -> bool:
    allowed_machine_hash = str(record.get("allowed_machine_hash") or "")
    return bool(allowed_machine_hash) and hmac.compare_digest(allowed_machine_hash, _current_machine_hash())


def _current_machine_hash() -> str:
    identifier = _machine_identifier()
    return hashlib.sha256(f"passapp:{identifier}".encode("utf-8")).hexdigest()


def _machine_identifier() -> str:
    windows_guid = _windows_machine_guid()
    if windows_guid:
        return windows_guid
    return "|".join((platform.node(), platform.system(), str(uuid.getnode())))


def _windows_machine_guid() -> str:
    try:
        import winreg
    except ImportError:
        return ""

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return ""
    return str(value).strip()


def _public_user(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(record.get("username", "")),
        "role": str(record.get("role", ROLE_USER)),
        "active": bool(record.get("active", True)),
        "created_at": str(record.get("created_at", "")),
    }
