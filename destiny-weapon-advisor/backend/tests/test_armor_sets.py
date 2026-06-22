"""Session-aware tests for per-user armor sets: GET/PUT/DELETE /api/armor-sets.

All tests:
  - require a valid session (401 without one)
  - state-changing routes require CSRF header (403 without one)
  - operate on per-user data (user A's sets are invisible to user B)
"""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

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


def _csrf(client) -> dict:
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


# ---------------------------------------------------------------------------
# 401 without session
# ---------------------------------------------------------------------------

async def test_armor_sets_get_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/armor-sets")
    assert r.status_code == 401


async def test_armor_sets_put_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put("/api/armor-sets", json=_SET)
    assert r.status_code == 401


async def test_armor_sets_delete_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.delete("/api/armor-sets/pytest-armor-set")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# CSRF required on PUT/DELETE
# ---------------------------------------------------------------------------

async def test_armor_sets_put_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-as-nocsrf1")
    r = await app_client.put("/api/armor-sets", json=_SET)
    assert r.status_code == 403


async def test_armor_sets_delete_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-as-nocsrf2")
    r = await app_client.delete("/api/armor-sets/pytest-armor-set")
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Happy path: save / get / delete round-trip
# ---------------------------------------------------------------------------

async def test_armor_set_put_get_delete_round_trip(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-as-rt1")
    csrf = _csrf(app_client)

    r = await app_client.put("/api/armor-sets", json=_SET, headers=csrf)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await app_client.get("/api/armor-sets")
    assert r.status_code == 200
    sets = r.json()["armorSets"]
    match = next((s for s in sets if s["name"] == "pytest-armor-set"), None)
    assert match is not None
    assert match["className"] == "Warlock"
    assert match["characterId"] == "char-123"
    assert match["tier"] == 17
    assert len(match["items"]) == 2
    assert match["items"][0]["slot"] == "Helmet"

    r = await app_client.delete("/api/armor-sets/pytest-armor-set", headers=csrf)
    assert r.status_code == 200

    r = await app_client.get("/api/armor-sets")
    assert all(s["name"] != "pytest-armor-set" for s in r.json()["armorSets"])


async def test_armor_set_put_upsert_overwrites(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-as-ups1")
    csrf = _csrf(app_client)

    await app_client.put("/api/armor-sets", json=_SET, headers=csrf)
    updated = {**_SET, "tier": 20}
    r = await app_client.put("/api/armor-sets", json=updated, headers=csrf)
    assert r.status_code == 200

    r = await app_client.get("/api/armor-sets")
    match = next((s for s in r.json()["armorSets"] if s["name"] == "pytest-armor-set"), None)
    assert match is not None
    assert match["tier"] == 20

    # Cleanup
    await app_client.delete("/api/armor-sets/pytest-armor-set", headers=csrf)


async def test_armor_set_put_missing_field_returns_422(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-as-422")
    csrf = _csrf(app_client)
    r = await app_client.put("/api/armor-sets", json={"name": "x"}, headers=csrf)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Isolation: user B does not see user A's armor set
# ---------------------------------------------------------------------------

async def test_armor_set_isolation_b_does_not_see_a(app_client, monkeypatch, clean_db):
    # User A saves a set.
    await login_user(app_client, monkeypatch, bungie_id="bm-as-iso-a")
    csrf_a = _csrf(app_client)
    await app_client.put("/api/armor-sets", json=_SET, headers=csrf_a)

    r_a = await app_client.get("/api/armor-sets")
    assert any(s["name"] == "pytest-armor-set" for s in r_a.json()["armorSets"])

    # User B logs in.
    await login_user(app_client, monkeypatch, bungie_id="bm-as-iso-b")
    r_b = await app_client.get("/api/armor-sets")
    assert r_b.status_code == 200
    assert all(s["name"] != "pytest-armor-set" for s in r_b.json()["armorSets"])
