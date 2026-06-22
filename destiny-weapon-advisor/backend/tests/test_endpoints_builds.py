"""Session-aware tests for builds/activities endpoints:
  GET /api/builds, PUT /api/builds,
  GET /api/activities, PUT /api/activities,
  GET /api/activities/catalog.

All tests:
  - require a valid session (401 without one) for builds and activities
  - builds/activities are per-user; catalog is globally cached (account-independent)
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# 401 tests (no session)
# ---------------------------------------------------------------------------

async def test_builds_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/builds")
    assert r.status_code == 401


async def test_activities_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/activities")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Per-user builds: PUT then GET reflects for A; B sees only seed defaults
# ---------------------------------------------------------------------------

async def test_builds_put_and_get_for_user_a(app_client, monkeypatch, clean_db):
    """PUT a build override for user A; GET returns it."""
    await login_user(app_client, monkeypatch, bungie_id="bm-bld-a")
    build_data = {"weapons": ["Hand Cannon", "Rocket Launcher"], "notes": "A's build"}
    r_put = await app_client.put("/api/builds", json={"key": "Titan|Solar", "data": build_data})
    assert r_put.status_code == 200
    assert r_put.json() == {"ok": True}

    r_get = await app_client.get("/api/builds")
    assert r_get.status_code == 200
    body = r_get.json()
    assert "builds" in body
    assert body["builds"]["Titan|Solar"] == build_data


async def test_builds_user_b_does_not_see_user_a_override(app_client, monkeypatch, clean_db):
    """User B sees only seed defaults, not A's overridden build."""
    # Log in as A and save a build override.
    await login_user(app_client, monkeypatch, bungie_id="bm-bld-iso-a")
    custom_data = {"weapons": ["Gjallarhorn"], "notes": "A only"}
    await app_client.put("/api/builds", json={"key": "Hunter|Arc", "data": custom_data})

    # Confirm A sees it.
    r_a = await app_client.get("/api/builds")
    assert r_a.status_code == 200
    assert r_a.json()["builds"].get("Hunter|Arc") == custom_data

    # Log in as B (replaces session cookie).
    await login_user(app_client, monkeypatch, bungie_id="bm-bld-iso-b")
    r_b = await app_client.get("/api/builds")
    assert r_b.status_code == 200
    # B should NOT see A's custom data for that key (either absent or a seed default).
    b_builds = r_b.json()["builds"]
    assert b_builds.get("Hunter|Arc") != custom_data


# ---------------------------------------------------------------------------
# Per-user activities: PUT then GET reflects for A; B doesn't see it
# ---------------------------------------------------------------------------

async def test_activities_put_and_get_for_user_a(app_client, monkeypatch, clean_db):
    """PUT an activity override for user A; GET returns it."""
    await login_user(app_client, monkeypatch, bungie_id="bm-act-a")
    activity_data = {
        "name": "My Custom Raid",
        "recommendedSubclass": "Solar",
        "recommendedClass": "Titan",
    }
    r_put = await app_client.put(
        "/api/activities",
        json={"name": "My Custom Raid", "data": activity_data},
    )
    assert r_put.status_code == 200
    assert r_put.json() == {"ok": True}

    r_get = await app_client.get("/api/activities")
    assert r_get.status_code == 200
    body = r_get.json()
    assert "activities" in body
    names = [a["name"] for a in body["activities"]]
    assert "My Custom Raid" in names


async def test_activities_user_b_does_not_see_user_a_custom(app_client, monkeypatch, clean_db):
    """User B does not see A's user-only custom activity."""
    # Log in as A and add a custom activity.
    await login_user(app_client, monkeypatch, bungie_id="bm-act-iso-a")
    await app_client.put(
        "/api/activities",
        json={"name": "A-Only Dungeon", "data": {"name": "A-Only Dungeon", "recommendedSubclass": "Void"}},
    )

    # Confirm A sees it.
    r_a = await app_client.get("/api/activities")
    assert r_a.status_code == 200
    names_a = [ac["name"] for ac in r_a.json()["activities"]]
    assert "A-Only Dungeon" in names_a

    # Log in as B.
    await login_user(app_client, monkeypatch, bungie_id="bm-act-iso-b")
    r_b = await app_client.get("/api/activities")
    assert r_b.status_code == 200
    names_b = [ac["name"] for ac in r_b.json()["activities"]]
    assert "A-Only Dungeon" not in names_b


# ---------------------------------------------------------------------------
# activities/catalog: cached-path (no Bungie call)
# ---------------------------------------------------------------------------

async def test_activities_catalog_returns_seeded_cache(app_client, monkeypatch, clean_db):
    """Pre-seed manifest_cache with catalog; GET should return it without any Bungie call."""
    pool = clean_db
    catalog_data = [{"name": "Test Raid", "type": "Raid"}]
    await cache_repo.manifest_set(pool, "activity_catalog", json.dumps(catalog_data), "v1")

    # Log in (endpoint is behind auth).
    await login_user(app_client, monkeypatch, bungie_id="bm-cat-1")

    r = await app_client.get("/api/activities/catalog")
    assert r.status_code == 200
    body = r.json()
    assert "catalog" in body
    assert body["catalog"] == catalog_data
