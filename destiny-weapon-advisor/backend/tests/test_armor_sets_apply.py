"""Session-aware tests for POST /api/armor-sets/apply.

- apply unknown set → 404
- apply known set → mocks Bungie calls; asserts per-user profile refreshed
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAR_ID = "char-apply-123"
_INSTANCE_ID = "armor-inst-1"
_ITEM_HASH = 5551234

_ARMOR_SET = {
    "name": "apply-test-set",
    "className": "Warlock",
    "characterId": _CHAR_ID,
    "tier": 15,
    "items": [
        {"instanceId": _INSTANCE_ID, "itemHash": _ITEM_HASH, "slot": "Helmet", "name": "Test Helm"},
    ],
}

_PROFILE_WITH_ITEM = {
    "characters": {
        "data": {
            _CHAR_ID: {
                "classType": 2,
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

async def test_armor_sets_apply_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/armor-sets/apply", json={"name": "does-not-exist-xyz"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 403 without CSRF
# ---------------------------------------------------------------------------

async def test_armor_sets_apply_403_without_csrf(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-asa-nocsrf")
    r = await app_client.post("/api/armor-sets/apply", json={"name": "does-not-exist-xyz"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 404 for unknown set (with valid session + CSRF)
# ---------------------------------------------------------------------------

async def test_apply_unknown_set_returns_404(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-asa-404")
    csrf = _csrf(app_client)
    r = await app_client.post("/api/armor-sets/apply", json={"name": "does-not-exist-xyz"},
                               headers=csrf)
    assert r.status_code == 404
    assert r.json()["detail"] == "Armor set not found."


# ---------------------------------------------------------------------------
# Happy path: apply known set — mocked Bungie; per-user profile refreshed
# ---------------------------------------------------------------------------

async def test_apply_armor_set_happy_path(app_client, monkeypatch, clean_db):
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-asa-happy")
    csrf = _csrf(app_client)

    # Save the armor set first (with CSRF).
    r = await app_client.put("/api/armor-sets", json=_ARMOR_SET, headers=csrf)
    assert r.status_code == 200

    # Seed the profile cache so _load_profile_or_400 passes.
    await cache_repo.set(pool, uid, "profile_cache",
                         json.dumps(_PROFILE_WITH_ITEM), settings.user_cache_ttl_seconds)
    await cache_repo.set(pool, uid, "profile_membership_id",
                         "bm-asa-happy", settings.user_cache_ttl_seconds)

    # Monkeypatch Bungie functions — no real network calls.
    import app.main as main_module

    async def fake_valid_access_token(pool_arg, uid_arg, settings_arg, client, key):
        return ("acc-token", 3, "bm-asa-happy")

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
    monkeypatch.setattr(bs_module, "valid_access_token", fake_valid_access_token)

    r = await app_client.post("/api/armor-sets/apply", json={"name": "apply-test-set"},
                               headers=csrf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "results" in body

    # Verify per-user profile_cache was refreshed with the sentinel
    cached_raw = await cache_repo.get(pool, uid, "profile_cache")
    assert cached_raw is not None
    cached = json.loads(cached_raw)
    assert cached.get("_refreshed") is True
