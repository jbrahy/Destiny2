"""Validation (422) tests — logged-in user sends an incomplete request body.

FastAPI returns 422 only after auth passes, so these tests use the shared
app_client fixture (which has a running lifespan + test-DB pool).
"""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _csrf_header(client) -> dict:
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


async def test_transfer_missing_fields_returns_422(app_client, monkeypatch, clean_db):
    """POST /api/transfer with missing required fields returns 422."""
    await login_user(app_client, monkeypatch, bungie_id="bm-422-xfer")
    csrf = _csrf_header(app_client)
    # instanceId is present but itemHash, targetCharacterId are missing
    r = await app_client.post("/api/transfer", json={"instanceId": "x"}, headers=csrf)
    assert r.status_code == 422


async def test_perk_put_missing_rating_returns_422(app_client, monkeypatch, clean_db):
    """PUT /api/perks with missing required 'rating' field returns 422."""
    await login_user(app_client, monkeypatch, bungie_id="bm-422-perk")
    # No CSRF required for PUT /api/perks
    r = await app_client.put("/api/perks", json={"name": "Frenzy"})
    assert r.status_code == 422


async def test_membership_select_missing_fields_returns_422(app_client, monkeypatch, clean_db):
    """POST /api/memberships/select with missing 'membershipId' returns 422."""
    await login_user(app_client, monkeypatch, bungie_id="bm-422-memsel")
    # membershipId is missing
    r = await app_client.post("/api/memberships/select", json={"membershipType": 2})
    assert r.status_code == 422


async def test_transfer_bulk_missing_fields_returns_422(app_client, monkeypatch, clean_db):
    """POST /api/transfer/bulk with empty body returns 422."""
    await login_user(app_client, monkeypatch, bungie_id="bm-422-bulk")
    csrf = _csrf_header(app_client)
    r = await app_client.post("/api/transfer/bulk", json={}, headers=csrf)
    assert r.status_code == 422
