from fastapi.testclient import TestClient

from app.main import app


def test_transfer_missing_fields_returns_422():
    client = TestClient(app)
    resp = client.post("/api/transfer", json={"instanceId": "x"})
    assert resp.status_code == 422


def test_perk_put_missing_rating_returns_422():
    client = TestClient(app)
    resp = client.put("/api/perks", json={"name": "Frenzy"})
    assert resp.status_code == 422


def test_membership_select_missing_fields_returns_422():
    client = TestClient(app)
    resp = client.post("/api/memberships/select", json={"membershipType": 2})
    assert resp.status_code == 422


def test_transfer_bulk_missing_fields_returns_422():
    client = TestClient(app)
    resp = client.post("/api/transfer/bulk", json={})
    assert resp.status_code == 422


# test_counts_endpoint_ok removed — counts now requires a session.
# Covered by test_endpoints_read.py::test_counts_with_seeded_cache and
# test_endpoints_read.py::test_counts_401_without_session.
