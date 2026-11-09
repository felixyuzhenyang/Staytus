"""IBM Cloud Orchestrate Chat Completions transport.

Contract: /v1/orchestrate/{agent_id}/chat/completions, X-IBM-THREAD-ID,
and per-run context from IBM's published API/OpenAPI. This module never puts
signed user capabilities in model messages or retries an uncertain agent run.

Primary references:
https://developer.watson-orchestrate.ibm.com/apis/orchestrate-agent/chat-with-agents
https://developer.watson-orchestrate.ibm.com/conversation/context_variables
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
import threading
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class OrchestrateError(RuntimeError):
    """Public-safe transport failure; no provider body, URL or credential included."""


class OrchestrateUnavailable(OrchestrateError):
    """Missing/invalid deployment configuration or unavailable IAM authentication."""


@dataclass(frozen=True)
class OrchestrateSettings:
    service_url: str
    agent_id: str
    api_key: str = field(default="", repr=False)
    bearer_token: str = field(default="", repr=False)
    timeout: float = 90


@dataclass(frozen=True)
class AgentReply:
    message: str
    thread_id: str


# Chat dependencies construct a transport per request. Keep IAM tokens reusable
# across those instances, keyed by a one-way API-key digest, never by user input.
# Tokens remain process-local and are never written to a database or browser.
_iam_tokens: dict[str, tuple[str, float]] = {}
_iam_lock = threading.Lock()

# This is an application-side character guard for one history message, not the
# model's token context window. Keep the separate aggregate-history guard below.
MAX_HISTORY_ITEM_CHARACTERS = 100_000


def _uuid(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid UUID")
    result = str(UUID(value))
    if result != value.lower():
        raise ValueError("Use canonical UUID format")
    return result


def _credential(value: str) -> bool:
    return (isinstance(value, str) and bool(value) and len(value) <= 16384
            and not any(c.isspace() or ord(c) < 32 or ord(c) >= 127 for c in value))


class OrchestrateRuntime:
    def __init__(self, settings: OrchestrateSettings, client: httpx.Client | None = None):
        try:
            parsed = urlsplit(settings.service_url)
            hostname = parsed.hostname or ""
            path = parsed.path.rstrip("/")
            parts = path.split("/")
            if (parsed.scheme != "https" or not re.fullmatch(
                    r"api\.[a-z0-9-]+\.watson-orchestrate\.cloud\.ibm\.com", hostname)
                    or parsed.port not in (None, 443) or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or len(parts) != 3 or parts[1] != "instances"):
                raise ValueError("Invalid Cloud instance URL")
            instance_id = _uuid(parts[2])
            agent_id = _uuid(settings.agent_id)
            timeout = float(settings.timeout)
            if isinstance(settings.timeout, bool) or not math.isfinite(timeout) or not 0 < timeout <= 180:
                raise ValueError("Invalid timeout")
            if not (_credential(settings.api_key) or _credential(settings.bearer_token)):
                raise ValueError("Missing credentials")
            if ((settings.api_key and not _credential(settings.api_key))
                    or (settings.bearer_token and not _credential(settings.bearer_token))):
                raise ValueError("Invalid credential format")
        except (ValueError, TypeError, AttributeError):
            raise OrchestrateUnavailable("Configure an HTTPS IBM Cloud service instance URL, UUID agent ID and server credentials") from None
        self.settings = settings
        self.timeout = timeout
        self.url = f"https://{hostname}/instances/{instance_id}/v1/orchestrate/{agent_id}/chat/completions"
        self._owns_client = client is None
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)
        self._cache_key = hashlib.sha256(settings.api_key.encode()).hexdigest() if settings.api_key else ""

    def _token(self) -> str:
        # API keys take precedence so IAM can refresh credentials. An explicit
        # bearer-only configuration is supported but cannot be refreshed by us.
        if not self.settings.api_key:
            return self.settings.bearer_token
        with _iam_lock:
            stamp = time.time()
            cached = _iam_tokens.get(self._cache_key)
            if cached and stamp < cached[1] - 60:
                return cached[0]
            try:
                response = self.client.post("https://iam.cloud.ibm.com/identity/token",
                    data={"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": self.settings.api_key},
                    headers={"Accept": "application/json"}, timeout=min(self.timeout, 30), follow_redirects=False)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, dict) or not _credential(result.get("access_token")):
                    raise ValueError("Invalid IAM token")
                expires = stamp + float(result.get("expires_in", 3600))
                if "expiration" in result:
                    expires = min(expires, float(result["expiration"]))
                if not math.isfinite(expires) or expires <= stamp:
                    raise ValueError("Invalid IAM expiry")
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                raise OrchestrateUnavailable("IBM Cloud authentication failed; verify server credentials and tenant permissions") from None
            for key in list(_iam_tokens):
                if _iam_tokens[key][1] <= stamp:
                    del _iam_tokens[key]
            if len(_iam_tokens) >= 128:
                del _iam_tokens[min(_iam_tokens, key=lambda key: _iam_tokens[key][1])]
            _iam_tokens[self._cache_key] = result["access_token"], expires
            return result["access_token"]

    def _invalidate_token(self, rejected_token: str):
        with _iam_lock:
            cached = _iam_tokens.get(self._cache_key)
            if cached and cached[0] == rejected_token:
                del _iam_tokens[self._cache_key]

    @staticmethod
    def _body(message: str, history: list | None, context: dict | None) -> dict:
        if not isinstance(message, str) or not message.strip() or len(message) > 8000:
            raise OrchestrateError("A nonempty message of at most 8000 characters is required")
        if history is not None and (not isinstance(history, list) or len(history) > 40):
            raise OrchestrateError("Conversation history has an invalid format")
        messages = []
        for item in history or []:
            if (not isinstance(item, dict) or set(item) != {"role", "content"}
                    or item["role"] not in ("system", "user", "assistant")
                    or not isinstance(item["content"], str)
                    or len(item["content"]) > MAX_HISTORY_ITEM_CHARACTERS):
                raise OrchestrateError("Conversation history has an invalid format")
            messages.append({"role": item["role"], "content": item["content"]})
        values = context if context is not None else {}
        try:
            if not isinstance(values, dict) or any(not isinstance(key, str) for key in values):
                raise ValueError("Invalid context")
            if len(json.dumps(values, allow_nan=False)) > 8192:
                raise ValueError("Oversized context")
            if sum(len(item["content"]) for item in messages) > 256000:
                raise ValueError("Oversized history")
        except (TypeError, ValueError):
            raise OrchestrateError("Server context or conversation history has an invalid format") from None
        # Context is deliberately not interpolated into messages. Resend it on
        # every turn: IBM scopes context to a single run, even on reused threads.
        return {"messages": [*messages, {"role": "user", "content": message.strip()}],
                "stream": False, "context": values}

    @staticmethod
    def _reply(response: httpx.Response) -> AgentReply:
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Invalid response")
            thread_id = _uuid(result["thread_id"])
            choices = result["choices"]
            if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                raise ValueError("Missing choices")
            message = choices[0]["message"]
            if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
                raise ValueError("Missing assistant message")
            content = message["content"]
            if isinstance(content, list):
                texts = []
                for block in content:
                    if not isinstance(block, dict):
                        raise ValueError("Invalid content block")
                    if block.get("response_type", block.get("type")) == "text":
                        if not isinstance(block.get("text"), str):
                            raise ValueError("Invalid text block")
                        texts.append(block["text"])
                content = "\n".join(texts)
            if not isinstance(content, str) or not content.strip() or len(content) > 100000:
                raise ValueError("Empty or invalid assistant text")
            return AgentReply(message=content.strip(), thread_id=thread_id)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise OrchestrateError("IBM Orchestrate returned an invalid chat response") from None

    def send(self, message: str, thread_id: str | None = None, history: list | None = None,
             context: dict | None = None) -> AgentReply:
        body = self._body(message, history, context)
        headers = {"Accept": "application/json"}
        if thread_id is not None:
            try:
                headers["X-IBM-THREAD-ID"] = _uuid(thread_id)
            except (ValueError, TypeError):
                raise OrchestrateError("Conversation thread ID is invalid") from None
        token = self._token()
        headers["Authorization"] = "Bearer " + token
        try:
            response = self.client.post(self.url, headers=headers, json=body,
                                        timeout=self.timeout, follow_redirects=False)
            # Retry only an authentication rejection, before an agent run is
            # accepted. Never retry a timeout, 429, server error or bad response.
            if response.status_code == 401 and self.settings.api_key:
                self._invalidate_token(token)
                headers["Authorization"] = "Bearer " + self._token()
                response = self.client.post(self.url, headers=headers, json=body,
                                            timeout=self.timeout, follow_redirects=False)
            response.raise_for_status()
        except OrchestrateError:
            raise
        except httpx.TimeoutException:
            raise OrchestrateError("IBM Orchestrate timed out; the run may have started, so no automatic retry was made") from None
        except httpx.HTTPError:
            raise OrchestrateError("IBM Orchestrate request failed; check integration permissions and service availability") from None
        return self._reply(response)

    def close(self):
        if self._owns_client:
            self.client.close()
