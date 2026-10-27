"""Contract smoke tests. Run with CC_DEMO_MODE=1 in a disposable SQLite database."""
from auth_support import login_response
import pytest
from cc_api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app({'TESTING': True, 'DEMO_MODE': True, 'APP_ENV': 'synthetic_dev', 'SECRET_KEY': 'pytest-only', 'DB_PATH': str(tmp_path / 'test.sqlite')})
    return app.test_client()


def switch(client, uid):
    response = login_response(client, uid)
    assert response.status_code == 200
    return response.json['csrf_token']


def test_session_required(client):
    assert client.get('/api/v1/doctors/me/patients').status_code == 401


def test_grants_remove_medication_from_every_doctor_view(client):
    switch(client, 'doc_ther')
    data = client.get('/api/v1/doctors/me/patients').json
    assert data['total'] == 1
    assert 'medication_label' not in data['items'][0]
    overview = client.get('/api/v1/doctors/me/patients/pat_a/overview').json
    assert not any(s['key'] == 'medications' for s in overview['sections'])
    assert 'Учебный препарат X' not in str(overview)
    assert client.get('/api/v1/doctors/me/patients/pat_b/overview').status_code == 404


def test_critical_alert_is_assigned_to_authorized_doctor(client):
    csrf = switch(client, 'doc_psy')
    items = client.get('/api/v1/doctors/me/patients').json['items']
    assert items[0]['attention_level'] == 'critical'
    assert client.post('/api/v1/alerts/al_001/acknowledge').status_code == 403
    r = client.post('/api/v1/alerts/al_001/acknowledge', headers={'X-CSRF-Token': csrf}, json={})
    assert r.status_code == 200
    assert r.json['status'] == 'acknowledged'
    assert client.post('/api/v1/alerts/al_001/acknowledge', headers={'X-CSRF-Token': csrf}, json={}).status_code == 409


def test_patient_can_create_self_report_not_doctor(client):
    csrf = switch(client, 'pat_01')
    r = client.post('/api/v1/patients/me/check-ins', json={'mood_score': 3, 'comparison': 'same'}, headers={'X-CSRF-Token': csrf})
    assert r.status_code == 201
    assert r.json['source_type'] == 'patient_self_report'
    csrf = switch(client, 'doc_psy')
    assert client.post('/api/v1/patients/me/check-ins', json={'mood_score': 3, 'comparison': 'same'}, headers={'X-CSRF-Token': csrf}).status_code == 403
