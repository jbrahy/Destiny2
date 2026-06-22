from fastapi.testclient import TestClient

from app.main import app


def test_recommendations_default_context_ok():
    client = TestClient(app)
    resp = client.get("/api/recommendations")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
    assert body["context"] == "General (PvE)"


def test_recommendations_pvp_context_label():
    client = TestClient(app)
    resp = client.get("/api/recommendations", params={"context": "general-pvp"})
    assert resp.status_code == 200
    assert resp.json()["context"] == "General (PvP)"


def test_recommendations_unknown_context_falls_back():
    client = TestClient(app)
    resp = client.get("/api/recommendations", params={"context": "Nonexistent Activity"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["context"] == "Nonexistent Activity"
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
