from fastapi.testclient import TestClient

from app.main import app


def test_unknown_activity_returns_404():
    client = TestClient(app)
    resp = client.get("/api/loadout-suggestion", params={"activity": "Nope"})
    assert resp.status_code == 404


def test_known_activity_returns_suggestion_shape():
    client = TestClient(app)
    # Seeded activities are always present via load_activities.
    resp = client.get("/api/loadout-suggestion", params={"activity": "Crota's End (Raid)"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity"] == "Crota's End (Raid)"
    assert set(body["weapons"]) == {"Primary", "Special", "Heavy"}
    assert "subclass" in body and "elementCoverage" in body
