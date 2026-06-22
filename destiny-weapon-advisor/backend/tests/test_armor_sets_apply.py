from fastapi.testclient import TestClient

from app.main import app


def test_apply_unknown_set_returns_404_with_detail():
    client = TestClient(app)
    resp = client.post("/api/armor-sets/apply", json={"name": "does-not-exist-xyz"})
    assert resp.status_code == 404
    # Asserting the specific detail makes this a meaningful RED: before the route
    # exists FastAPI returns 404 with detail "Not Found"; only the implemented
    # route returns this message.
    assert resp.json()["detail"] == "Armor set not found."
