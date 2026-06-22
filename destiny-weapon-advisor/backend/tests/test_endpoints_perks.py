"""Session-aware tests for perks endpoints:
  GET /api/perks, PUT /api/perks

All tests:
  - require a valid session (401 without one)
  - operate on per-user data (user A ratings are invisible to user B)
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

# A minimal weapons_cache entry containing one weapon with perkNames and weaponType.
def _make_weapons_cache(weapon_type: str = "Auto Rifle", perk_names: list = None) -> dict:
    if perk_names is None:
        perk_names = ["Rangefinder", "Kill Clip"]
    return {
        "weapons": [
            {
                "instanceId": "w1",
                "itemHash": 111,
                "name": "Hard Light",
                "weaponType": weapon_type,
                "element": "Solar",
                "location": "Vault",
                "isMasterworked": False,
                "verdict": "keep",
                "matchedPerks": [],
                "note": "",
                "verdictReason": "",
                "upgradePath": None,
                "tags": [],
                "isDuplicate": False,
                "power": 1800,
                "ammoType": "Primary",
                "frame": "Adaptive",
                "perkNames": perk_names,
                "stats": {},
                "ratedPerks": [],
                "icon": "",
                "equipped": False,
            }
        ],
        "cachedAt": 1700000000.0,
    }


# ---------------------------------------------------------------------------
# 401 tests (no session)
# ---------------------------------------------------------------------------

async def test_get_perks_401_without_session(app_client):
    """GET /api/perks should return 401 when there is no active session."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/perks")
    assert r.status_code == 401


async def test_put_perks_401_without_session(app_client):
    """PUT /api/perks should return 401 when there is no active session."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.put(
            "/api/perks",
            json={"name": "Kill Clip", "weaponType": "Auto Rifle", "rating": "s_tier"},
        )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/perks — returns weapon types with perks from weapons_cache
# ---------------------------------------------------------------------------

async def test_get_perks_returns_weapon_types_from_cache(app_client, monkeypatch, clean_db):
    """GET /api/perks should return weaponTypes derived from the user's weapons_cache."""
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-perks-get1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    # Seed weapons_cache for this user.
    weapons_payload = _make_weapons_cache(weapon_type="Auto Rifle", perk_names=["Rangefinder", "Kill Clip"])
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps(weapons_payload), settings.user_cache_ttl_seconds)

    r = await app_client.get("/api/perks")
    assert r.status_code == 200
    body = r.json()
    assert "weaponTypes" in body

    # "Auto Rifle" should appear in the response.
    types = {wt["weaponType"] for wt in body["weaponTypes"]}
    assert "Auto Rifle" in types

    # The two seeded perk names should appear under "Auto Rifle".
    auto_rifle = next(wt for wt in body["weaponTypes"] if wt["weaponType"] == "Auto Rifle")
    perk_names_in_response = {p["name"] for p in auto_rifle["perks"]}
    assert "Rangefinder" in perk_names_in_response
    assert "Kill Clip" in perk_names_in_response


async def test_get_perks_empty_when_no_cache(app_client, monkeypatch, clean_db):
    """GET /api/perks returns empty weaponTypes when weapons_cache is absent."""
    await login_user(app_client, monkeypatch, bungie_id="bm-perks-empty1")
    r = await app_client.get("/api/perks")
    assert r.status_code == 200
    assert r.json()["weaponTypes"] == []


# ---------------------------------------------------------------------------
# PUT /api/perks — saves rating; GET reflects it
# ---------------------------------------------------------------------------

async def test_put_perks_saves_and_get_reflects_rating(app_client, monkeypatch, clean_db):
    """PUT /api/perks persists a user rating; a follow-up GET shows that rating."""
    pool = clean_db
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-perks-put1")
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    # Seed weapons_cache so GET /api/perks has something to build from.
    weapons_payload = _make_weapons_cache(weapon_type="Auto Rifle", perk_names=["Kill Clip"])
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps(weapons_payload), settings.user_cache_ttl_seconds)

    # Save a rating via PUT (use single-char tier format: S/A/B/C/D).
    put_r = await app_client.put(
        "/api/perks",
        json={
            "name": "Kill Clip",
            "weaponType": "Auto Rifle",
            "rating": "S",
            "reason": "Huge damage bonus on reload kill",
            "tags": ["damage"],
            "notes": "Best in slot",
        },
    )
    assert put_r.status_code == 200
    assert put_r.json()["ok"] is True

    # GET should reflect the saved rating.
    get_r = await app_client.get("/api/perks")
    assert get_r.status_code == 200
    body = get_r.json()
    auto_rifle = next(wt for wt in body["weaponTypes"] if wt["weaponType"] == "Auto Rifle")
    kill_clip = next(p for p in auto_rifle["perks"] if p["name"] == "Kill Clip")
    assert kill_clip["rating"] == "S"
    assert kill_clip["isOverride"] is True


# ---------------------------------------------------------------------------
# Isolation: user B cannot see user A's perk ratings
# ---------------------------------------------------------------------------

async def test_perk_ratings_isolation_between_users(app_client, monkeypatch, clean_db):
    """User A's saved perk rating must NOT be visible to user B."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    # Log in as user A, seed cache, and save a rating.
    uid_a = await login_user(app_client, monkeypatch, bungie_id="bm-perks-iso-a")
    weapons_payload = _make_weapons_cache(weapon_type="Auto Rifle", perk_names=["Kill Clip"])
    await cache_repo.set(pool, uid_a, "weapons_cache", json.dumps(weapons_payload), settings.user_cache_ttl_seconds)

    put_r = await app_client.put(
        "/api/perks",
        json={
            "name": "Kill Clip",
            "weaponType": "Auto Rifle",
            "rating": "S",
            "reason": "Great",
            "tags": [],
            "notes": "",
        },
    )
    assert put_r.status_code == 200

    # User A should see the override.
    get_a = await app_client.get("/api/perks")
    assert get_a.status_code == 200
    body_a = get_a.json()
    auto_rifle_a = next(wt for wt in body_a["weaponTypes"] if wt["weaponType"] == "Auto Rifle")
    kill_clip_a = next(p for p in auto_rifle_a["perks"] if p["name"] == "Kill Clip")
    assert kill_clip_a["isOverride"] is True

    # Log in as user B — this replaces the session cookie on app_client.
    uid_b = await login_user(app_client, monkeypatch, bungie_id="bm-perks-iso-b")

    # Seed weapons_cache for B with the same perk names.
    await cache_repo.set(pool, uid_b, "weapons_cache", json.dumps(weapons_payload), settings.user_cache_ttl_seconds)

    # B should NOT see user A's override — isOverride must be False.
    get_b = await app_client.get("/api/perks")
    assert get_b.status_code == 200
    body_b = get_b.json()
    auto_rifle_b = next(wt for wt in body_b["weaponTypes"] if wt["weaponType"] == "Auto Rifle")
    kill_clip_b = next(p for p in auto_rifle_b["perks"] if p["name"] == "Kill Clip")
    assert kill_clip_b["isOverride"] is False
