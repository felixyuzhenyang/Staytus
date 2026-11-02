"""Exercise bridge authentication/HTTP behavior without installing the IBM SDK.

The separate --check-adk command exercises the real SDK decorator as well.
Only SDK imports/decorators are substituted here; the transport code is real.
"""
import ast
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import pytest


@pytest.fixture
def bridge():
    source = Path(__file__).resolve().parents[2] / "orchestrate/python_tools.py"
    tree = ast.parse(source.read_text())
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and node.module.startswith("ibm_watsonx_orchestrate"))]
    namespace = {"tool": lambda **options: lambda fn: fn,
        "ConnectionType": SimpleNamespace(KEY_VALUE="key_value"), "AgentRun": SimpleNamespace,
        "connections": SimpleNamespace(key_value=lambda app_id: {
            "backend_url": "https://gateway.example.invalid", "tool_key": "synthetic-service-canary"})}
    exec(compile(tree, str(source), "exec"), namespace)
    return SimpleNamespace(namespace=namespace,
        context=SimpleNamespace(request_context={"staytus_context": "synthetic-session-canary"}))


def test_profile_bridge_forwards_both_credentials_without_model_identifiers(bridge):
    requests, handlers = [], []
    class Opener:
        def open(self, request, *, timeout):
            requests.append(request)
            assert timeout == 25
            return BytesIO(b'{"id":"owned-synthetic-profile"}')
    def factory(handler):
        handlers.append(handler)
        return Opener()
    bridge.namespace["build_opener"] = factory
    result = bridge.namespace["get_student_profile"](bridge.context)
    assert result == {"id": "owned-synthetic-profile"}
    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "https://gateway.example.invalid/tools/get_student_profile"
    assert request.method == "POST" and json.loads(request.data) == {}
    assert request.get_header("X-tool-key") == "synthetic-service-canary"
    assert request.get_header("X-staytus-context") == "synthetic-session-canary"
    assert len(handlers) == 1 and isinstance(handlers[0], bridge.namespace["_NoRedirect"])
    assert handlers[0].redirect_request(request, None, 307, "redirect", {}, "https://other.invalid") is None


@pytest.mark.parametrize("status,expected", [(401, "tool_authorization_failed"),
    (403, "tool_permission_required"), (307, "backend_tool_unavailable"),
    (500, "backend_tool_unavailable")])
def test_http_denials_and_uncertain_failure_never_retry_or_leak(bridge, status, expected):
    calls = []
    class Opener:
        def open(self, request, *, timeout):
            calls.append(request)
            raise HTTPError(request.full_url, status, "synthetic-private-error-canary", {},
                BytesIO(b"synthetic-private-body-canary"))
    bridge.namespace["build_opener"] = lambda *handlers: Opener()
    result = bridge.namespace["create_email_preview"](bridge.context, {"subject": "Synthetic"})
    assert len(calls) == 1 and result["error"] == expected
    assert "canary" not in json.dumps(result)


@pytest.mark.parametrize("payload,expected", [(b"[]", "invalid_backend_response"),
    (b"not-json-private-canary", "backend_tool_unavailable"),
    (b"x" * 2_000_001, "invalid_backend_response")])
def test_invalid_or_oversized_responses_are_bounded_and_private(bridge, payload, expected):
    class Opener:
        def open(self, request, *, timeout):
            return BytesIO(payload)
    bridge.namespace["build_opener"] = lambda *handlers: Opener()
    result = bridge.namespace["get_student_profile"](bridge.context)
    assert result["error"] == expected and "canary" not in json.dumps(result)


def test_missing_context_stops_before_connection_or_network(bridge):
    bridge.namespace["connections"].key_value = lambda app_id: pytest.fail("Credential lookup before authentication")
    bridge.namespace["build_opener"] = lambda *handlers: pytest.fail("Unauthenticated network call")
    result = bridge.namespace["get_student_profile"](SimpleNamespace(request_context={}))
    assert result["error"] == "authenticated_context_required"


def test_transport_failure_never_echoes_sensitive_exception_or_retries(bridge):
    calls = []
    class Opener:
        def open(self, request, *, timeout):
            calls.append(request)
            raise URLError("synthetic-service-canary synthetic-session-canary")
    bridge.namespace["build_opener"] = lambda *handlers: Opener()
    result = bridge.namespace["get_student_profile"](bridge.context)
    assert len(calls) == 1 and result["error"] == "backend_tool_unavailable"
    assert "canary" not in json.dumps(result)
