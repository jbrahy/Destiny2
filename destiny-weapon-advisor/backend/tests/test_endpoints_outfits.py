"""GET /api/outfits — one outfit per seeded class/subclass, read-only."""
import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_outfits_requires_authentication(app_client):
    assert (await app_client.get("/api/outfits")).status_code == 401


async def test_outfits_needs_a_cached_inventory(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.get("/api/outfits")
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]
