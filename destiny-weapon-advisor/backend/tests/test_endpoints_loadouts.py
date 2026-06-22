"""Session-aware tests for per-user loadouts:
  GET /api/loadouts, PUT /api/loadouts, DELETE /api/loadouts/{name},
  POST /api/loadouts/apply.

All tests:
  - require a valid session (401 without one)
  - state-changing routes require CSRF header (403 without one)
  - operate on per-user data (isolation between users A and B)
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAR_ID = "char-ldout-123"
_INSTANCE_ID = "ldout-inst-1"
_ITEM_HASH = 7771234

_LOADOUT = {
    "name": "pytest-loadout",
    "characterId": _CHAR_ID,
    "items": [
        {"instanceId": _INSTANCE_ID, "itemHash": _ITEM_HASH},
    ],
}

_PROFILE_WITH_ITEM = {
    "characters": {
        "data": {
            _CHAR_ID: {
                "classType": 0,
                "light": 1800,
                "dateLastPlayed": "2024-01-01T00:00:00Z",
            }
        }
    },
    "characterEquipment": {"data": {}},
    "characterInventories": {
        "data": {
            _CHAR_ID: {
                "items": [
                    {"itemInstanceId": _INSTANCE_ID, "itemHash": _ITEM_HASH}
                ]
            }
        }
    },
    "profileInventory": {"data": {"items": []}},
    "itemComponents": {},
}

_FRESH_PROFILE_SENTINEL = {
    "_refreshed": True,
    "characters": {"data": {}},
    "characterEquipment": {"data": {}},
    "characterInventories": {"data": {}},
    "profileInventory": {"data": {"items": []}},
    "itemComponents": {},
}


def _csrf(client) -> dict:
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


# ---------------------------------------------------------------------------
# 401 without session
# ---------------------------------------------------------------------------

async def test_loadouts_get_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/loadouts")
    assert r.status_code == 401


async def test_loadouts_put_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put("/api/loadouts", json=_LOADOUT)
    assert r.status_code == 401


async def test_loadouts_delete_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.delete("/api/loadouts/pytest-loadout")
    assert r.status_code == 401


async def test_loadouts_apply_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/loadouts/apply", json={"name": "pytest-loadout"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# CSRF required on PUT/DELETE/apply
# ---------------------------------------------------------------------------

async def test_loadouts_put_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-nocsrf1")
    r = await app_client.put("/api/loadouts", json=_LOADOUT)
    assert r.status_code == 403


async def test_loadouts_delete_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-nocsrf2")
    r = await app_client.delete("/api/loadouts/pytest-loadout")
    assert r.status_code == 403


async def test_loadouts_apply_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-nocsrf3")
    r = await app_client.post("/api/loadouts/apply", json={"name": "pytest-loadout"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Happy path: save / get / delete round-trip
# ---------------------------------------------------------------------------

async def test_loadout_put_get_delete_round_trip(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-rt1")
    csrf = _csrf(app_client)

    r = await app_client.put("/api/loadouts", json=_LOADOUT, headers=csrf)
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await app_client.get("/api/loadouts")
    assert r.status_code == 200
    loadouts = r.json()["loadouts"]
    match = next((lo for lo in loadouts if lo["name"] == "pytest-loadout"), None)
    assert match is not None
    assert match["characterId"] == _CHAR_ID
    assert len(match["items"]) == 1
    assert match["items"][0]["instanceId"] == _INSTANCE_ID

    r = await app_client.delete("/api/loadouts/pytest-loadout", headers=csrf)
    assert r.status_code == 200

    r = await app_client.get("/api/loadouts")
    assert all(lo["name"] != "pytest-loadout" for lo in r.json()["loadouts"])


async def test_loadout_put_upsert_overwrites(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-ups1")
    csrf = _csrf(app_client)

    await app_client.put("/api/loadouts", json=_LOADOUT, headers=csrf)
    updated = {**_LOADOUT, "items": []}
    r = await app_client.put("/api/loadouts", json=updated, headers=csrf)
    assert r.status_code == 200

    r = await app_client.get("/api/loadouts")
    match = next((lo for lo in r.json()["loadouts"] if lo["name"] == "pytest-loadout"), None)
    assert match is not None
    assert match["items"] == []

    # Cleanup
    await app_client.delete("/api/loadouts/pytest-loadout", headers=csrf)


async def test_loadout_put_missing_field_returns_422(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-422")
    csrf = _csrf(app_client)
    r = await app_client.put("/api/loadouts", json={"name": "x"}, headers=csrf)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Isolation: user B does not see user A's loadouts
# ---------------------------------------------------------------------------

async def test_loadout_isolation_b_does_not_see_a(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-iso-a")
    csrf_a = _csrf(app_client)
    await app_client.put("/api/loadouts", json=_LOADOUT, headers=csrf_a)

    r_a = await app_client.get("/api/loadouts")
    assert any(lo["name"] == "pytest-loadout" for lo in r_a.json()["loadouts"])

    await login_user(app_client, monkeypatch, bungie_id="bm-ld-iso-b")
    r_b = await app_client.get("/api/loadouts")
    assert r_b.status_code == 200
    assert all(lo["name"] != "pytest-loadout" for lo in r_b.json()["loadouts"])


# ---------------------------------------------------------------------------
# Apply: 404 for unknown loadout
# ---------------------------------------------------------------------------

async def test_apply_unknown_loadout_returns_404(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ld-apply-404")
    csrf = _csrf(app_client)
    r = await app_client.post("/api/loadouts/apply", json={"name": "does-not-exist-xyz"},
                               headers=csrf)
    assert r.status_code == 404
    assert r.json()["detail"] == "Loadout not found."


# ---------------------------------------------------------------------------
# Apply happy path: mocked Bungie; per-user profile refreshed
# ---------------------------------------------------------------------------

async def test_apply_loadout_happy_path(app_client, monkeypatch, clean_db):
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-ld-apply-happy")
    csrf = _csrf(app_client)

    # Save the loadout first.
    r = await app_client.put("/api/loadouts", json=_LOADOUT, headers=csrf)
    assert r.status_code == 200

    # Seed profile cache.
    await cache_repo.set(pool, uid, "profile_cache",
                         json.dumps(_PROFILE_WITH_ITEM), settings.user_cache_ttl_seconds)
    await cache_repo.set(pool, uid, "profile_membership_id",
                         "bm-ld-apply-happy", settings.user_cache_ttl_seconds)

    # Monkeypatch Bungie functions.
    import app.main as main_module

    async def fake_transfer_item(*args, **kwargs):
        return None

    async def fake_equip_item(*args, **kwargs):
        return None

    async def fake_get_profile(*args, **kwargs):
        return _FRESH_PROFILE_SENTINEL

    monkeypatch.setattr(main_module, "transfer_item", fake_transfer_item)
    monkeypatch.setattr(main_module, "equip_item", fake_equip_item)
    monkeypatch.setattr(main_module, "get_profile", fake_get_profile)

    import app.bungie_session as bs_module

    async def fake_valid_access_token(pool_arg, uid_arg, settings_arg, client, key):
        return ("acc-token", 3, "bm-ld-apply-happy")

    monkeypatch.setattr(bs_module, "valid_access_token", fake_valid_access_token)

    r = await app_client.post("/api/loadouts/apply", json={"name": "pytest-loadout"},
                               headers=csrf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "results" in body

    # Verify per-user profile_cache was refreshed with the sentinel.
    cached_raw = await cache_repo.get(pool, uid, "profile_cache")
    assert cached_raw is not None
    cached = json.loads(cached_raw)
    assert cached.get("_refreshed") is True
