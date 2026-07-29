"""Endpoint wiring for the dismantle sweep. Bungie writes are faked; no test
touches a live inventory."""
import json

import httpx
import pytest

from app.bungie_client import BungieApiError
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


async def _noop_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                         access, settings, http_client):
    return None


async def _noop_lock(mtype, instance_id, character_id, state, access, settings, http_client):
    return None


async def _fake_get_profile(mtype, mid, access, settings, http_client):
    """Stand-in for the post-sweep cache refresh. Must never hit Bungie."""
    return _profile_with("inst-1", 777)


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


def _csrf_header(client) -> dict:
    """Read the csrftoken cookie from the client's cookie jar."""
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


async def test_sweep_transfers_then_unlocks_in_that_order(app_client, clean_db, monkeypatch):
    """The ordering guarantee, checked per item across a two-item batch: an
    interrupted sweep must never leave an unlocked weapon sitting in the
    vault. A single-item batch can't distinguish this from a "transfer ALL,
    then unlock ALL" regression, which would still leave every item but the
    last unlocked-in-vault during an interruption — so this asserts the exact
    interleaved call sequence, not just a single index comparison."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 1, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")
    await user_tables.set_tag(clean_db, uid, "inst-2", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1", "inst-2"],
        "overrides": ["inst-1", "inst-2"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert resp.json()["staged"] == ["inst-1", "inst-2"]

    assert calls == [
        ("transfer", "inst-1"), ("lock", "inst-1", False),
        ("transfer", "inst-2"), ("lock", "inst-2", False),
    ]


async def test_sweep_records_prior_lock_state_for_undo(app_client, clean_db, monkeypatch):
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777, locked=True)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": ["inst-1"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert await user_tables.get_staged_sweep(clean_db, uid) == {"inst-1": True}


async def test_sweep_does_not_overwrite_recorded_lock_state_on_restage(app_client, clean_db, monkeypatch):
    """Invariant: staging unlocks an item, so if a sweep runs a second time over
    an instance that is already staged, re-reading its (now unlocked) state must
    NOT clobber the True recorded on the first pass — that would destroy what
    undo needs to restore."""
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777, locked=True)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    # First sweep: records the true prior lock state (True) and, via
    # _fake_get_profile, refreshes the cache to show inst-1 unlocked — mirroring
    # what a real unlock would do to the cached inventory.
    resp1 = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": ["inst-1"],
    }, headers=_csrf_header(app_client))
    assert resp1.status_code == 200, resp1.text
    assert await user_tables.get_staged_sweep(clean_db, uid) == {"inst-1": True}

    # Second sweep over the same already-staged instance: it is no longer
    # blocked (the cache now shows it unlocked), so no override is needed.
    resp2 = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    }, headers=_csrf_header(app_client))
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["staged"] == ["inst-1"]
    # The load-bearing assertion: the recorded lock state must still be True.
    assert await user_tables.get_staged_sweep(clean_db, uid) == {"inst-1": True}


async def test_sweep_partial_failure_reports_failed_and_keeps_successes_staged(app_client, clean_db, monkeypatch):
    """Partial-failure contract: one item's transfer fails (BungieApiError),
    it lands in `failed` with its error, the loop continues, and the other
    item is still staged and still recorded — no rollback of successes."""
    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        if instance_id == "inst-2":
            raise BungieApiError("simulated transfer failure")

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")
    await user_tables.set_tag(clean_db, uid, "inst-2", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1", "inst-2"], "overrides": [],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staged"] == ["inst-1"]
    assert body["failed"] == [{"instanceId": "inst-2", "error": "simulated transfer failure"}]
    # inst-2's transfer never ran to completion, so it should never have been
    # recorded — only inst-1, which fully succeeded.
    assert await user_tables.get_staged_sweep(clean_db, uid) == {"inst-1": False}


async def test_sweep_unlock_timeout_preserves_recorded_lock_state(app_client, clean_db, monkeypatch):
    """FINDING 1 regression guard. httpx.ReadTimeout is an httpx.RequestError
    — a SIBLING of HTTPStatusError, not a subclass — so the handler's except
    clause must catch it explicitly or a bare network blip on one item's
    unlock call would propagate uncaught and abort the whole sweep.

    More importantly: the item whose unlock times out must still have its
    true prior lock state recorded, because the write now happens right after
    its transfer succeeds and before the unlock call that failed — not
    batched up and flushed only after the entire loop finishes. And the
    batch must continue past the failure: the item staged after the failing
    one must still be transferred, unlocked, and recorded too."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))
        if instance_id == "inst-2":
            raise httpx.ReadTimeout("simulated network timeout")

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 1, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi(vault_items)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    for iid in ("inst-1", "inst-2", "inst-3"):
        await user_tables.set_tag(clean_db, uid, iid, "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1", "inst-2", "inst-3"],
        "overrides": ["inst-1", "inst-2", "inst-3"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staged"] == ["inst-1", "inst-3"]
    assert body["failed"] == [{"instanceId": "inst-2", "error": "simulated network timeout"}]
    # All three transfers ran (the timeout happened on the unlock call), and
    # the loop continued past inst-2's failure to process inst-3.
    assert [c for c in calls if c[0] == "transfer"] == [
        ("transfer", "inst-1"), ("transfer", "inst-2"), ("transfer", "inst-3"),
    ]

    # The load-bearing assertion: inst-2's transfer succeeded before its
    # unlock blew up, so its true prior lock state (True) must still have
    # been recorded, exactly like inst-1 and inst-3.
    assert await user_tables.get_staged_sweep(clean_db, uid) == {
        "inst-1": True, "inst-2": True, "inst-3": True,
    }


async def test_sweep_override_cannot_unblock_an_equipped_weapon(app_client, clean_db, monkeypatch):
    """The equipped block is a hard block — never overridable — even for the
    live-writing endpoint, not just the pure blocklist layer. Passing the
    equipped item's id in both instanceIds and overrides must still reject
    it, and must never touch Bungie's transfer endpoint for it."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(instance_id)

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    equipped_items = [
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_multi([], equipped_items)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-3", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-3"], "overrides": ["inst-3"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staged"] == []
    assert body["rejected"] == [{"instanceId": "inst-3", "reason": "equipped"}]
    assert calls == []


async def test_sweep_rejects_an_instance_the_preview_never_offered(app_client, clean_db, monkeypatch):
    """Server-side re-check: a client cannot smuggle in an arbitrary item."""
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    # no junk tag, so inst-1 is not a candidate at all

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert resp.json()["staged"] == []
    assert resp.json()["rejected"] == [
        {"instanceId": "inst-1", "reason": "not_a_candidate"},
    ]
