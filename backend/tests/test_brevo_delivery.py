"""Restricted Brevo HTTPS sending: receipts, owner scope and uncertain outcomes."""
import json

import httpx
import pytest

from app import notifications as n
from app.notification_models import NotificationDelivery
from test_notifications import authorization, client, enable_digest, store  # noqa: F401 - shared isolated fixtures

Settings = n.NotificationSettings


def config():
    return Settings(_env_file=None, notification_email_enabled=True,
        notification_email_transport="brevo_api", notification_brevo_api_key="synthetic-brevo-key",
        notification_from_email="staytus@example.invalid")


def delivery():
    return NotificationDelivery(id="synthetic-delivery", account_id="a", profile_id="p-a",
        recipient="verified-a@example.invalid", provider="google", connection_id="connection-a",
        dedup_key="test:synthetic|profile:1", subject="Test reminder", body="Synthetic reminder only")


def transport(monkeypatch, handler):
    constructor = httpx.Client
    monkeypatch.setattr(n.httpx, "Client", lambda **kwargs: constructor(transport=httpx.MockTransport(handler), **kwargs))


def test_brevo_readiness_requires_its_key_not_smtp_credentials():
    settings = config()
    assert n.email_readiness(settings)["configured"]
    settings.notification_brevo_api_key = ""
    assert n.email_readiness(settings)["missing"] == ["NOTIFICATION_BREVO_API_KEY"]


def test_brevo_sends_fixed_endpoint_and_returns_provider_receipt(monkeypatch):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(201, json={"messageId": "<synthetic@brevo.invalid>"})
    transport(monkeypatch, handler)
    assert n.send_brevo_api(delivery(), config()) == {"transport": "brevo_api", "provider_message_id": "<synthetic@brevo.invalid>"}
    request = seen[0]
    assert str(request.url) == "https://api.brevo.com/v3/smtp/email"
    assert request.headers["api-key"] == "synthetic-brevo-key"
    body = json.loads(request.content)
    assert body["to"] == [{"email": "verified-a@example.invalid"}]
    assert body["sender"] == {"name": "Staytus", "email": "staytus@example.invalid"}
    assert body["textContent"] == "Synthetic reminder only" and "synthetic-brevo-key" not in str(body)


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (403, False), (429, True)])
def test_brevo_definitive_rejection_is_bounded_and_redacted(monkeypatch, status, retryable):
    transport(monkeypatch, lambda request: httpx.Response(status, json={"message": "sensitive-provider-detail"}))
    with pytest.raises(n.DeliveryRejected) as failure:
        n.send_brevo_api(delivery(), config())
    assert failure.value.retryable is retryable and "sensitive-provider-detail" not in str(failure.value)


@pytest.mark.parametrize("status", [302, 408, 500, 502])
def test_brevo_redirects_and_ambiguous_server_responses_do_not_retry(monkeypatch, status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers={"Location": "https://untrusted.invalid/"})
    transport(monkeypatch, handler)
    with pytest.raises(n.DeliveryUncertain):
        n.send_brevo_api(delivery(), config())
    assert len(seen) == 1


def test_brevo_lost_response_and_missing_receipt_remain_uncertain(monkeypatch):
    def timeout(request):
        raise httpx.ReadTimeout("private-provider-detail")
    transport(monkeypatch, timeout)
    with pytest.raises(n.DeliveryUncertain) as failure:
        n.send_brevo_api(delivery(), config())
    assert "private-provider-detail" not in str(failure.value)


def test_brevo_empty_success_does_not_claim_a_verified_send(monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(201, json={}))
    with pytest.raises(n.DeliveryUncertain):
        n.send_brevo_api(delivery(), config())


def test_owned_test_endpoint_uses_selected_brevo_transport(client, store, monkeypatch):
    enable_digest(store[0])
    monkeypatch.setattr(n, "NotificationSettings", config)
    monkeypatch.setattr(n, "send_smtp", lambda *args: pytest.fail("Unexpected SMTP fallback"))
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(201, json={"messageId": "<owned-test@brevo.invalid>"})
    transport(monkeypatch, handler)
    response = client.post("/api/v1/notifications/test-email", headers=authorization(), json={})
    assert response.status_code == 200 and response.json()["provider_accepted"]
    assert len(calls) == 1 and calls[0]["to"] == [{"email": "verified-a@example.invalid"}]
