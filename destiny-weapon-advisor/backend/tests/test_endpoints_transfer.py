"""Tests for write-to-Bungie endpoints:
  POST /api/transfer, POST /api/transfer/bulk,
  GET /api/postmaster, POST /api/postmaster/pull.

CSRF double-submit pattern is enforced on all state-changing POSTs.
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Minimal profile fixture with one item in the vault
# ---------------------------------------------------------------------------

_INSTANCE_ID = "item-inst-1"
_ITEM_HASH = 9876543
_CHAR_ID = "char-abc-123"

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
    "characterInventories": {"data": {}},
    "profileInventory": {
        "data": {
            "items": [
                {"itemInstanceId": _INSTANCE_ID, "itemHash": _ITEM_HASH}
            ]
        }
    },
    "itemComponents": {},
}

# Sentinel returned by fake_get_profile so we can verify cache was refreshed
_FRESH_PROFILE_SENTINEL = {"_refreshed": True, "characters": {"data": {}},
                           "characterEquipment": {"data": {}},
                           "characterInventories": {"data": {}},
                           "profileInventory": {"data": {"items": []}},
                           "itemComponents": {}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csrf_header(client) -> dict:
    """Read the csrftoken cookie from the client's cookie jar."""
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


# ---------------------------------------------------------------------------
# 401 without session — POST /api/transfer
# ---------------------------------------------------------------------------

async def test_transfer_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/transfer", json={
            "instanceId": _INSTANCE_ID,
            "itemHash": _ITEM_HASH,
            "targetCharacterId": _CHAR_ID,
            "equip": False,
        })
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 403 without CSRF header — POST /api/transfer
# ---------------------------------------------------------------------------

async def test_transfer_403_without_csrf(app_client, monkeypatch, clean_db):
    """Logged-in user but missing X-CSRF-Token header → 403."""
    await login_user(app_client, monkeypatch, bungie_id="bm-xfer-nocsrf")
    r = await app_client.post("/api/transfer", json={
        "instanceId": _INSTANCE_ID,
        "itemHash": _ITEM_HASH,
        "targetCharacterId": _CHAR_ID,
        "equip": False,
    })
    # No CSRF header → 403
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Happy path — POST /api/transfer
# ---------------------------------------------------------------------------

async def test_transfer_happy_path(app_client, monkeypatch, clean_db):
    """Logged-in user with CSRF; mocked Bungie calls; profile cache refreshed."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-xfer-happy")

    # Seed profile_cache and profile_membership_id for this user
    await cache_repo.set(pool, uid, "profile_cache",
                         json.dumps(_PROFILE_WITH_ITEM), settings.user_cache_ttl_seconds)
    await cache_repo.set(pool, uid, "profile_membership_id",
                         "bm-xfer-happy", settings.user_cache_ttl_seconds)

    # Monkeypatch Bungie functions — no real network calls
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

    csrf = _csrf_header(app_client)
    r = await app_client.post("/api/transfer", json={
        "instanceId": _INSTANCE_ID,
        "itemHash": _ITEM_HASH,
        "targetCharacterId": _CHAR_ID,
        "equip": False,
    }, headers=csrf)
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}

    # Verify _save_profile refreshed the per-user profile_cache
    cached_raw = await cache_repo.get(pool, uid, "profile_cache")
    assert cached_raw is not None
    cached = json.loads(cached_raw)
    assert cached.get("_refreshed") is True


# ---------------------------------------------------------------------------
# GET /api/postmaster — 401 without session
# ---------------------------------------------------------------------------

async def test_postmaster_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/postmaster")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/postmaster — returns items from seeded cache
# ---------------------------------------------------------------------------

_POSTMASTER_BUCKET = 215593132

_PROFILE_WITH_POSTMASTER = {
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
                    {
                        "itemInstanceId": "pm-inst-1",
                        "itemHash": _ITEM_HASH,
                        "bucketHash": _POSTMASTER_BUCKET,
                        "quantity": 1,
                    }
                ]
            }
        }
    },
    "profileInventory": {"data": {"items": []}},
    "itemComponents": {},
}


async def test_postmaster_returns_items(app_client, monkeypatch, clean_db):
    """With seeded profile_cache and manifest_cache, GET /api/postmaster lists items."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-pm-read")

    await cache_repo.set(pool, uid, "profile_cache",
                         json.dumps(_PROFILE_WITH_POSTMASTER), settings.user_cache_ttl_seconds)

    # Monkeypatch load_cached_manifest to return a minimal fake manifest
    import app.main as main_module

    class FakeManifest:
        def name(self, h): return f"Item-{h}"
        def icon(self, h): return ""

    async def fake_load_cached_manifest(pool_arg):
        return FakeManifest()

    monkeypatch.setattr(main_module, "load_cached_manifest", fake_load_cached_manifest)

    r = await app_client.get("/api/postmaster")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert len(body["items"]) == 1
    assert body["items"][0]["itemHash"] == _ITEM_HASH
    assert body["items"][0]["characterId"] == _CHAR_ID
