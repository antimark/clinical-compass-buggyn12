"""Flask integration checks; run after pip install -r requirements.txt."""
from __future__ import annotations
import pytest
flask = pytest.importorskip("flask", reason="Flask is not installed in this execution environment")
from clinical_compass.api import create_app


def test_login_and_pii_api_disabled_then_enabled(active):
    db, ids, cipher, engine, key = active
    app = create_app({"TESTING": True, "SECRET_KEY": "X" * 48,
                      "DATABASE_URL": str(engine.url), "PII_ENCRYPTION_KEY": key,
                      "SESSION_COOKIE_SECURE": False})
    client = app.test_client()
    csrf = client.get("/api/v1/auth/csrf").json["csrf_token"]
    result = client.post("/api/v1/auth/login", json={"username": "clinic_admin",
                                                     "password": "ValidPassword!222"},
                         headers={"X-CSRF-Token": csrf})
    assert result.status_code == 200
    uri = f"/api/v1/clinics/{ids['org1']}/patients"
    response = client.get(uri)
    assert response.status_code == 200
    assert any(item["fields"] == {"first_name": "Alice"} for item in response.json["items"])
    # A different clinic's identifiers never appear here.
    assert ids["ref3"] not in str(response.json)
    # Clinical entities are never in the administrative schema.
    assert "clinical_records" not in str(response.json)
    assert response.headers["Cache-Control"].startswith("no-store")
    assert client.get(f"/api/v1/clinics/{ids['org2']}/patients").status_code == 403


def test_anonymous_access_and_csrf(active):
    db, ids, cipher, engine, key = active
    app = create_app({"TESTING": True, "SECRET_KEY": "X" * 48,
                      "DATABASE_URL": str(engine.url), "PII_ENCRYPTION_KEY": key,
                      "SESSION_COOKIE_SECURE": False})
    client = app.test_client()
    assert client.get(f"/api/v1/clinics/{ids['org1']}/patients").status_code == 403
    assert client.post("/api/v1/auth/login", json={"username": "clinic_admin",
                                                   "password": "ValidPassword!222"}).status_code == 403
