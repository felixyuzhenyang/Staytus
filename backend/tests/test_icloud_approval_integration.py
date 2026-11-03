"""The real application routes keep iCloud writes behind exact human approval."""
from test_icloud_calendar import cloud as _icloud_fixture, link

icloud_transport = _icloud_fixture


def preview(client, headers):
    response = client.post('/api/v1/approvals', headers=headers, json={'kind': 'calendar',
        'payload': {'provider': 'icloud', 'title': 'Synthetic planning reminder', 'date': '2030-06-12'}})
    assert response.status_code == 201, response.text
    item = response.json()
    path = '/api/v1/approvals/' + item['id']
    assert item['payload']['_connector_target']['provider'] == 'icloud'
    assert item['target_account'] == 'synthetic@example.invalid · Personal'
    assert client.post(path + '/preview', headers=headers).status_code == 200
    return path, item


def test_real_approval_route_creates_only_once_and_cannot_export_remote_event(env, student, icloud_transport):
    client, _ = env
    cloud_client, _, calls, *_ = icloud_transport
    link(cloud_client)
    providers = client.get('/api/v1/connections', headers=student).json()['providers']
    assert next(item for item in providers if item['provider'] == 'icloud')['calendar_write']
    path, item = preview(client, student)
    assert not any(call.method == 'PUT' for call in calls)
    approved = client.post(path + '/approve', headers=student, json={'payload_hash': item['payload_hash']})
    assert approved.status_code == 200, approved.text
    assert approved.json()['receipt']['provider'] == 'icloud'
    assert approved.json()['receipt']['attendees_notified'] is False
    assert client.post(path + '/approve', headers=student, json={'payload_hash': item['payload_hash']}).status_code == 409
    assert client.get(path + '/calendar.ics', headers=student).status_code == 409
    assert sum(call.method == 'PUT' for call in calls) == 1


def test_uncertain_icloud_write_persists_terminal_receipt_without_retry(env, student, icloud_transport):
    client, _ = env
    cloud_client, _, calls, state, *_ = icloud_transport
    link(cloud_client)
    path, item = preview(client, student)
    state['failure'] = 'timeout'
    response = client.post(path + '/approve', headers=student, json={'payload_hash': item['payload_hash']})
    assert response.status_code == 502
    rows = client.get('/api/v1/approvals', headers=student).json()['approvals']
    assert next(row for row in rows if row['id'] == item['id'])['status'] == 'FAILED_UNCONFIRMED'
    assert client.post(path + '/approve', headers=student, json={'payload_hash': item['payload_hash']}).status_code == 409
    assert sum(call.method == 'PUT' for call in calls) == 1
