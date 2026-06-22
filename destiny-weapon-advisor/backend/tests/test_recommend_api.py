"""Session-aware tests for GET /api/recommendations.

Legacy single-user tests removed — /api/recommendations now requires a session.
Functional coverage lives in test_endpoints_read.py.  This module retains only
the 401-without-session assertion so the file stays discoverable.
"""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_recommendations_401_without_session(app_client):
    from httpx import AsyncClient, ASGITransport
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/recommendations")
    assert r.status_code == 401


async def test_recommendations_default_context_ok(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec-def1")
    r = await app_client.get("/api/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}
    assert body["context"] == "General (PvE)"


async def test_recommendations_pvp_context_label(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec-pvp1")
    r = await app_client.get("/api/recommendations", params={"context": "general-pvp"})
    assert r.status_code == 200
    assert r.json()["context"] == "General (PvP)"


async def test_recommendations_unknown_context_falls_back(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec-unk1")
    r = await app_client.get("/api/recommendations", params={"context": "Nonexistent Activity"})
    assert r.status_code == 200
    body = r.json()
    assert body["context"] == "Nonexistent Activity"
    assert set(body["slots"]) == {"Primary", "Special", "Heavy"}


async def test_recommendations_slots_are_lists(app_client, monkeypatch, clean_db):
    await login_user(app_client, monkeypatch, bungie_id="bm-rec-lst1")
    r = await app_client.get("/api/recommendations")
    assert r.status_code == 200
    slots = r.json()["slots"]
    assert all(isinstance(slots[k], list) for k in ("Primary", "Special", "Heavy"))
