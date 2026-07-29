"""Endpoint wiring for the dismantle sweep. Bungie writes are faked; no test
touches a live inventory."""
import json

import pytest

from app.repositories import cache as cache_repo, user_tables
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAR_ID = "char-1"
_KINETIC = 1498876634


def _profile_with(instance_id: str, item_hash: int, locked: bool = False) -> dict:
    return {
        "characters": {"data": {_CHAR_ID: {
            "classType": 0, "light": 1800, "dateLastPlayed": "2024-01-01T00:00:00Z",
        }}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {_CHAR_ID: {"items": []}}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": instance_id, "itemHash": item_hash,
             "state": 1 if locked else 0, "bucketHash": 138197802},
        ]}},
        "itemComponents": {},
    }


async def _seed_manifest(pool) -> None:
    """Minimal manifest with item hash 777 as a weapon whose home bucket is
    Kinetic, so the batch planner sees a real bucket."""
    items_data = {
        "777": {
            "displayProperties": {"name": "Test Weapon", "description": "", "icon": ""},
            "itemType": 3,
            "inventory": {"bucketTypeHash": _KINETIC, "tierType": 3},
        }
    }
    await cache_repo.manifest_set(pool, "manifest_items", json.dumps(items_data), "v1")
    await cache_repo.manifest_set(pool, "manifest_stats", json.dumps({}), "v1")


async def test_preview_returns_junk_tagged_weapon_as_a_candidate(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200
    body = resp.json()
    ids = [c["instanceId"] for c in body["candidates"]]
    assert "inst-1" in ids
    # An empty character bucket means the one candidate fits this batch.
    assert body["plan"]["staged"] == ["inst-1"]
    # bucketHash must be a stringified key so the UI can index plan.perBucket directly.
    candidate = next(c for c in body["candidates"] if c["instanceId"] == "inst-1")
    assert candidate["bucketHash"] == str(_KINETIC)


async def test_preview_requires_a_cached_profile(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]


async def test_preview_requires_authentication(app_client):
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 401
