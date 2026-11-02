"""Calendar exports retain approved alarm/date content across Apple-compatible ICS."""
import pytest


def approved(client, headers, payload):
    response = client.post("/api/v1/approvals", headers=headers, json={"kind": "calendar", "payload": payload})
    assert response.status_code == 201
    proposal = response.json()
    base = "/api/v1/approvals/" + proposal["id"]
    assert client.post(base + "/preview", headers=headers).status_code == 200
    result = client.post(base + "/approve", headers=headers, json={"payload_hash": proposal["payload_hash"]})
    assert result.status_code == 200
    return base, result.json()


def test_calendar_file_has_approved_alarm_and_exclusive_end(env, student):
    client, _ = env
    base, result = approved(client, student, {"title": "Prepare documents", "date": "2027-12-31", "reminder_minutes": 10080})
    assert result["receipt"]["mode"] == "file_export"
    response = client.get(base + "/calendar.ics", headers=student)
    assert response.status_code == 200
    assert "DTSTART;VALUE=DATE:20271231" in response.text
    assert "DTEND;VALUE=DATE:20280101" in response.text
    assert "TRIGGER:-PT10080M" in response.text and "ACTION:DISPLAY" in response.text


def test_calendar_unicode_folding_and_text_cannot_inject_events(env, student):
    client, _ = env
    title = "准备材料🌏" * 20
    description = "Meeting\nEND:VEVENT\nBEGIN:VEVENT\nSUMMARY:Injected"
    base, _ = approved(client, student, {"title": title, "date": "2027-03-16", "description": description})
    content = client.get(base + "/calendar.ics", headers=student).text
    assert all(len(line.encode("utf-8")) <= 75 for line in content.split("\r\n"))
    unfolded = content.replace("\r\n ", "")
    assert f"SUMMARY:{title}\r\n" in unfolded
    assert unfolded.count("\r\nBEGIN:VEVENT\r\n") == 1
    assert "DESCRIPTION:Meeting\\nEND:VEVENT\\nBEGIN:VEVENT\\nSUMMARY:Injected" in unfolded


@pytest.mark.parametrize("extra", [{"provider": "icloud"}, {"reminder_minutes": -1}, {"reminder_minutes": 40321}])
def test_calendar_unsupported_target_or_alarm_cannot_be_approved(env, student, extra):
    client, _ = env
    response = client.post("/api/v1/approvals", headers=student, json={"kind": "calendar",
        "payload": {"title": "Prepare", "date": "2027-03-16", **extra}})
    assert response.status_code == 422
