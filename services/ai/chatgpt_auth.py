"""Official Sign in with ChatGPT public-client flow; no API keys or browser cookies."""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
import uuid
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from services.ai.exceptions import AIServiceError

ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPES = "openid profile email offline_access resource.invoke " + PLAN_SCOPE
_LOCK = threading.RLock()


def request_json(url, *, form=None, token=None, timeout=30):
    headers = {"Accept": "application/json"}
    body = None
    if form is not None:
        body = urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=timeout) as response:
            value = json.load(response)
    except HTTPError as exc:
        # Never include response bodies or request URLs: they can contain credentials.
        messages = {401: "Accesso ChatGPT scaduto: collegati nuovamente.",
                    403: "ChatGPT non ha autorizzato l'uso del piano per questa app.",
                    429: "Limite del piano ChatGPT raggiunto. Controlla Gestisci utilizzo."}
        raise AIServiceError(messages.get(exc.code, f"Richiesta OpenAI non riuscita (HTTP {exc.code}).")) from None
    except (OSError, URLError, ValueError):
        raise AIServiceError("Impossibile comunicare con OpenAI. Controlla la connessione e riprova.") from None
    if not isinstance(value, dict):
        raise AIServiceError("Risposta OpenAI non valida.")
    return value


def _protect(data: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        raise AIServiceError("La protezione delle credenziali ChatGPT richiede Windows.")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise AIServiceError("Credenziali ChatGPT non leggibili per questo utente Windows. Ricollega l'account.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


class ChatGPTAuth:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PassApp" / "ChatGPT"
        self.path = self.directory / "connection.dpapi"

    @contextmanager
    def locked(self):
        # Serialize rotating refresh tokens across threads and PassApp processes.
        with _LOCK:
            self.directory.mkdir(parents=True, exist_ok=True)
            with (self.directory / "session.lock").open("a+b") as handle:
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    deadline = time.monotonic() + 40
                    while True:
                        try:
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError:
                            if time.monotonic() >= deadline:
                                raise AIServiceError("Account ChatGPT occupato da un'altra operazione. Riprova.") from None
                            time.sleep(0.1)
                try:
                    yield
                finally:
                    if os.name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def _read(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(_protect(self.path.read_bytes(), decrypt=True))
        except (OSError, ValueError):
            raise AIServiceError("Connessione ChatGPT non leggibile. Ricollega l'account.") from None

    def _write(self, value):
        data = _protect(json.dumps(value).encode())
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, self.path)

    def summary(self):
        with self.locked():
            value = self._read()
        return {"connected": bool(value.get("access_token")), "email": value.get("email", ""),
                "sharing": PLAN_SCOPE in value.get("scopes", [])}

    def disconnect(self):
        with self.locked():
            value = self._read()
            # Keep registration and verified identity for the next sign-in, clear all tokens.
            self._write({k: v for k, v in value.items() if k in {"client_id", "subject", "email"}})

    def _host_id(self):
        path = self.directory / "host.json"
        if path.exists():
            return json.loads(path.read_text())["ext_agent_host_id"]
        value = "urn:uuid:" + str(uuid.uuid4())
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"ext_agent_host_id": value}))
        os.replace(temporary, path)
        return value

    @staticmethod
    def _verify_identity(token, client_id, nonce):
        try:
            import jwt
            keys = jwt.PyJWKClient(ISSUER + "/.well-known/jwks.json", timeout=30)
            key = keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=client_id,
                                issuer=ISSUER, leeway=5,
                                options={"require": ["sub", "exp", "iat", "nonce"]})
            if not isinstance(claims["sub"], str) or not claims["sub"] or claims["nonce"] != nonce:
                raise ValueError()
            return claims
        except ImportError:
            raise AIServiceError("Installa le dipendenze aggiornate di PassApp (PyJWT e cryptography).") from None
        except Exception:
            raise AIServiceError("Identita ChatGPT non verificata. Accesso rifiutato; riprova.") from None

    @staticmethod
    def _with_tokens(value, tokens):
        updated = dict(value)
        if not tokens.get("access_token") or str(tokens.get("token_type", "")).lower() != "bearer":
            raise AIServiceError("OpenAI non ha restituito credenziali valide per il piano ChatGPT.")
        updated.update({k: tokens[k] for k in ("access_token", "refresh_token", "id_token") if k in tokens})
        updated["expires_at"] = time.time() + float(tokens.get("expires_in", 0))
        if "scope" in tokens:
            updated["scopes"] = tokens["scope"].split()
        return updated

    def sign_in(self, cancelled: threading.Event | None = None):
        with self.locked():
            previous = self._read()
            host = self._host_id()
        client_id = previous.get("client_id", "dynamic_agent_client")
        state, nonce, verifier = (secrets.token_urlsafe(48) for _ in range(3))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        result = {}

        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                params = parse_qs(parsed.query)
                valid = parsed.path == "/auth/callback" and params.get("state") == [state]
                if not valid:
                    self.send_response(400)
                    self.end_headers()
                    return
                if any(len(values) != 1 for values in params.values()):
                    self.send_response(400)
                    self.end_headers()
                    return
                result.update({k: v[0] for k, v in params.items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write("Puoi tornare a PassApp per completare il collegamento.".encode())

        with HTTPServer(("127.0.0.1", 0), Callback) as server:
            server.timeout = 0.5
            redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
            params = dict(client_id=client_id, ext_agent_host_id=host, response_type="code",
                          redirect_uri=redirect, scope=SCOPES, resource=RESOURCE,
                          state=state, nonce=nonce, code_challenge_method="S256", code_challenge=challenge)
            if client_id == "dynamic_agent_client":
                params["agent_name_hint"] = "PassApp Polizia Locale"
            elif previous.get("email"):
                params["login_hint"] = previous["email"]
            if not webbrowser.open(ISSUER + "/api/accounts/authorize?" + urlencode(params)):
                raise AIServiceError("Impossibile aprire il browser per accedere a ChatGPT.")
            deadline = time.monotonic() + 300
            while not result and time.monotonic() < deadline:
                if cancelled and cancelled.is_set():
                    raise AIServiceError("Collegamento ChatGPT annullato.")
                server.handle_request()
        if not result:
            raise AIServiceError("Accesso ChatGPT scaduto. Premi nuovamente Continue with ChatGPT.")
        if result.get("error"):
            raise AIServiceError("Collegamento ChatGPT non autorizzato. Ripeti l'accesso e autorizza l'uso del piano.")
        issued = result.get("client_id", client_id)
        if not result.get("code") or issued == "dynamic_agent_client" or (client_id != "dynamic_agent_client" and issued != client_id):
            raise AIServiceError("Registrazione ChatGPT incompleta o non corrispondente.")
        with self.locked():
            # Save registration before exchange, even if the one-time code expires.
            registration = {"client_id": issued}
            if issued == previous.get("client_id"):
                registration.update({k: previous[k] for k in ("subject", "email") if k in previous})
            if not previous.get("access_token"):
                self._write(registration)
            tokens = request_json(TOKEN_URL, form=dict(grant_type="authorization_code", client_id=issued,
                                  code=result["code"], code_verifier=verifier, redirect_uri=redirect, resource=RESOURCE))
            claims = self._verify_identity(tokens.get("id_token", ""), issued, nonce)
            if previous.get("subject") and claims["sub"] != previous["subject"]:
                raise AIServiceError("L'account ChatGPT non corrisponde al collegamento salvato.")
            connection = self._with_tokens(dict(client_id=issued, subject=claims["sub"],
                                               email=claims.get("email", "")), tokens)
            self._write(connection)
        return self.summary()

    def access_token(self):
        with self.locked():
            value = self._read()
            if not value.get("access_token"):
                raise AIServiceError("Collega ChatGPT dalla pagina Configurazione: Continue with ChatGPT.")
            if value.get("expires_at", 0) <= time.time() + 60:
                if not value.get("refresh_token"):
                    raise AIServiceError("Accesso ChatGPT scaduto. Collegati nuovamente.")
                tokens = request_json(TOKEN_URL, form=dict(grant_type="refresh_token",
                                      client_id=value["client_id"], refresh_token=value["refresh_token"], resource=RESOURCE))
                value = self._with_tokens(value, tokens)
                self._write(value)
            if PLAN_SCOPE not in value.get("scopes", []):
                raise AIServiceError("Ricollega ChatGPT e autorizza l'uso del tuo piano per PassApp.")
            return value["access_token"]
