"""Endpoint wiring for the dismantle sweep. Bungie writes are faked; no test
touches a live inventory."""
import json

import pytest

from app.repositories import cache as cache_repo, user_tables
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAR_ID = "char-1"
_KINETIC = 1498876634
_EXOTIC_HASH = 778


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


def _profile_multi(vault_items: list[dict], equipped_items: list[dict] | None = None) -> dict:
    """Like _profile_with but for multiple unequipped (vault) items plus
    optional equipped items, needed to exercise the blocklist paths."""
    return {
        "characters": {"data": {_CHAR_ID: {
            "classType": 0, "light": 1800, "dateLastPlayed": "2024-01-01T00:00:00Z",
        }}},
        "characterEquipment": {"data": {_CHAR_ID: {"items": equipped_items or []}}},
        "characterInventories": {"data": {_CHAR_ID: {"items": []}}},
        "profileInventory": {"data": {"items": vault_items}},
        "itemComponents": {},
    }


async def _seed_manifest(pool) -> None:
    """Minimal manifest with item hash 777 as a (non-exotic) weapon and hash
    778 as an exotic weapon, both homed in the Kinetic bucket, so the batch
    planner sees a real bucket."""
    items_data = {
        "777": {
            "displayProperties": {"name": "Test Weapon", "description": "", "icon": ""},
            "itemType": 3,
            "inventory": {"bucketTypeHash": _KINETIC, "tierType": 3},
        },
        str(_EXOTIC_HASH): {
            "displayProperties": {"name": "Test Exotic", "description": "", "icon": ""},
            "itemType": 3,
            "inventory": {"bucketTypeHash": _KINETIC, "tierType": 6},
        },
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


async def test_preview_blocks_a_locked_candidate(app_client, clean_db, monkeypatch):
    """A locked weapon is still surfaced as a candidate (so the UI can show it
    greyed with a reason) but must never be staged, even with free bucket
    space, because the blocklist filter is what keeps it out of plan.staged."""
    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 1, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")
    await user_tables.set_tag(clean_db, uid, "inst-2", "junk")

    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200
    body = resp.json()
    locked = next(c for c in body["candidates"] if c["instanceId"] == "inst-2")
    assert locked["blocked"] == "locked"
    assert locked["overridable"] is True
    # The important half: the locked candidate must be absent from staged
    # despite the Kinetic bucket having plenty of free space.
    assert "inst-2" not in body["plan"]["staged"]
    assert "inst-1" in body["plan"]["staged"]


async def test_preview_blocks_an_equipped_candidate(app_client, clean_db, monkeypatch):
    """An equipped weapon is a hard block — never overridable — even if the
    user tagged it junk."""
    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    equipped_items = [
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items, equipped_items)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")
    await user_tables.set_tag(clean_db, uid, "inst-3", "junk")

    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200
    body = resp.json()
    equipped = next(c for c in body["candidates"] if c["instanceId"] == "inst-3")
    assert equipped["blocked"] == "equipped"
    assert equipped["overridable"] is False
    assert "inst-3" not in body["plan"]["staged"]
    assert "inst-1" in body["plan"]["staged"]


async def test_preview_blocks_an_exotic_candidate(app_client, clean_db, monkeypatch):
    """An exotic weapon is blocked but overridable — distinct from the
    equipped hard block."""
    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": 138197802},
        {"itemInstanceId": "inst-4", "itemHash": _EXOTIC_HASH, "state": 0, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")
    await user_tables.set_tag(clean_db, uid, "inst-4", "junk")

    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200
    body = resp.json()
    exotic = next(c for c in body["candidates"] if c["instanceId"] == "inst-4")
    assert exotic["blocked"] == "exotic"
    assert exotic["overridable"] is True
    assert "inst-4" not in body["plan"]["staged"]
    assert "inst-1" in body["plan"]["staged"]


async def test_preview_requires_a_cached_profile(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]


async def test_preview_requires_authentication(app_client):
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 401
