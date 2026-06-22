import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_login_redirects_to_bungie(app_client):
    r = await app_client.get("/api/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "bungie.net" in r.headers["location"]


async def test_callback_creates_session_and_status_true(app_client, monkeypatch, clean_db):
    import app.auth as auth
    # seed a valid state by hitting /api/login
    loc = (await app_client.get("/api/login", follow_redirects=False)).headers["location"]
    state = loc.split("state=")[1].split("&")[0]

    async def fake_exchange(code, settings, client):
        return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

    async def fake_members(access, settings, client):
        return {
            "bungieNetUser": {"membershipId": "bnet-mid1"},
            "primaryMembershipId": "mid1",
            "destinyMemberships": [
                {"membershipType": 3, "membershipId": "mid1", "displayName": "G"}
            ],
        }

    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    monkeypatch.setattr(auth, "get_memberships", fake_members)
    r = await app_client.get(f"/callback?code=x&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "sid=" in r.headers.get("set-cookie", "")
    s = await app_client.get("/api/status")
    assert s.json()["authenticated"] is True


async def test_callback_sets_csrf_cookie(app_client, monkeypatch, clean_db):
    """Callback must set csrftoken cookie (httponly=False so JS can read it)."""
    import app.auth as auth
    loc = (await app_client.get("/api/login", follow_redirects=False)).headers["location"]
    state = loc.split("state=")[1].split("&")[0]

    async def fake_exchange(code, settings, client):
        return {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600}

    async def fake_members(access, settings, client):
        return {
            "bungieNetUser": {"membershipId": "bnet-mid-csrf1"},
            "primaryMembershipId": "mid-csrf1",
            "destinyMemberships": [
                {"membershipType": 3, "membershipId": "mid-csrf1", "displayName": "CsrfUser"}
            ],
        }

    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    monkeypatch.setattr(auth, "get_memberships", fake_members)
    await app_client.get(f"/callback?code=x&state={state}", follow_redirects=False)

    # csrftoken must be set in the cookie jar after login
    csrf = app_client.cookies.get("csrftoken")
    assert csrf is not None and len(csrf) > 0


async def test_protected_route_401_without_session(app_client):
    # Use a fresh client with no cookies by creating an independent request
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://t"
    ) as fresh_client:
        r = await fresh_client.get("/api/weapons")
        assert r.status_code == 401
