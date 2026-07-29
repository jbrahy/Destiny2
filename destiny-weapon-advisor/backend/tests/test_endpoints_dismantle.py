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
    """Stand-in for the post-write cache refresh. Must never hit Bungie."""
    return _profile_with("inst-1", 777)


def _fake_get_profile_for(profile: dict):
    """Stand-in that always answers with `profile`. Sweep re-fetches the
    profile from Bungie before it evaluates candidates and lock state (the
    cache is up to user_cache_ttl_seconds stale, and staging is irreversible),
    so a sweep test's seeded inventory must be what that fetch returns."""
    async def _fake(mtype, mid, access, settings, http_client):
        return profile
    return _fake


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

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 1, "bucketHash": 138197802},
    ]
    profile = _profile_multi(vault_items)
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
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
    profile = _profile_with("inst-1", 777, locked=True)
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": ["inst-1"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}


async def test_sweep_does_not_overwrite_recorded_lock_state_on_restage(app_client, clean_db, monkeypatch):
    """Invariant: staging unlocks an item, so if a sweep runs a second time over
    an instance that is already staged, re-reading its (now unlocked) state must
    NOT clobber the True recorded on the first pass — that would destroy what
    undo needs to restore. The protection is the insert-only upsert, so this
    holds even without a read-then-write guard that a concurrent sweep could
    slip past."""
    locked_profile = _profile_with("inst-1", 777, locked=True)
    unlocked_profile = _profile_with("inst-1", 777)
    fetches = []

    async def fake_get_profile(mtype, mid, access, settings, http_client):
        """Only the first fetch — the first sweep's pre-check — still sees
        inst-1 locked; every fetch after it sees it unlocked, mirroring what
        that sweep's unlock call does to the real inventory."""
        fetches.append(1)
        return locked_profile if len(fetches) == 1 else unlocked_profile

    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(locked_profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    # First sweep: records the true prior lock state (True), then the refresh
    # leaves inst-1 unlocked — mirroring what a real unlock would do.
    resp1 = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": ["inst-1"],
    }, headers=_csrf_header(app_client))
    assert resp1.status_code == 200, resp1.text
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}

    # Second sweep over the same already-staged instance: it is no longer
    # blocked (the profile now shows it unlocked), so no override is needed.
    resp2 = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    }, headers=_csrf_header(app_client))
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["staged"] == ["inst-1"]
    # The load-bearing assertion: the recorded lock state must still be True.
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}


async def test_sweep_partial_failure_reports_failed_and_keeps_successes_staged(app_client, clean_db, monkeypatch):
    """Partial-failure contract: one item's transfer fails (BungieApiError),
    it lands in `failed` with its error, the loop continues, and the other
    item is still staged and still recorded — no rollback of successes."""
    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        if instance_id == "inst-2":
            raise BungieApiError("simulated transfer failure")

    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    profile = _profile_multi(vault_items)
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
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
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": False}


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

    vault_items = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 1, "bucketHash": 138197802},
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 1, "bucketHash": 138197802},
    ]
    profile = _profile_multi(vault_items)
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
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
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {
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

    equipped_items = [
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 0, "bucketHash": 138197802},
    ]
    profile = _profile_multi([], equipped_items)
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
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
    profile = _profile_with("inst-1", 777)
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
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


async def test_undo_relocks_then_returns_items_to_the_vault(app_client, clean_db, monkeypatch):
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id, to_vault))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert resp.json()["restored"] == ["inst-1"]

    kinds = [c[0] for c in calls]
    assert kinds.index("lock") < kinds.index("transfer")
    assert ("lock", "inst-1", True) in calls


async def test_undo_clears_the_staged_rows(app_client, clean_db, monkeypatch):
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {}


async def test_undo_with_nothing_staged_is_a_no_op(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"restored": [], "failed": []}


async def test_undo_mid_batch_failure_reports_failed_and_continues(app_client, clean_db, monkeypatch):
    """A failure on a NON-LAST item must not abort the batch: it lands in
    `failed`, the loop continues, and the item staged after it still gets
    restored."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))
        if instance_id == "inst-2":
            raise BungieApiError("simulated transfer failure")

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
        {"itemInstanceId": "inst-2", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
        {"itemInstanceId": "inst-3", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(
        clean_db, uid, "bm1", [("inst-1", True), ("inst-2", True), ("inst-3", True)]
    )

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["inst-1", "inst-3"]
    assert body["failed"] == [{"instanceId": "inst-2", "error": "simulated transfer failure"}]
    # All three were re-locked (proving the loop continued past inst-2's
    # transfer failure), and only the two that fully restored were cleared.
    assert [c for c in calls if c[0] == "lock"] == [
        ("lock", "inst-1", True), ("lock", "inst-2", True), ("lock", "inst-3", True),
    ]
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-2": True}


async def test_undo_read_timeout_is_caught_and_reported_as_failed(app_client, clean_db, monkeypatch):
    """FINDING carried forward from Task 7: httpx.ReadTimeout is an
    httpx.RequestError, a sibling of HTTPStatusError, not a subclass — the
    handler's except clause must catch it explicitly or a network blip
    propagates uncaught and aborts the whole undo batch."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))
        if instance_id == "inst-1":
            raise httpx.ReadTimeout("simulated network timeout")

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == []
    assert body["failed"] == [{"instanceId": "inst-1", "error": "simulated network timeout"}]
    # The lock call was attempted (and blew up) but transfer never ran.
    assert calls == [("lock", "inst-1", True)]
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}


async def test_undo_already_locked_item_restores_without_error(app_client, clean_db, monkeypatch):
    """Carry-forward from Task 7's review: an item whose unlock failed during
    the sweep was left transferred but still LOCKED. Undo re-locks it anyway
    — a harmless no-op against Bungie — and must not treat that as an error
    or skip the item."""
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
    profile = _profile_with("inst-1", 777)
    # Already locked in the profile (state=1), matching an item left locked
    # after a Task-7-style sweep unlock failure.
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 1, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["inst-1"]
    assert body["failed"] == []
    assert calls == [("lock", "inst-1", True), ("transfer", "inst-1")]
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {}


async def test_undo_missing_instance_counts_as_restored_not_failed(app_client, clean_db, monkeypatch):
    """FINDING 2(a): an instance id staged for undo but no longer anywhere in
    the cached profile was already dismantled in-game — the feature working
    as intended — so it must land in `restored`, not `failed`, and must never
    trigger a lock or transfer call."""
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
    # inst-missing is staged but never appears in the cached profile at all.
    profile = _profile_with("inst-1", 777)
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-missing", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["inst-missing"]
    assert body["failed"] == []
    assert calls == []
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {}


async def test_undo_does_not_relock_an_item_that_was_unlocked_before_the_sweep(app_client, clean_db, monkeypatch):
    """FINDING 2(b): `was_locked=False` must never trigger a lock call — only
    the transfer back to vault. Every other undo test stages with
    was_locked=True, so nothing else in this file proves the guard exists."""
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
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", False)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["inst-1"]
    assert calls == [("transfer", "inst-1")]


async def test_undo_relocks_on_the_character_that_actually_owns_the_item(app_client, clean_db, monkeypatch):
    """FINDING 3: nothing records which character a sweep staged an item to.
    If the item currently sits on a different character than the one
    selected in the undo request body, the re-lock call must target the
    item's actual owning character (resolved via _find_item_location), not
    blindly trust body.characterId — otherwise the lock call errors."""
    _CHAR_ID_2 = "char-2"
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id, character_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, character_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characters"]["data"][_CHAR_ID_2] = {
        "classType": 0, "light": 1800, "dateLastPlayed": "2024-01-01T00:00:00Z",
    }
    profile["characterInventories"]["data"][_CHAR_ID_2] = {"items": [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]}
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    # The undo request names _CHAR_ID (char-1), but inst-1 actually lives on
    # char-2 — the character the (unrecorded) sweep staged it to.
    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["restored"] == ["inst-1"]
    assert body["failed"] == []
    assert ("lock", "inst-1", _CHAR_ID_2, True) in calls


async def test_undo_after_account_switch_does_not_wipe_the_other_accounts_records(
    app_client, clean_db, monkeypatch
):
    """FINDING 1, reproduced end-to-end: stage a sweep under Destiny
    membership A, switch the active membership to B and load B's inventory
    (so profile_cache and profile_membership_id are both B, exactly like a
    real account switch), then call undo. Before the membership_id column,
    every one of A's staged instance ids was absent from B's profile, so the
    handler treated all of them as "already dismantled in-game", appended
    them to `restored`, and cleared every row — a false success that wiped
    the undo record for weapons that are still unlocked on account A. With
    the fix, undo (correctly scoped to B) sees nothing staged and returns a
    no-op, and A's rows must still be there afterward."""
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)  # active membership: "bm1"

    # Stage a sweep under account A ("bm1").
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    # Switch the active Destiny membership to account B ("bm2") — mirrors
    # POST /api/memberships/select, which is how a real account switch
    # updates the tokens row valid_access_token reads from.
    resp = await app_client.post("/api/memberships/select",
                                 json={"membershipType": 3, "membershipId": "bm2"})
    assert resp.status_code == 200, resp.text

    # Load B's inventory: profile_cache and profile_membership_id both now
    # reflect account B, and B's profile has no idea inst-1 ever existed.
    b_profile = _profile_with("inst-9", 999)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(b_profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm2", 3600)

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    # Undo, scoped to B, sees nothing staged — a true no-op, not a false
    # "successfully restored everything".
    assert resp.json() == {"restored": [], "failed": []}

    # The load-bearing assertion: account A's staged row survived.
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}
    # And it was never (incorrectly) visible under B's scope.
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm2") == {}


async def test_undo_with_a_degraded_profile_aborts_and_keeps_every_row(app_client, clean_db, monkeypatch):
    """FINAL-REVIEW FINDING 1. Bungie answers HTTP 200 with ErrorCode 1 but the
    component `data` ABSENT when a component is unavailable (reduced OAuth
    scope, privacy settings, partial outage), and that reply gets cached like
    any other. Every staged instance is then "missing from the profile", which
    the handler otherwise reads as "already dismantled in-game": it would
    report a clean restore and DELETE every row — and the row is the only
    record of a weapon's pre-sweep lock state, which cannot be re-derived once
    the weapon is unlocked. Undo must refuse the whole batch and clear
    nothing."""
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
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps({"characters": {"data": {}}}), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1",
                                        [("inst-1", True), ("inst-2", False)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 400, resp.text
    assert "Inventory data unavailable" in resp.json()["detail"]
    # Nothing was attempted against Bungie...
    assert calls == []
    # ...and the load-bearing assertion: every undo record survived intact.
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {
        "inst-1": True, "inst-2": False,
    }


# Destiny's postmaster ("Lost Items") bucket. Items sit here inside
# characterInventories, so nothing but the raw profile can tell them apart.
_POSTMASTER_BUCKET = 215593132


async def test_sweep_never_touches_a_weapon_in_the_postmaster(app_client, clean_db, monkeypatch):
    """FINAL-REVIEW FINDING 3. Postmaster items live in characterInventories,
    but a Candidate's bucket_hash comes from the manifest definition, so a
    postmaster hand cannon reports Kinetic and sails through the batch planner.
    When it is already on the target character _move_one sees source == target
    and transfers nothing — so the sweep would unlock it in place, in the
    postmaster, and report it as staged. Weapons only, never postmaster: it
    must not be a candidate at all."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    profile = _profile_multi([])
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "pm-1", "itemHash": 777, "state": 1,
         "bucketHash": _POSTMASTER_BUCKET},
    ]
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "pm-1", "junk")

    # Preview must not even offer it.
    prev = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert prev.status_code == 200, prev.text
    assert [c["instanceId"] for c in prev.json()["candidates"]] == []

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["pm-1"], "overrides": ["pm-1"],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staged"] == []
    assert body["rejected"] == [{"instanceId": "pm-1", "reason": "not_a_candidate"}]
    # The load-bearing assertion: no transfer, and above all no unlock.
    assert calls == []
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {}


async def test_undo_refuses_when_the_cached_profile_is_another_accounts(app_client, clean_db, monkeypatch):
    """FINAL-REVIEW FINDING 5. Sweep and both transfer endpoints refuse to act
    on a profile belonging to a different Destiny account; undo read staged
    rows for the token's membership but the profile with no such check, so it
    would decide "restore or already dismantled" from the wrong inventory —
    and clear rows on the strength of it."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile)

    uid = await login_user(app_client, monkeypatch)  # token membership: "bm1"
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-9", 999)), 3600)
    # The cached inventory belongs to a different Destiny account.
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm2", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1", [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID},
                                 headers=_csrf_header(app_client))
    assert resp.status_code == 400, resp.text
    assert "different account" in resp.json()["detail"]
    assert calls == []
    assert await user_tables.get_staged_sweep(clean_db, uid, "bm1") == {"inst-1": True}


async def test_sweep_reads_a_freshly_fetched_profile_not_the_stale_cache(app_client, clean_db, monkeypatch):
    """FINAL-REVIEW FINDING 6. The cache lives for user_cache_ttl_seconds (300),
    and BOTH halves of the lock protection read the profile: the `locked` block
    that keeps the weapon out of the sweep, and the was_locked recorded for
    undo. A user who locks a weapon in-game and sweeps inside that window would
    otherwise have it neither blocked NOR recorded — unlocked with no way back.
    So sweep must re-fetch from Bungie before evaluating anything."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    # What Bungie really holds: inst-1 was locked in-game a minute ago.
    live_profile = _profile_with("inst-1", 777, locked=True)
    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)
    monkeypatch.setattr("app.main.get_profile", _fake_get_profile_for(live_profile))

    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    # What the cache still says: unlocked, from before that lock.
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    # No override is sent — against the stale cache inst-1 looks unblocked and
    # would be swept; against the live profile it is `locked` and must not be.
    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    }, headers=_csrf_header(app_client))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staged"] == []
    assert body["rejected"] == [{"instanceId": "inst-1", "reason": "locked"}]
    assert calls == []


async def test_preview_reports_the_staged_sweep_for_the_undo_banner(app_client, clean_db, monkeypatch):
    """FINAL-REVIEW FINDING 7. preview's top-level `staged` map is the only
    signal that makes the Undo affordance appear, and its membership scoping
    was untested — a bogus membership id here silently hides Undo for a user
    with weapons sitting unlocked."""
    uid = await login_user(app_client, monkeypatch)
    await _seed_manifest(clean_db)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    await cache_repo.set(clean_db, uid, "profile_membership_id", "bm1", 3600)
    await user_tables.stage_sweep_items(clean_db, uid, "bm1",
                                        [("inst-1", True), ("inst-2", False)])

    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200, resp.text
    assert resp.json()["staged"] == {"inst-1": True, "inst-2": False}
