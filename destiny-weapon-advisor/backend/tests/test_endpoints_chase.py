"""GET /api/chase — weapons whose roll pool beats what's in the vault."""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ITEMS = {
    "100": {"displayProperties": {"name": "Fatebringer", "icon": "/fb.jpg"},
            "itemType": 3, "itemTypeDisplayName": "Hand Cannon",
            "inventory": {"tierType": 5},
            "sockets": {"socketEntries": [
                {"randomizedPlugSetHash": 5002}, {"randomizedPlugSetHash": 5003}]}},
    "10": {"displayProperties": {"name": "Explosive Payload"}, "itemTypeDisplayName": "Trait"},
    "11": {"displayProperties": {"name": "Frenzy"}, "itemTypeDisplayName": "Trait"},
    "13": {"displayProperties": {"name": "Meh Perk"}, "itemTypeDisplayName": "Trait"},
}
_PLUGSETS = {
    "5002": {"reusablePlugItems": [{"plugItemHash": 10, "currentlyCanRoll": True},
                                   {"plugItemHash": 13, "currentlyCanRoll": True}]},
    "5003": {"reusablePlugItems": [{"plugItemHash": 11, "currentlyCanRoll": True}]},
}
_PROFILE = {
    "characters": {"data": {}},
    "characterEquipment": {"data": {}},
    "characterInventories": {"data": {}},
    "profileInventory": {"data": {"items": [
        {"itemInstanceId": "inst-1", "itemHash": 100, "state": 0},
    ]}},
    "itemComponents": {"sockets": {"data": {"inst-1": {"sockets": [{"plugHash": 13}]}}}},
}


async def _seed(pool, uid):
    await cache_repo.manifest_set(pool, "manifest_items", json.dumps(_ITEMS), "v1")
    await cache_repo.manifest_set(pool, "manifest_stats", json.dumps({}), "v1")
    await cache_repo.manifest_set(pool, "manifest_plugsets", json.dumps(_PLUGSETS), "v1")
    await cache_repo.set(pool, uid, "profile_cache", json.dumps(_PROFILE), 3600)


async def test_chase_requires_authentication(app_client):
    assert (await app_client.get("/api/chase")).status_code == 401


async def test_chase_lists_a_weapon_whose_pool_beats_the_vault(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
    await _seed(clean_db, uid)

    resp = await app_client.get("/api/chase")
    assert resp.status_code == 200
    rows = resp.json()["chase"]
    assert len(rows) == 1
    assert rows[0]["name"] == "Fatebringer"
    assert rows[0]["chasePerks"] == ["Explosive Payload", "Frenzy"]
    assert rows[0]["haveCount"] == 1


async def test_chase_needs_a_cached_profile(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.get("/api/chase")
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]
