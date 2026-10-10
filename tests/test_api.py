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

def test_nlp_endpoints_need_secret_and_fail_closed_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    for path in ("/nlp/suggest-code", "/nlp/extract-note", "/ask"):
        assert client.post(path, json={}).status_code == 401
        assert client.post(path, json={}, headers={"X-Webhook-Secret": "test-secret"}).status_code == 503
    assert "Ask the chart" in client.get("/ask-page").text


def test_installable_app_files_are_served_and_data_is_never_cached():
    m = client.get("/manifest.webmanifest")
    assert m.status_code == 200 and m.json()["display"] == "standalone"
    assert client.get("/icon-192.png").content[:4] == b"\x89PNG" and client.get("/icon-512.png").status_code == 200
    sw = client.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert '"/ask"' not in sw.text and "/previsit" not in sw.text.split("FILES")[1].split("]")[0]
    assert 'rel="manifest"' in client.get("/ask-page").text
