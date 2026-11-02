"""Verify IBM's HTTP contract locally, without representing a mock as tenant access."""
from dataclasses import replace
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.integrations import orchestrate_runtime as module
from app.integrations.orchestrate_runtime import (
    AgentReply, OrchestrateError, OrchestrateRuntime, OrchestrateSettings, OrchestrateUnavailable,
)

INSTANCE = "11111111-1111-4111-8111-111111111111"
AGENT = "22222222-2222-4222-8222-222222222222"
THREAD = "33333333-3333-4333-8333-333333333333"
SERVICE = "https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/" + INSTANCE
CONFIG = OrchestrateSettings(SERVICE, AGENT, bearer_token="private-bearer")


@pytest.fixture(autouse=True)
def clear_iam_cache(monkeypatch):
    monkeypatch.setattr(module, "_iam_tokens", {})


def response(message="Official guidance is available at the cited source.", thread=THREAD):
    return {"id": "44444444-4444-4444-8444-444444444444", "object": "chat.completion",
            "created": 123, "model": "orchestrate", "thread_id": thread,
            "choices": [{"message": {"role": "assistant", "content": message}}]}


def transport(handler, config=CONFIG):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OrchestrateRuntime(config, client=client)


def test_service_path_messages_thread_header_and_context_each_turn():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())
    runtime = transport(handler)
    history = [{"role": "system", "content": "Use the retrieved official excerpts."}]
    first = runtime.send("Review my dates", history=history, context={"staytus_context": "signed-capability-one"})
    assert first == AgentReply("Official guidance is available at the cited source.", THREAD)
    runtime.send("Continue", thread_id=first.thread_id, history=[*history, {"role": "assistant", "content": first.message}],
                 context={"staytus_context": "signed-capability-two"})
    assert len(calls) == 2
    for request in calls:
        assert request.url == SERVICE + f"/v1/orchestrate/{AGENT}/chat/completions"
        assert request.method == "POST" and request.headers["Authorization"] == "Bearer private-bearer"
        assert json.loads(request.content)["stream"] is False
        assert "signed-capability" not in json.dumps(json.loads(request.content)["messages"])
    assert "X-IBM-THREAD-ID" not in calls[0].headers
    assert calls[1].headers["X-IBM-THREAD-ID"] == THREAD
    assert json.loads(calls[0].content) == {"messages": [*history, {"role": "user", "content": "Review my dates"}],
                                           "stream": False, "context": {"staytus_context": "signed-capability-one"}}
    assert json.loads(calls[1].content)["context"] == {"staytus_context": "signed-capability-two"}
    assert history == [{"role": "system", "content": "Use the retrieved official excerpts."}]


def test_iam_cache_shared_across_request_runtime_instances_and_refreshes_on_expiry(monkeypatch):
    calls, stamp = [], [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: stamp[0])
    def handler(request):
        calls.append(request)
        if request.url.host == "iam.cloud.ibm.com":
            form = parse_qs(request.content.decode())
            assert form == {"grant_type": ["urn:ibm:params:oauth:grant-type:apikey"], "apikey": ["private-api-key"]}
            return httpx.Response(200, json={"access_token": "iam-token-" + str(stamp[0]), "expires_in": 120})
        return httpx.Response(200, json=response())
    config = replace(CONFIG, api_key="private-api-key", bearer_token="")
    first, second = transport(handler, config), transport(handler, config)
    first.send("First", context={"staytus_context": "one"})
    second.send("Second", context={"staytus_context": "two"})
    assert sum(c.url.host == "iam.cloud.ibm.com" for c in calls) == 1
    stamp[0] = 1061
    second.send("Third", context={"staytus_context": "three"})
    assert sum(c.url.host == "iam.cloud.ibm.com" for c in calls) == 2
    chat_calls = [c for c in calls if c.url.host != "iam.cloud.ibm.com"]
    assert chat_calls[0].headers["Authorization"] == "Bearer iam-token-1000.0"
    assert chat_calls[-1].headers["Authorization"] == "Bearer iam-token-1061"


def test_auth_rejection_refreshes_iam_once_with_unchanged_context_and_thread():
    calls, grants, chats = [], 0, 0
    def handler(request):
        nonlocal grants, chats
        calls.append(request)
        if request.url.host == "iam.cloud.ibm.com":
            grants += 1
            return httpx.Response(200, json={"access_token": f"token-{grants}", "expires_in": 3600})
        chats += 1
        if chats == 1:
            return httpx.Response(401, text="private-auth-response")
        assert request.headers["Authorization"] == "Bearer token-2"
        return httpx.Response(200, json=response())
    runtime = transport(handler, replace(CONFIG, api_key="private-api-key", bearer_token=""))
    result = runtime.send("Continue", thread_id=THREAD, context={"staytus_context": "fresh-capability"})
    assert result.thread_id == THREAD and grants == chats == 2
    chat_calls = [c for c in calls if c.url.host != "iam.cloud.ibm.com"]
    assert chat_calls[0].content == chat_calls[1].content
    assert all(c.headers["X-IBM-THREAD-ID"] == THREAD for c in chat_calls)


def test_second_auth_rejection_never_retries_a_third_time():
    grants, chats = [], []
    def handler(request):
        if request.url.host == "iam.cloud.ibm.com":
            grants.append(request)
            return httpx.Response(200, json={"access_token": "token-" + str(len(grants)), "expires_in": 3600})
        chats.append(request)
        return httpx.Response(401, text="do-not-expose-provider-detail")
    runtime = transport(handler, replace(CONFIG, api_key="private-api-key", bearer_token=""))
    with pytest.raises(OrchestrateError) as error:
        runtime.send("Check documents")
    assert len(grants) == len(chats) == 2
    assert "do-not-expose-provider-detail" not in str(error.value)


@pytest.mark.parametrize("status", [301, 403, 404, 409, 429, 500, 502, 503])
def test_other_statuses_never_retry_or_follow_redirects(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="secret-upstream-body", headers={"location": "https://attacker.example/"})
    # Even an injected client configured to follow redirects is overridden per call.
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    runtime = OrchestrateRuntime(CONFIG, client)
    with pytest.raises(OrchestrateError) as error:
        runtime.send("Review documents", context={"staytus_context": "private-capability"})
    assert len(calls) == 1
    assert all(secret not in str(error.value) for secret in ("secret-upstream-body", "private-bearer", "private-capability"))


def test_bearer_only_auth_error_has_no_iam_retry():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="private-body")
    with pytest.raises(OrchestrateError):
        transport(handler).send("Review documents")
    assert len(calls) == 1 and calls[0].url.host != "iam.cloud.ibm.com"


def test_timeout_is_safe_and_never_retried():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-provider-body-and-secret", request=request)
    with pytest.raises(OrchestrateError) as error:
        transport(handler).send("Review documents", context={"staytus_context": "private-capability"})
    assert len(calls) == 1 and "no automatic retry" in str(error.value)
    assert "private" not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("data", [None, [], {}, {"choices": []},
    {"thread_id": "not-a-uuid", "choices": [{"message": {"content": "Text"}}]},
    {"thread_id": THREAD, "choices": [{"message": {"content": " "}}]},
    {"thread_id": THREAD, "choices": [{"delta": {"content": "No stream"}}]},
    {"thread_id": THREAD, "choices": [{"message": {"role": "tool", "content": "Do not display tool output"}}]},
    {"thread_id": THREAD, "choices": [{"message": {"content": {"secret": "provider-private"}}}]},
    {"thread_id": THREAD, "choices": [{"message": {"content": [{"response_type": "image", "text": "Not text"}]}}]},
])
def test_malformed_success_response_is_rejected_without_fallback(data):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=data)
    with pytest.raises(OrchestrateError, match="invalid chat response"):
        transport(handler).send("Review documents")
    assert len(calls) == 1


def test_invalid_json_and_structured_text_blocks():
    with pytest.raises(OrchestrateError, match="invalid chat response"):
        transport(lambda _: httpx.Response(200, text="private-non-json-body")).send("Hello")
    blocks = [{"response_type": "text", "text": "First paragraph"}, {"type": "text", "text": "Second paragraph"}]
    result = transport(lambda _: httpx.Response(200, json=response(blocks))).send("Hello")
    assert result.message == "First paragraph\nSecond paragraph"


@pytest.mark.parametrize("change", [
    {"service_url": ""}, {"service_url": "http://127.0.0.1:8000/instances/" + INSTANCE},
    {"service_url": "https://api.us-south.watson-orchestrate.cloud.ibm.com.attacker.example/instances/" + INSTANCE},
    {"service_url": "https://ca-tor.watson-orchestrate.cloud.ibm.com/instances/" + INSTANCE},
    {"service_url": SERVICE + "/v1"}, {"service_url": SERVICE + "?key=private"},
    {"service_url": SERVICE + "#fragment"}, {"service_url": SERVICE.replace("https://", "https://user:password@")},
    {"service_url": SERVICE.replace(".com/", ".com:8443/")},
    {"service_url": SERVICE.replace(INSTANCE, "not-an-instance")},
    {"agent_id": ""}, {"agent_id": "../../../escape"},
    {"api_key": "", "bearer_token": ""}, {"bearer_token": "token\r\nInjected: secret"},
    {"bearer_token": "non-ascii-秘密"}, {"timeout": 0}, {"timeout": float("nan")}, {"timeout": 181},
])
def test_invalid_configuration_fails_before_network_without_echoing_inputs(change):
    with pytest.raises(OrchestrateUnavailable) as error:
        OrchestrateRuntime(replace(CONFIG, **change))
    assert all(secret not in str(error.value) for secret in ("private", "password", "attacker", "秘密"))


@pytest.mark.parametrize("body", [{}, [], {"access_token": ""}, {"access_token": "token", "expires_in": -1},
                                  {"access_token": "token", "expiration": "not-a-number"},
                                  {"access_token": "token", "expires_in": "nan"}])
def test_malformed_iam_response_is_typed_unavailable(body):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=body)
    with pytest.raises(OrchestrateUnavailable, match="authentication failed"):
        transport(handler, replace(CONFIG, api_key="private-api-key", bearer_token="")).send("Hello")
    assert len(calls) == 1 and calls[0].url.host == "iam.cloud.ibm.com"


def test_iam_failure_is_safe_and_settings_repr_redacts_credentials():
    config = replace(CONFIG, api_key="private-api-key", bearer_token="private-bearer")
    assert "private-api-key" not in repr(config) and "private-bearer" not in repr(config)
    with pytest.raises(OrchestrateUnavailable) as error:
        transport(lambda _: httpx.Response(403, text="private-provider-response"), config).send("Hello")
    assert "private" not in str(error.value)


@pytest.mark.parametrize("kwargs", [{"message": " "}, {"message": "x" * 8001}, {"message": "Hello", "thread_id": "bad\r\nthread"},
    {"message": "Hello", "history": [{"role": "tool", "content": "bad"}]},
    {"message": "Hello", "history": [{"role": "system", "content": "text", "capability": "private"}]},
    {"message": "Hello", "context": {"unsafe": float("nan")}},
    {"message": "Hello", "context": {"oversized": "x" * 9000}}])
def test_invalid_messages_and_context_do_not_make_requests(kwargs):
    calls = []
    runtime = transport(lambda request: calls.append(request))
    with pytest.raises(OrchestrateError):
        runtime.send(**kwargs)
    assert calls == []


def test_close_closes_owned_client_and_preserves_injected_client():
    owned = OrchestrateRuntime(CONFIG)
    owned.close()
    assert owned.client.is_closed
    borrowed = transport(lambda _: httpx.Response(200, json=response()))
    borrowed.close()
    assert not borrowed.client.is_closed
    borrowed.client.close()


def test_authenticated_chat_route_uses_real_adapter_contract_with_fake_http(env, student, monkeypatch):
    client, _ = env
    for key, value in {"ORCHESTRATE_SERVICE_URL": SERVICE, "ORCHESTRATE_AGENT_ID": AGENT,
                       "ORCHESTRATE_API_KEY": "", "ORCHESTRATE_BEARER_TOKEN": "private-bearer",
                       "ORCHESTRATE_CONTEXT_VERIFIED": "true"}.items():
        monkeypatch.setenv(key, value)
    calls, original_client = [], httpx.Client
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response())
    monkeypatch.setattr(module.httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs))
    first = client.post("/api/v1/chat", headers=student, json={"message": "Review my program dates"})
    assert first.status_code == 200, first.text
    assert first.json()["mode"] == "orchestrate"
    payload = json.loads(calls[0].content)
    capability = payload["context"]["staytus_context"]
    assert capability not in json.dumps(payload["messages"]) and capability not in first.text
    tool = client.post("/tools/get_student_profile", json={}, headers={
        "X-Tool-Key": "test-tool-key", "X-Staytus-Context": capability})
    assert tool.status_code == 200 and tool.json()["id"] == "mei-lin"
    second = client.post("/api/v1/chat", headers=student, json={
        "message": "Continue", "conversation_id": first.json()["conversation_id"]})
    assert second.status_code == 200 and calls[1].headers["X-IBM-THREAD-ID"] == THREAD
