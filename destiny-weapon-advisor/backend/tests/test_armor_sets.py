from fastapi.testclient import TestClient

from app.main import app

_SET = {
    "name": "pytest-armor-set",
    "className": "Warlock",
    "characterId": "char-123",
    "tier": 17,
    "items": [
        {"instanceId": "i1", "itemHash": 11, "slot": "Helmet", "name": "Ferropotent Cover"},
        {"instanceId": "i2", "itemHash": 22, "slot": "Class Item", "name": "Swordmaster's Bond"},
    ],
}


def test_put_get_delete_round_trip():
    client = TestClient(app)
    try:
        assert client.put("/api/armor-sets", json=_SET).status_code == 200
        body = client.get("/api/armor-sets").json()
        match = next((s for s in body["armorSets"] if s["name"] == "pytest-armor-set"), None)
        assert match is not None
        assert match["className"] == "Warlock"
        assert match["characterId"] == "char-123"
        assert match["tier"] == 17
        assert len(match["items"]) == 2
        assert match["items"][0]["slot"] == "Helmet"
    finally:
        assert client.delete("/api/armor-sets/pytest-armor-set").status_code == 200
    after = client.get("/api/armor-sets").json()["armorSets"]
    assert all(s["name"] != "pytest-armor-set" for s in after)


def test_put_upsert_overwrites():
    client = TestClient(app)
    try:
        client.put("/api/armor-sets", json=_SET)
        updated = {**_SET, "tier": 20}
        client.put("/api/armor-sets", json=updated)
        body = client.get("/api/armor-sets").json()["armorSets"]
        match = next(s for s in body if s["name"] == "pytest-armor-set")
        assert match["tier"] == 20
    finally:
        client.delete("/api/armor-sets/pytest-armor-set")


def test_put_missing_field_returns_422():
    client = TestClient(app)
    resp = client.put("/api/armor-sets", json={"name": "x"})
    assert resp.status_code == 422
