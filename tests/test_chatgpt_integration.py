import io
import json
import os
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen
from unittest.mock import Mock, patch

import pytest

from services.ai.chatgpt_auth import ChatGPTAuth, PLAN_SCOPE, RESOURCE, _protect
from services.ai.chatgpt_client import ChatGPTClient, ChatGPTConfig, _consume_stream
from services.ai.exceptions import AIServiceError


def events(*items):
    return io.BytesIO(b"".join(("data: " + json.dumps(item) + "\n\n").encode() for item in items))


def test_stream_requires_completed_and_rejects_partial_output():
    delta = {"type": "response.output_text.delta", "delta": "Testo incompleto"}
    for terminal in ({"type": "response.failed"}, {"type": "response.incomplete"}, {"type": "error"}):
        with pytest.raises(AIServiceError):
            _consume_stream(events(delta, terminal))
    with pytest.raises(AIServiceError):
        _consume_stream(events(delta))
    assert _consume_stream(events(delta, {"type": "response.completed"}))["output_text"] == "Testo incompleto"


def test_inference_uses_oauth_public_responses_and_account_catalog():
    auth = Mock()
    auth.access_token.return_value = "test-bearer"
    client = ChatGPTClient(ChatGPTConfig(), auth)
    catalog = {"models": [{"slug": "available-model", "display_name": "Available", "visibility": "list"},
                          {"slug": "hidden-model", "visibility": "hide"}]}
    stream = events({"type": "response.output_text.delta", "delta": "Risposta"},
                    {"type": "response.completed", "response": {"status": "completed"}})
    with patch("services.ai.chatgpt_client.request_json", return_value=catalog), patch(
        "services.ai.chatgpt_client.urlopen", return_value=stream
    ) as call:
        assert client.response_text(client.chat_sync("Istruzioni", "Dati", structured=True)) == "Risposta"
    request = call.call_args.args[0]
    assert request.full_url == RESOURCE + "/responses"
    assert request.get_header("Authorization") == "Bearer test-bearer"
    body = json.loads(request.data)
    assert body["model"] == "available-model"
    assert body["input"] == [{"role": "user", "content": "Dati"}]
    assert body["store"] is False and body["stream"] is True
    assert body["text"]["format"]["type"] == "json_object"


def test_unknown_model_never_submits_document():
    client = ChatGPTClient(ChatGPTConfig(model="old-local-model"), Mock())
    with patch.object(client, "list_models", return_value=(("available", "Available"),)), patch(
        "services.ai.chatgpt_client.urlopen"
    ) as call, pytest.raises(AIServiceError):
        client.chat_sync("system", "private data")
    call.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_storage_refresh_rotation_and_disconnect(tmp_path):
    auth = ChatGPTAuth(tmp_path)
    with auth.locked():
        auth._write({"client_id": "issued", "subject": "subject", "email": "test@example.invalid",
                     "access_token": "old-access", "refresh_token": "old-refresh", "expires_at": 0,
                     "scopes": [PLAN_SCOPE]})
    assert b"old-access" not in auth.path.read_bytes()
    assert _protect(_protect(b"test"), decrypt=True) == b"test"
    with patch("services.ai.chatgpt_auth.request_json", return_value={
        "access_token": "new-access", "refresh_token": "new-refresh", "token_type": "Bearer", "expires_in": 3600
    }) as call:
        assert auth.access_token() == "new-access"
        assert call.call_args.kwargs["form"]["client_id"] == "issued"
        assert "scope" not in call.call_args.kwargs["form"]
        assert auth.access_token() == "new-access"
        assert call.call_count == 1
    auth.disconnect()
    assert auth._read() == {"client_id": "issued", "subject": "subject", "email": "test@example.invalid"}


def test_missing_grant_prevents_api_use(tmp_path):
    auth = ChatGPTAuth(tmp_path)
    with patch.object(auth, "_read", return_value={"access_token": "token", "expires_at": time.time() + 3600}), pytest.raises(AIServiceError):
        auth.access_token()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
@pytest.mark.parametrize("wrong_state,error,issued", [(True, None, "registered"), (False, "access_denied", "registered"), (False, None, None)])
def test_untrusted_oauth_callback_never_exchanges_code(tmp_path, wrong_state, error, issued):
    auth = ChatGPTAuth(tmp_path)
    cancel = threading.Event()
    def browser(url):
        query = parse_qs(urlsplit(url).query)
        def callback():
            params = {"state": "wrong" if wrong_state else query["state"][0], "code": "unused"}
            if issued:
                params["client_id"] = issued
            if error:
                params["error"] = error
            try:
                with urlopen(query["redirect_uri"][0] + "?" + urlencode(params), timeout=5):
                    pass
            except Exception:
                pass
            finally:
                if wrong_state:
                    cancel.set()
        threading.Thread(target=callback, daemon=True).start()
        return True
    with patch("services.ai.chatgpt_auth.webbrowser.open", side_effect=browser), patch(
        "services.ai.chatgpt_auth.request_json"
    ) as exchange, pytest.raises(AIServiceError):
        auth.sign_in(cancel)
    exchange.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_sign_in_pkce_and_issued_registration(tmp_path):
    auth = ChatGPTAuth(tmp_path)
    authorize = {}
    def browser(url):
        authorize.update(parse_qs(urlsplit(url).query))
        def callback():
            params = {"state": authorize["state"][0], "code": "one-time", "client_id": "issued-id"}
            with urlopen(authorize["redirect_uri"][0] + "?" + urlencode(params), timeout=5):
                pass
        threading.Thread(target=callback, daemon=True).start()
        return True
    tokens = {"id_token": "test-id", "access_token": "test-access", "refresh_token": "test-refresh",
              "token_type": "Bearer", "scope": PLAN_SCOPE, "expires_in": 3600}
    with patch("services.ai.chatgpt_auth.webbrowser.open", side_effect=browser), patch(
        "services.ai.chatgpt_auth.request_json", return_value=tokens
    ) as exchange, patch.object(auth, "_verify_identity", return_value={"sub": "verified", "email": "test@example.invalid"}) as verify:
        assert auth.sign_in()["sharing"]
    assert authorize["client_id"] == ["dynamic_agent_client"]
    assert authorize["code_challenge_method"] == ["S256"]
    assert authorize["ext_agent_host_id"][0].startswith("urn:uuid:")
    form = exchange.call_args.kwargs["form"]
    assert form["client_id"] == "issued-id"
    assert form["redirect_uri"] == authorize["redirect_uri"][0]
    verify.assert_called_once_with("test-id", "issued-id", authorize["nonce"][0])
    assert auth._host_id() == authorize["ext_agent_host_id"][0]


def test_identity_rejects_bad_nonce_and_signature():
    key = Mock()
    key.key = "test-key"
    for claims in ({"sub": "valid", "nonce": "wrong"}, {"sub": "", "nonce": "expected"}):
        with patch("jwt.PyJWKClient") as jwks, patch("jwt.decode", return_value=claims), pytest.raises(AIServiceError):
            jwks.return_value.get_signing_key_from_jwt.return_value = key
            ChatGPTAuth._verify_identity("test", "client", "expected")
    with patch("jwt.PyJWKClient") as jwks, patch("jwt.decode", side_effect=ValueError("bad signature")), pytest.raises(AIServiceError):
        jwks.return_value.get_signing_key_from_jwt.return_value = key
        ChatGPTAuth._verify_identity("test", "client", "expected")


def test_document_error_is_visible_instead_of_silent_local_substitution():
    from core.ai_documents import prepare_segnalazione_pdf
    with patch("core.ai_documents.ChatGPTClient") as client, pytest.raises(AIServiceError):
        client.return_value.chat_sync.side_effect = AIServiceError("Limit reached")
        prepare_segnalazione_pdf({}, {"ai": {"documents_enabled": True}})
    with patch("core.ai_documents.ChatGPTClient") as client:
        text, source = prepare_segnalazione_pdf({}, {"ai": {"documents_enabled": False}})
        assert text and source == "locale"
        client.assert_not_called()


def test_legacy_settings_migrate_without_using_local_endpoint():
    from app_config import _sanitize_ai_config
    config = {"ai": {"model": "qwen", "base_url": "http://127.0.0.1:1234", "documents_enabled": False}}
    _sanitize_ai_config(config)
    assert config["ai"]["provider"] == "chatgpt" and config["ai"]["model"] == ""
    assert "base_url" not in config["ai"]
    assert config["ai"]["documents_enabled"] is False


def test_loading_old_config_does_not_keep_local_model(tmp_path):
    import app_config
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"ai": {"model": "qwen", "documents_enabled": False}}))
    with patch.object(app_config, "CONFIG_PATH", config_path):
        config = app_config.load_config(force_reload=True)
    assert config["ai"]["model"] == ""
    assert config["ai"]["documents_enabled"] is False
    app_config.load_config(force_reload=True)
