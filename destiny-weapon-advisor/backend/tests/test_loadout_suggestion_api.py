"""Session-aware tests for GET /api/loadout-suggestion.

Legacy single-user tests removed — the endpoint now requires a session.
"""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_loadout_suggestion_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/loadout-suggestion", params={"activity": "x"})
    assert r.status_code == 401


async def test_unknown_activity_returns_404(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ls-404")
    r = await app_client.get("/api/loadout-suggestion", params={"activity": "Nope"})
    assert r.status_code == 404


async def test_known_activity_returns_suggestion_shape(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-ls-ok1")
    # Seeded activities are always present via builds_repo.load_activities.
    r = await app_client.get("/api/loadout-suggestion", params={"activity": "Crota's End (Raid)"})
    assert r.status_code == 200
    body = r.json()
    assert body["activity"] == "Crota's End (Raid)"
    assert set(body["weapons"]) == {"Primary", "Special", "Heavy"}
    assert "subclass" in body and "elementCoverage" in body
