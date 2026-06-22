"""Session-aware tests for read endpoints:
  GET /api/weapons, /api/recommendations, /api/loadout-suggestion,
  /api/counts, /api/characters, /api/armor.

All tests:
  - require a valid session (401 without one)
  - operate on per-user data (user A data is invisible to user B)
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WEAPONS_PAYLOAD = {
    "weapons": [
        {
            "instanceId": "w1",
            "itemHash": 111,
            "name": "The Lament",
            "weaponType": "Sword",
            "element": "Solar",
            "location": "Vault",
            "isMasterworked": True,
            "verdict": "god_roll",
            "matchedPerks": [],
            "note": "",
            "verdictReason": "",
            "upgradePath": None,
            "tags": [],
            "isDuplicate": False,
            "power": 1800,
            "ammoType": "Heavy",
            "frame": "Adaptive",
            "perkNames": [],
            "stats": {},
            "ratedPerks": [],
            "icon": "",
            "equipped": False,
        }
    ],
    "cachedAt": 1700000000.0,
}

_ARMOR_PAYLOAD = [
    {
        "instanceId": "a1",
        "itemHash": 222,
        "name": "Helm of the Taken King",
        "slot": "Helmet",
        "className": "Titan",
        "power": 1800,
        "isExotic": False,
        "isMasterworked": False,
        "stats": {"Resilience": 80},
        "location": "Vault",
        "icon": "",
        "equipped": False,
    }
]

_PROFILE_PAYLOAD = {
    "characters": {
        "data": {
            "char1": {
                "classType": 0,
                "light": 1800,
                "dateLastPlayed": "2024-01-01T00:00:00Z",
            }
        }
    }
}


# ---------------------------------------------------------------------------
# 401 tests (no session)
# ---------------------------------------------------------------------------

async def test_weapons_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/weapons")
    assert r.status_code == 401


async def test_recommendations_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/recommendations")
    assert r.status_code == 401


async def test_counts_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/counts")
    assert r.status_code == 401


async def test_characters_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/characters")
    assert r.status_code == 401


async def test_armor_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/armor")
    assert r.status_code == 401


async def test_loadout_suggestion_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/loadout-suggestion", params={"activity": "x"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/weapons — seeded cache returned
# ---------------------------------------------------------------------------

async def test_weapons_returns_cached_data(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-wep1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    await cache_repo.set(
        pool, uid, "weapons_cache",
        json.dumps(_WEAPONS_PAYLOAD),
        settings.user_cache_ttl_seconds,
    )
    r = await app_client.get("/api/weapons")
    assert r.status_code == 200
    body = r.json()
    assert len(body["weapons"]) == 1
    assert body["weapons"][0]["name"] == "The Lament"


# ---------------------------------------------------------------------------
# GET /api/counts — derived from cached weapons+armor
# ---------------------------------------------------------------------------

async def test_counts_with_seeded_cache(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-cnt1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    ttl = settings.user_cache_ttl_seconds
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps(_WEAPONS_PAYLOAD), ttl)
    await cache_repo.set(pool, uid, "armor_cache", json.dumps(_ARMOR_PAYLOAD), ttl)
    r = await app_client.get("/api/counts")
    assert r.status_code == 200
    body = r.json()
    assert body["weapons"] == 1
    assert body["armor"] == 1
    assert body["vaultWeapons"] == 1   # location == "Vault"
    assert body["vaultArmor"] == 1     # location == "Vault"


async def test_counts_returns_zeros_when_no_cache(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-cnt2")
    r = await app_client.get("/api/counts")
    assert r.status_code == 200
    body = r.json()
    assert body == {"weapons": 0, "armor": 0, "vaultWeapons": 0, "vaultArmor": 0}


# ---------------------------------------------------------------------------
# GET /api/armor — returns cached armor list
# ---------------------------------------------------------------------------

async def test_armor_returns_cached_data(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-arm1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    await cache_repo.set(pool, uid, "armor_cache", json.dumps(_ARMOR_PAYLOAD), settings.user_cache_ttl_seconds)
    r = await app_client.get("/api/armor")
    assert r.status_code == 200
    body = r.json()
    assert len(body["armor"]) == 1
    assert body["armor"][0]["name"] == "Helm of the Taken King"
    assert "Resilience" in body["statNames"]


# ---------------------------------------------------------------------------
# GET /api/characters — returns parsed profile characters
# ---------------------------------------------------------------------------

async def test_characters_returns_empty_when_no_profile(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-char1")
    r = await app_client.get("/api/characters")
    assert r.status_code == 200
    assert r.json() == {"characters": []}


async def test_characters_returns_data_from_profile_cache(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-char2")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    await cache_repo.set(pool, uid, "profile_cache", json.dumps(_PROFILE_PAYLOAD), settings.user_cache_ttl_seconds)
    r = await app_client.get("/api/characters")
    assert r.status_code == 200
    body = r.json()
    assert len(body["characters"]) == 1
    assert body["characters"][0]["light"] == 1800


# ---------------------------------------------------------------------------
# GET /api/recommendations — returns per-user weapons
# ---------------------------------------------------------------------------

async def test_recommendations_returns_slot_structure(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-rec1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps(_WEAPONS_PAYLOAD), settings.user_cache_ttl_seconds)
    r = await app_client.get("/api/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
    assert body["context"] == "General (PvE)"


async def test_recommendations_pvp_label(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec2")
    r = await app_client.get("/api/recommendations", params={"context": "general-pvp"})
    assert r.status_code == 200
    assert r.json()["context"] == "General (PvP)"


async def test_recommendations_unknown_context_falls_back(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec3")
    r = await app_client.get("/api/recommendations", params={"context": "Nonexistent Activity"})
    assert r.status_code == 200
    body = r.json()
    assert body["context"] == "Nonexistent Activity"


# ---------------------------------------------------------------------------
# GET /api/loadout-suggestion — 404 for unknown activity
# ---------------------------------------------------------------------------

async def test_loadout_suggestion_unknown_activity_404(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ls1")
    r = await app_client.get("/api/loadout-suggestion", params={"activity": "Nope"})
    assert r.status_code == 404


async def test_loadout_suggestion_known_activity_shape(app_client, monkeypatch, clean_db):
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-ls2")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps(_WEAPONS_PAYLOAD), settings.user_cache_ttl_seconds)
    r = await app_client.get("/api/loadout-suggestion", params={"activity": "Crota's End (Raid)"})
    assert r.status_code == 200
    body = r.json()
    assert body["activity"] == "Crota's End (Raid)"
    assert set(body["weapons"]) == {"Primary", "Special", "Heavy"}
    assert "subclass" in body


# ---------------------------------------------------------------------------
# Isolation: user B cannot see user A's weapons
# ---------------------------------------------------------------------------

async def test_weapons_isolation_user_b_sees_empty(app_client, monkeypatch, clean_db):
    """User A's cached weapons must not be visible to user B."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    _B_WEAPONS = {"weapons": [], "cachedAt": 0.0}

    # Log in as user A and seed weapons cache.
    uid_a = await login_user(app_client, monkeypatch, bungie_id="bm-iso-a")
    await cache_repo.set(pool, uid_a, "weapons_cache", json.dumps(_WEAPONS_PAYLOAD), settings.user_cache_ttl_seconds)

    # Confirm A sees the data.
    r_a = await app_client.get("/api/weapons")
    assert r_a.status_code == 200
    assert len(r_a.json()["weapons"]) == 1
    assert r_a.json()["weapons"][0]["name"] == "The Lament"

    # Now log in as user B (replaces the sid cookie on app_client).
    uid_b = await login_user(app_client, monkeypatch, bungie_id="bm-iso-b")

    # Seed an explicit empty weapons cache for B so the route returns from cache
    # without making a live Bungie call (which would fail in tests).
    await cache_repo.set(pool, uid_b, "weapons_cache", json.dumps(_B_WEAPONS), settings.user_cache_ttl_seconds)

    r_b = await app_client.get("/api/weapons")
    assert r_b.status_code == 200
    # B must see only their own (empty) list, not A's weapon.
    assert r_b.json()["weapons"] == []
