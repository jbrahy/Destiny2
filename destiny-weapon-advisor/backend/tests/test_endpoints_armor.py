"""GET /api/armor carries the backend verdict and set data."""
import json

import pytest

from app.manifest import load_cached_manifest
from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ITEMS = {
    "500": {"displayProperties": {"name": "Techsec Helm", "icon": "/t.jpg"},
            "itemType": 2, "itemTypeDisplayName": "Helmet",
            "inventory": {"tierType": 5}, "classType": 2},
}
_SETS = {"900": {"displayProperties": {"name": "Techsec"}, "setItems": [500],
                 "setPerks": [{"requiredSetCount": 2, "sandboxPerkHash": 7001}]}}
_PERKS = {"7001": {"displayProperties": {"name": "Wrecker", "description": "Bonus Kinetic damage."}}}
_STATS = {"1": {"displayProperties": {"name": "Melee"}},
          "2": {"displayProperties": {"name": "Weapons"}}}
_PROFILE = {
    "characters": {"data": {}}, "characterEquipment": {"data": {}},
    "characterInventories": {"data": {}},
    "profileInventory": {"data": {"items": [
        {"itemInstanceId": "a1", "itemHash": 500, "state": 0}]}},
    "itemComponents": {"stats": {"data": {"a1": {"stats": {
        "1": {"value": 30}, "2": {"value": 35}}}}}},
}


async def _seed(pool, uid):
    await cache_repo.manifest_set(pool, "manifest_items", json.dumps(_ITEMS), "v1")
    await cache_repo.manifest_set(pool, "manifest_stats", json.dumps(_STATS), "v1")
    await cache_repo.manifest_set(pool, "manifest_item_sets", json.dumps(_SETS), "v1")
    await cache_repo.manifest_set(pool, "manifest_sandbox_perks", json.dumps(_PERKS), "v1")
    await cache_repo.set(pool, uid, "profile_cache", json.dumps(_PROFILE), 3600)


async def _fake_load_manifest(client, pool, throttle):
    """Stand-in for app.main.load_manifest: reads the seeded cache instead of
    hitting Bungie's live manifest endpoint (which /api/weapons alone uses)."""
    return await load_cached_manifest(pool)


async def _fake_get_profile(mtype, mid, access, settings, client):
    """Stand-in for app.main.get_profile: must never hit Bungie."""
    return _PROFILE


async def test_armor_requires_authentication(app_client):
    assert (await app_client.get("/api/armor")).status_code == 401


async def test_armor_items_carry_verdict_focus_and_set(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
    await _seed(clean_db, uid)
    monkeypatch.setattr("app.main.load_manifest", _fake_load_manifest)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)
    # /api/armor reads armor_cache, which _compute_weapons fills.
    await app_client.get("/api/weapons")

    resp = await app_client.get("/api/armor")
    assert resp.status_code == 200
    piece = resp.json()["armor"][0]
    assert piece["setName"] == "Techsec"
    assert piece["setHash"] == 900
    assert piece["setBonuses"] == [
        {"count": 2, "name": "Wrecker", "description": "Bonus Kinetic damage."}]
    assert piece["focus"] == 65          # 30 + 35
    assert piece["waste"] == 0
    assert piece["verdict"] in {"top_roll", "good", "ok", "dismantle"}
