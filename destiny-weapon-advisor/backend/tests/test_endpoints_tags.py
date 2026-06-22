"""Session-aware tests for per-user item tags: GET/PUT /api/tags.

All tests:
  - require a valid session (401 without one)
  - operate on per-user data (user A's tags are invisible to user B)
"""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_tags_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/tags")
    assert r.status_code == 401


async def test_tags_set_and_clear(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-tag1")

    # Set a tag.
    r = await app_client.put("/api/tags", json={"instanceId": "123", "tag": "keep"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await app_client.get("/api/tags")
    assert r.status_code == 200
    assert r.json()["tags"]["123"] == "keep"

    # Clear it with an empty tag.
    r = await app_client.put("/api/tags", json={"instanceId": "123", "tag": ""})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = await app_client.get("/api/tags")
    assert r.status_code == 200
    assert "123" not in r.json()["tags"]


async def test_tags_isolation_user_b_does_not_see_user_a(app_client, monkeypatch, clean_db):
    # User A tags an item.
    await login_user(app_client, monkeypatch, bungie_id="bm-tag-iso-a")
    r = await app_client.put("/api/tags", json={"instanceId": "123", "tag": "junk"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    # Confirm A sees it.
    r_a = await app_client.get("/api/tags")
    assert r_a.status_code == 200
    assert r_a.json()["tags"]["123"] == "junk"

    # Log in as user B (replaces the sid cookie on app_client).
    await login_user(app_client, monkeypatch, bungie_id="bm-tag-iso-b")
    r_b = await app_client.get("/api/tags")
    assert r_b.status_code == 200
    assert "123" not in r_b.json()["tags"]
