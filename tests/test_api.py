from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_wrong_secret_rejected():
    assert client.post("/webhook/observation", json={}, headers={"X-Webhook-Secret": "nope"}).status_code == 401
    assert client.post("/webhook/condition", json={}).status_code == 401


def test_own_derived_observation_is_skipped():
    r = client.post("/webhook/observation", json={"resourceType": "Observation", "status": "preliminary"},
                    headers={"X-Webhook-Secret": "test-secret"})
    assert r.json() == {"skipped": True}


def test_unconfigured_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "")
    assert client.post("/webhook/condition", json={}, headers={"X-Webhook-Secret": ""}).status_code == 503