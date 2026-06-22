"""Session-aware tests for membership endpoints:
  GET /api/memberships, POST /api/memberships/select

All tests:
  - require a valid session (401 without one)
  - select updates per-user token row and clears that user's account cache keys
  - select does NOT clear another user's cache keys
"""
import pytest

from app.repositories import cache as cache_repo, tokens as tokens_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# 401 tests (no session)
# ---------------------------------------------------------------------------

async def test_get_memberships_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/memberships")
    assert r.status_code == 401


async def test_post_memberships_select_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/memberships/select", json={"membershipType": 3, "membershipId": "999"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/memberships/select — updates token row and clears cache keys
# ---------------------------------------------------------------------------

async def test_select_updates_membership_and_clears_cache(app_client, monkeypatch, clean_db):
    """Selecting a membership updates the user_tokens row and clears account cache keys."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-sel1")

    # Seed account cache keys for this user.
    await cache_repo.set(pool, uid, "weapons_cache", "w", settings.user_cache_ttl_seconds)
    await cache_repo.set(pool, uid, "profile_cache", "p", settings.user_cache_ttl_seconds)

    # Confirm the cache keys exist before the select.
    assert await cache_repo.get(pool, uid, "weapons_cache") == "w"
    assert await cache_repo.get(pool, uid, "profile_cache") == "p"

    # POST select with a new membership.
    r = await app_client.post(
        "/api/memberships/select",
        json={"membershipType": 1, "membershipId": "new-mid-1"},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # Token row must reflect the new membership.
    tok = await tokens_repo.get_tokens(pool, uid, settings.token_enc_key)
    assert tok is not None
    assert tok["membership_type"] == 1
    assert tok["membership_id"] == "new-mid-1"

    # Account cache keys must be cleared.
    assert await cache_repo.get(pool, uid, "weapons_cache") is None
    assert await cache_repo.get(pool, uid, "profile_cache") is None


# ---------------------------------------------------------------------------
# Isolation: user A's select does NOT clear user B's cache
# ---------------------------------------------------------------------------

async def test_select_does_not_clear_other_users_cache(app_client, monkeypatch, clean_db):
    """User A selecting a membership must not clear user B's cache keys."""
    pool = clean_db
    settings = __import__("app.config", fromlist=["get_settings"]).get_settings()

    # Log in user A; seed B's cache directly (B does not need to be logged in yet).
    uid_a = await login_user(app_client, monkeypatch, bungie_id="bm-iso-sel-a")
    uid_b = await login_user(app_client, monkeypatch, bungie_id="bm-iso-sel-b")

    # Seed weapons_cache for user B.
    await cache_repo.set(pool, uid_b, "weapons_cache", "b-weapons", settings.user_cache_ttl_seconds)

    # Switch back to user A (re-login replaces the sid cookie on app_client).
    uid_a = await login_user(app_client, monkeypatch, bungie_id="bm-iso-sel-a")

    # User A selects a membership.
    r = await app_client.post(
        "/api/memberships/select",
        json={"membershipType": 2, "membershipId": "a-new-mid"},
    )
    assert r.status_code == 200

    # User B's weapons_cache must still be present.
    assert await cache_repo.get(pool, uid_b, "weapons_cache") == "b-weapons"


# ---------------------------------------------------------------------------
# GET /api/memberships — returns memberships list and active membership
# ---------------------------------------------------------------------------

async def test_get_memberships_returns_expected_shape(app_client, monkeypatch, clean_db):
    """GET /api/memberships returns {memberships:[...], active:{...}} for a logged-in user."""
    import app.main as main_module

    uid = await login_user(app_client, monkeypatch, bungie_id="bm-getmem1")

    # Monkeypatch get_memberships to avoid live Bungie call.
    async def fake_get_memberships(access, settings, client):
        return {
            "primaryMembershipId": "bm-getmem1",
            "destinyMemberships": [
                {"membershipType": 3, "membershipId": "bm-getmem1", "displayName": "User-bm-getmem1"}
            ],
        }

    monkeypatch.setattr(main_module, "get_memberships", fake_get_memberships)

    r = await app_client.get("/api/memberships")
    assert r.status_code == 200
    body = r.json()

    # Shape checks.
    assert "memberships" in body
    assert "active" in body
    assert isinstance(body["memberships"], list)
    assert len(body["memberships"]) == 1
    m = body["memberships"][0]
    assert m["type"] == 3
    assert m["id"] == "bm-getmem1"
    assert m["displayName"] == "User-bm-getmem1"
    # active should contain type and id from the token row (set during login).
    assert body["active"] is not None
    assert "type" in body["active"]
    assert "id" in body["active"]
