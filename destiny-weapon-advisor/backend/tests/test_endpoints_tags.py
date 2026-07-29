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


# ---------------------------------------------------------------------------
# Bulk tagging: POST /api/tags/bulk
#
# Unlike PUT /api/tags (which predates CSRF enforcement here), the bulk endpoint
# is CSRF-protected, so these tests send the double-submit header.
# ---------------------------------------------------------------------------


def _csrf(client) -> dict:
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


async def test_bulk_tags_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/tags/bulk", json={"instanceIds": ["1"], "tag": "junk"})
    assert r.status_code == 401


async def test_bulk_tags_sets_many_at_once(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk1")

    r = await app_client.post(
        "/api/tags/bulk",
        json={"instanceIds": ["a", "b", "c"], "tag": "junk"},
        headers=_csrf(app_client),
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 3}

    tags = (await app_client.get("/api/tags")).json()["tags"]
    assert tags == {"a": "junk", "b": "junk", "c": "junk"}


async def test_bulk_tags_overwrites_existing_tag(app_client, monkeypatch, clean_db):
    """A weapon already tagged 'keep' must end up 'junk', not duplicated."""
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk2")
    await app_client.put("/api/tags", json={"instanceId": "a", "tag": "keep"})

    r = await app_client.post(
        "/api/tags/bulk", json={"instanceIds": ["a"], "tag": "junk"},
        headers=_csrf(app_client),
    )
    assert r.status_code == 200

    tags = (await app_client.get("/api/tags")).json()["tags"]
    assert tags["a"] == "junk"


async def test_bulk_tags_empty_tag_clears_them(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk3")
    await app_client.post(
        "/api/tags/bulk", json={"instanceIds": ["a", "b"], "tag": "junk"},
        headers=_csrf(app_client),
    )

    r = await app_client.post(
        "/api/tags/bulk", json={"instanceIds": ["a", "b"], "tag": ""},
        headers=_csrf(app_client),
    )
    assert r.status_code == 200

    tags = (await app_client.get("/api/tags")).json()["tags"]
    assert "a" not in tags and "b" not in tags


async def test_bulk_tags_empty_list_is_a_no_op(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk4")
    r = await app_client.post(
        "/api/tags/bulk", json={"instanceIds": [], "tag": "junk"},
        headers=_csrf(app_client),
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "count": 0}


async def test_bulk_tags_rejects_an_unknown_tag(app_client, monkeypatch, clean_db):
    """Only the four known tags (or '') are accepted — a typo must not persist."""
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk5")
    r = await app_client.post(
        "/api/tags/bulk", json={"instanceIds": ["a"], "tag": "jnuk"},
        headers=_csrf(app_client),
    )
    assert r.status_code == 422
    assert (await app_client.get("/api/tags")).json()["tags"] == {}


async def test_bulk_tags_rejects_an_oversized_batch(app_client, monkeypatch, clean_db):
    """Bounded so a single request cannot write unbounded rows."""
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk6")
    r = await app_client.post(
        "/api/tags/bulk",
        json={"instanceIds": [str(i) for i in range(1001)], "tag": "junk"},
        headers=_csrf(app_client),
    )
    assert r.status_code == 422


async def test_bulk_tags_are_user_isolated(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-bulk-a")
    await app_client.post(
        "/api/tags/bulk", json={"instanceIds": ["a"], "tag": "junk"},
        headers=_csrf(app_client),
    )

    await login_user(app_client, monkeypatch, bungie_id="bm-bulk-b")
    assert (await app_client.get("/api/tags")).json()["tags"] == {}
