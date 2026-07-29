# Weapon Dismantle Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user stage a batch of unwanted weapons from the web UI — moved onto one character and unlocked — so they can dismantle the whole batch from a single in-game inventory screen.

**Architecture:** Bungie's API has no dismantle endpoint, so the app stages rather than destroys. Pure decision logic (blocklist, batch planning) lives in a new `app/dismantle.py`; three thin FastAPI endpoints in `main.py` orchestrate Bungie writes through the existing throttle; a new `user_sweep_items` table records prior lock state so a sweep can be undone.

**Tech Stack:** Python 3 / FastAPI / aiomysql / httpx (backend, `pytest` + `pytest-asyncio`), React + TypeScript (frontend), MySQL 8.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-28-weapon-dismantle-sweep-design.md`. Read it before starting.
- **Weapons only.** Never touch armor, consumables, or postmaster items.
- **Blocklist is server-enforced.** The client is never trusted to filter. Every blocklist rule is re-checked in `/api/dismantle/sweep` even though `/api/dismantle/preview` already reported it.
- **Ordering:** for each item, transfer strictly precedes unlock. Undo reverses it: re-lock, then transfer to vault.
- **No test touches live inventory.** All Bungie calls in tests go through fakes.
- Verdicts are the `Verdict` enum in `app/models.py` (`god_roll`, `masterwork`, `good`, `no_data`, `dismantle`). The S/A/B/C/D scale (`TIER_SCORE` in `app/perk_ratings.py`) rates *perks*, not weapons. Do not conflate them.
- **Blocklist precedence (amended after the Task 3 review, and load-bearing):** `equipped` → `BLOCK_EQUIPPED`, never overridable; then `locked` → `BLOCK_LOCKED`; then `exotic` → `BLOCK_EXOTIC`; then `god_roll`/`masterwork` → `BLOCK_VERDICT`; all three of those overridable. `OwnedWeapon.is_locked` comes from the item state bitmask (`_LOCKED_STATE = 1` in `app/bungie_client.py`).
- **Tag exclusions (amended after the Task 3 review):** `keep`, `favorite`, and `infuse` all exclude a weapon from a sweep entirely. Only `junk` and untagged weapons are eligible.
- Backend tests run from `destiny-weapon-advisor/backend/` and need a live MySQL (`conftest.py` creates and drops the `advisor_test` database).
- Follow existing style: no docstring-free public functions, keep `main.py` handlers thin, match the `snake_case` backend / `camelCase` JSON boundary already used by `weapon_to_dict`.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/manifest.py` | *(modify)* add `bucket_hash()` accessor |
| `backend/app/models.py` | *(modify)* add `is_exotic`, `bucket_hash` to `OwnedWeapon` |
| `backend/app/bungie_client.py` | *(modify)* populate the two new fields; add `set_item_lock_state()` |
| `backend/app/dismantle.py` | **new** — pure logic: candidate classification, blocklist, batch planning |
| `backend/migrations/0004_dismantle_sweeps.sql` | **new** — `user_sweep_items` table |
| `backend/app/repositories/user_tables.py` | *(modify)* stage / read / clear sweep rows |
| `backend/app/main.py` | *(modify)* three endpoints + request models |
| `frontend/src/api.ts` | *(modify)* three client functions + types |
| `frontend/src/components/DismantlePage.tsx` | **new** — preview table, batch banner, staged state |
| `frontend/src/components/Nav.tsx` | *(modify)* add `"dismantle"` section |
| `frontend/src/components/AppShell.tsx` | *(modify)* render the section |

---

### Task 1: Expose exotic + bucket on weapons

`OwnedWeapon` carries no exotic flag and no inventory bucket. The blocklist needs the first; the batch planner needs the second. A vault item's `bucketHash` in the profile payload is the *vault* bucket, not the weapon bucket, so bucket must come from the manifest definition (`inventory.bucketTypeHash`), not the profile.

**Files:**
- Modify: `backend/app/manifest.py:31` (add accessor after `tier_type`)
- Modify: `backend/app/models.py:14-30` (`OwnedWeapon`)
- Modify: `backend/app/bungie_client.py:93-110` (`assemble_weapons`)
- Test: `backend/tests/test_bungie_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Manifest.bucket_hash(item_hash: int) -> int`; `OwnedWeapon.is_exotic: bool`; `OwnedWeapon.bucket_hash: int`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bungie_client.py`:

```python
def test_manifest_bucket_hash_reads_inventory_bucket_type_hash():
    m = Manifest(items={555: {"inventory": {"bucketTypeHash": 1498876634}}})
    assert m.bucket_hash(555) == 1498876634


def test_manifest_bucket_hash_defaults_to_zero_when_missing():
    assert Manifest(items={}).bucket_hash(999) == 0


def test_assemble_weapons_sets_is_exotic_and_bucket_hash():
    """tierType 6 is Exotic; tierType 5 is Legendary (already used for is_random_roll)."""
    manifest = Manifest(items={
        777: {
            "displayProperties": {"name": "Gjallarhorn", "icon": "/gjally.jpg"},
            "itemType": 3,
            "itemTypeDisplayName": "Rocket Launcher",
            "inventory": {"tierType": 6, "bucketTypeHash": 953998645},
            "equippingBlock": {"ammoType": 3},
        },
    })
    profile = {
        "characters": {"data": {}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "inst-777", "itemHash": 777, "state": 0},
        ]}},
        "itemComponents": {},
    }
    weapons = assemble_weapons(profile, manifest)
    assert len(weapons) == 1
    assert weapons[0].is_exotic is True
    assert weapons[0].bucket_hash == 953998645
```

Make sure `Manifest` and `assemble_weapons` are imported at the top of the file (add to the existing import line if absent).

- [ ] **Step 2: Run test to verify it fails**

```bash
cd destiny-weapon-advisor/backend
python -m pytest tests/test_bungie_client.py -k "bucket_hash or is_exotic" -v
```

Expected: FAIL — `AttributeError: 'Manifest' object has no attribute 'bucket_hash'`.

- [ ] **Step 3: Add the manifest accessor**

In `backend/app/manifest.py`, directly after `tier_type`:

```python
    def bucket_hash(self, item_hash: int) -> int:
        """The item's home inventory bucket. Read from the definition, not the
        profile: a vault-held item reports the vault bucket in the profile."""
        return self._def(item_hash).get("inventory", {}).get("bucketTypeHash", 0)
```

- [ ] **Step 4: Add the model fields**

In `backend/app/models.py`, add to `OwnedWeapon` (after `equipped: bool = False`, keeping defaults last):

```python
    is_exotic: bool = False
    bucket_hash: int = 0
```

- [ ] **Step 5: Populate them in assemble_weapons**

In `backend/app/bungie_client.py`, inside the `OwnedWeapon(...)` constructor call, after `equipped=equipped,`:

```python
                is_exotic=manifest.tier_type(item_hash) == 6,
                bucket_hash=manifest.bucket_hash(item_hash),
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_bungie_client.py -v
```

Expected: PASS, including all pre-existing tests in the file.

- [ ] **Step 7: Commit**

```bash
git add app/manifest.py app/models.py app/bungie_client.py tests/test_bungie_client.py
git commit -m "feat(weapons): expose is_exotic and bucket_hash on OwnedWeapon"
```

---

### Task 2: SetItemLockState client call

**Files:**
- Modify: `backend/app/bungie_client.py:198` (insert after `equip_item`)
- Test: `backend/tests/test_bungie_client.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `async set_item_lock_state(membership_type: int, instance_id: str, character_id: str, state: bool, access_token: str, settings: Settings, client: httpx.AsyncClient) -> None`. `state=True` locks, `state=False` unlocks. Raises `BungieApiError` on a non-success envelope.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bungie_client.py`:

```python
@pytest.mark.asyncio
async def test_set_item_lock_state_posts_expected_payload():
    calls = []

    class FakeResponse:
        def json(self):
            return {"ErrorCode": 1, "Response": 0}

    class FakeClient:
        async def post(self, url, json=None, headers=None):
            calls.append((url, json))
            return FakeResponse()

    settings = get_settings()
    await set_item_lock_state(
        3, "inst-1", "char-1", False, "token", settings, FakeClient()
    )

    url, payload = calls[0]
    assert url.endswith("/Destiny2/Actions/Items/SetItemLockState/")
    assert payload == {
        "state": False,
        "itemId": "inst-1",
        "characterId": "char-1",
        "membershipType": 3,
    }


@pytest.mark.asyncio
async def test_set_item_lock_state_raises_on_bungie_error():
    class FakeResponse:
        def json(self):
            return {"ErrorCode": 1618, "ErrorStatus": "DestinyItemNotFound",
                    "Message": "Item not found."}

    class FakeClient:
        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    with pytest.raises(BungieApiError):
        await set_item_lock_state(
            3, "inst-1", "char-1", False, "token", get_settings(), FakeClient()
        )
```

Ensure `pytest`, `get_settings`, `set_item_lock_state`, and `BungieApiError` are imported at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_bungie_client.py -k set_item_lock_state -v
```

Expected: FAIL — `ImportError: cannot import name 'set_item_lock_state'`.

- [ ] **Step 3: Write the implementation**

In `backend/app/bungie_client.py`, after `equip_item`:

```python
async def set_item_lock_state(
    membership_type: int, instance_id: str, character_id: str, state: bool,
    access_token: str, settings: Settings, client: httpx.AsyncClient,
) -> None:
    """Lock (state=True) or unlock (state=False) an item instance. Unlocking is
    the prerequisite for the user dismantling it in-game."""
    resp = await client.post(
        f"{_BASE}/Destiny2/Actions/Items/SetItemLockState/",
        json={
            "state": state, "itemId": instance_id,
            "characterId": character_id, "membershipType": membership_type,
        },
        headers=_headers(settings, access_token),
    )
    _raise_for_bungie(resp)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_bungie_client.py -k set_item_lock_state -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/bungie_client.py tests/test_bungie_client.py
git commit -m "feat(bungie): add set_item_lock_state client call"
```

---

### Task 3: Candidate classification and blocklist

The heart of the feature and the file that prevents an irreplaceable weapon from being staged. Pure functions, no I/O, no DB.

**Files:**
- Create: `backend/app/dismantle.py`
- Test: `backend/tests/test_dismantle_blocklist.py`

**Interfaces:**
- Consumes: `OwnedWeapon.is_exotic`, `OwnedWeapon.bucket_hash` (Task 1); `Verdict` from `app/models.py`; the dict shape returned by `score_by_perks` (`{"weapon", "verdict", "rated", "note", "tags", "is_duplicate"}`, optional `"dupe_demoted"`).
- Produces:
  - `WEAPON_BUCKETS: dict[int, str]`, `BUCKET_CAPACITY: int`
  - `BLOCK_EXOTIC`, `BLOCK_VERDICT`, `BLOCK_EQUIPPED`: `str` constants
  - `@dataclass Candidate` with fields `instance_id, item_hash, name, icon, power, bucket_hash, verdict, source, reason, blocked, overridable`
  - `classify(scored: list[dict], tags: dict[str, str]) -> list[Candidate]`
  - `enforce_blocklist(candidates: list[Candidate], requested_ids: list[str], overrides: list[str]) -> tuple[list[str], list[dict]]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dismantle_blocklist.py`:

```python
"""Blocklist enforcement — the guard against staging something irreplaceable.

Rules under test:
  exotic          -> blocked, override permitted
  god_roll        -> blocked, override permitted
  masterwork      -> blocked, override permitted
  equipped        -> blocked, override NEVER permitted
  good / no_data  -> allowed only if the user tagged them junk
  dismantle       -> suggested (unchecked), allowed when requested
"""
from app.dismantle import (
    BLOCK_EQUIPPED, BLOCK_EXOTIC, BLOCK_VERDICT,
    Candidate, classify, enforce_blocklist,
)
from app.models import OwnedWeapon, Verdict


def _weapon(instance_id, **kw):
    defaults = dict(
        item_hash=1, name="Test Gun", weapon_type="Hand Cannon", element="Arc",
        is_masterworked=False, is_random_roll=True, perks=frozenset(),
        location="Vault", power=1800, icon="/i.jpg", equipped=False,
        is_exotic=False, bucket_hash=1498876634,
    )
    defaults.update(kw)
    return OwnedWeapon(instance_id=instance_id, **defaults)


def _scored(weapon, verdict, **kw):
    row = {"weapon": weapon, "verdict": verdict, "rated": [], "note": "",
           "tags": [], "is_duplicate": False}
    row.update(kw)
    return row


def test_junk_tagged_weapon_is_a_tagged_candidate():
    scored = [_scored(_weapon("a"), Verdict.GOOD)]
    out = classify(scored, {"a": "junk"})
    assert len(out) == 1
    assert out[0].source == "tagged"
    assert out[0].blocked == ""


def test_dismantle_verdict_is_a_suggestion():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    out = classify(scored, {})
    assert out[0].source == "suggested"
    assert out[0].blocked == ""


def test_good_and_no_data_are_not_candidates_without_a_junk_tag():
    scored = [_scored(_weapon("a"), Verdict.GOOD),
              _scored(_weapon("b"), Verdict.NO_DATA)]
    assert classify(scored, {}) == []


def test_keep_tag_excludes_a_dismantle_verdict_weapon():
    """An explicit keep beats the engine's suggestion."""
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    assert classify(scored, {"a": "keep"}) == []


def test_exotic_is_blocked_but_overridable():
    scored = [_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EXOTIC
    assert out[0].overridable is True


def test_god_roll_and_masterwork_verdicts_are_blocked_but_overridable():
    scored = [_scored(_weapon("a"), Verdict.GOD_ROLL),
              _scored(_weapon("b"), Verdict.MASTERWORK)]
    out = classify(scored, {"a": "junk", "b": "junk"})
    assert {c.instance_id: c.blocked for c in out} == {
        "a": BLOCK_VERDICT, "b": BLOCK_VERDICT,
    }
    assert all(c.overridable for c in out)


def test_equipped_is_blocked_and_not_overridable():
    scored = [_scored(_weapon("a", equipped=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EQUIPPED
    assert out[0].overridable is False


def test_dupe_demoted_suggestion_reports_the_duplicate_reason():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE, dupe_demoted=True,
                      note="A better-perked copy of this weapon exists in your inventory.")]
    out = classify(scored, {})
    assert "better-perked copy" in out[0].reason


def test_enforce_blocklist_allows_a_clean_request():
    cands = classify([_scored(_weapon("a"), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], [])
    assert allowed == ["a"]
    assert rejected == []


def test_enforce_blocklist_rejects_a_blocked_item_without_override():
    cands = classify([_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], [])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EXOTIC}]


def test_enforce_blocklist_permits_a_blocked_item_with_override():
    cands = classify([_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], ["a"])
    assert allowed == ["a"]
    assert rejected == []


def test_override_cannot_unblock_an_equipped_weapon():
    """The hard block. An override must never reach the equipped rule."""
    cands = classify([_scored(_weapon("a", equipped=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], ["a"])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EQUIPPED}]


def test_enforce_blocklist_rejects_an_id_that_is_not_a_candidate():
    """A client asking to sweep something the preview never offered."""
    cands = classify([_scored(_weapon("a"), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["ghost-id"], [])
    assert allowed == []
    assert rejected == [{"instanceId": "ghost-id", "reason": "not_a_candidate"}]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_dismantle_blocklist.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.dismantle'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/dismantle.py`:

```python
"""Dismantle-sweep decision logic.

Bungie's API cannot dismantle an item, so a "sweep" stages weapons onto one
character and unlocks them; the user dismantles the batch in-game. Everything
in this module is pure — no I/O — so the rules that protect a user's inventory
are cheap to test exhaustively.
"""
from dataclasses import dataclass

from app.models import Verdict

# Destiny 2 weapon inventory buckets. A character holds 9 unequipped per bucket
# (the equipped item lives in characterEquipment, a separate bucket).
WEAPON_BUCKETS = {
    1498876634: "Kinetic",
    2465295065: "Energy",
    953998645: "Power",
}
BUCKET_CAPACITY = 9

BLOCK_EXOTIC = "exotic"
BLOCK_VERDICT = "high_verdict"
BLOCK_EQUIPPED = "equipped"

# Verdicts good enough that staging one requires an explicit override.
_BLOCKED_VERDICTS = {Verdict.GOD_ROLL, Verdict.MASTERWORK}
# The verdict the engine already flags as not worth keeping.
_SUGGESTED_VERDICT = Verdict.DISMANTLE


@dataclass
class Candidate:
    instance_id: str
    item_hash: int
    name: str
    icon: str
    power: int
    bucket_hash: int
    verdict: str
    source: str        # "tagged" | "suggested"
    reason: str
    blocked: str       # "" | BLOCK_EXOTIC | BLOCK_VERDICT | BLOCK_EQUIPPED
    overridable: bool


def classify(scored: list[dict], tags: dict[str, str]) -> list[Candidate]:
    """Build the sweep candidate list from scored weapons and the user's tags.

    A weapon is a candidate if the user tagged it 'junk', or if the scoring
    engine returned Verdict.DISMANTLE. An explicit 'keep' tag always wins.
    Blocked candidates are still returned — the UI shows them greyed with a
    reason, so a block is visible rather than a silent omission.
    """
    out: list[Candidate] = []
    for row in scored:
        weapon = row["weapon"]
        tag = tags.get(weapon.instance_id, "")
        if tag == "keep":
            continue

        if tag == "junk":
            source, reason = "tagged", "You tagged this junk."
        elif row["verdict"] == _SUGGESTED_VERDICT:
            source = "suggested"
            reason = (
                row.get("note")
                if row.get("dupe_demoted")
                else "Suggested: only low-value perks."
            )
        else:
            continue

        if weapon.equipped:
            blocked, overridable = BLOCK_EQUIPPED, False
        elif weapon.is_exotic:
            blocked, overridable = BLOCK_EXOTIC, True
        elif row["verdict"] in _BLOCKED_VERDICTS:
            blocked, overridable = BLOCK_VERDICT, True
        else:
            blocked, overridable = "", False

        out.append(Candidate(
            instance_id=weapon.instance_id,
            item_hash=weapon.item_hash,
            name=weapon.name,
            icon=weapon.icon,
            power=weapon.power,
            bucket_hash=weapon.bucket_hash,
            verdict=row["verdict"].value,
            source=source,
            reason=reason,
            blocked=blocked,
            overridable=overridable,
        ))
    return out


def enforce_blocklist(
    candidates: list[Candidate], requested_ids: list[str], overrides: list[str],
) -> tuple[list[str], list[dict]]:
    """Filter a client's requested sweep down to what is actually permitted.

    Re-run server-side on every sweep even though preview already reported the
    blocks — the client is not trusted to have honored them. Returns
    (allowed_instance_ids, rejected) where rejected entries are
    {"instanceId": str, "reason": str}.
    """
    by_id = {c.instance_id: c for c in candidates}
    override_set = set(overrides)
    allowed: list[str] = []
    rejected: list[dict] = []

    for instance_id in requested_ids:
        candidate = by_id.get(instance_id)
        if candidate is None:
            rejected.append({"instanceId": instance_id, "reason": "not_a_candidate"})
            continue
        if not candidate.blocked:
            allowed.append(instance_id)
            continue
        if candidate.overridable and instance_id in override_set:
            allowed.append(instance_id)
            continue
        rejected.append({"instanceId": instance_id, "reason": candidate.blocked})

    return allowed, rejected
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_dismantle_blocklist.py -v
```

Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
git add app/dismantle.py tests/test_dismantle_blocklist.py
git commit -m "feat(dismantle): candidate classification and server-enforced blocklist"
```

---

### Task 4: Batch planner

A character holds 9 unequipped weapons per bucket. A 31-weapon sweep cannot happen in one pass; the planner decides what fits now and what waits.

**Files:**
- Modify: `backend/app/dismantle.py` (append)
- Test: `backend/tests/test_dismantle_batching.py`

**Interfaces:**
- Consumes: `Candidate`, `WEAPON_BUCKETS`, `BUCKET_CAPACITY` (Task 3).
- Produces:
  - `@dataclass BatchPlan` with fields `staged: list[str]`, `deferred: list[str]`, `per_bucket: dict[int, dict]`
  - `plan_batch(candidates: list[Candidate], allowed_ids: list[str], occupancy: dict[int, int]) -> BatchPlan`
  - `bucket_occupancy(profile: dict, character_id: str) -> dict[int, int]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dismantle_batching.py`:

```python
"""Batch planning — a character holds BUCKET_CAPACITY unequipped weapons per
bucket, so a large sweep is necessarily split across several in-game passes."""
from app.dismantle import (
    BUCKET_CAPACITY, Candidate, bucket_occupancy, plan_batch,
)

KINETIC, ENERGY, POWER = 1498876634, 2465295065, 953998645


def _cand(instance_id, bucket_hash=KINETIC):
    return Candidate(
        instance_id=instance_id, item_hash=1, name="Gun", icon="/i.jpg",
        power=1800, bucket_hash=bucket_hash, verdict="dismantle",
        source="tagged", reason="", blocked="", overridable=False,
    )


def test_everything_fits_in_an_empty_bucket():
    cands = [_cand(f"k{i}") for i in range(5)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert plan.staged == ["k0", "k1", "k2", "k3", "k4"]
    assert plan.deferred == []


def test_overflow_is_deferred_in_request_order():
    cands = [_cand(f"k{i}") for i in range(12)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert len(plan.staged) == BUCKET_CAPACITY
    assert plan.staged == [f"k{i}" for i in range(9)]
    assert plan.deferred == ["k9", "k10", "k11"]


def test_existing_occupancy_reduces_free_space():
    cands = [_cand(f"k{i}") for i in range(5)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {KINETIC: 7})
    assert plan.staged == ["k0", "k1"]
    assert plan.deferred == ["k2", "k3", "k4"]


def test_a_full_bucket_stages_nothing_from_it():
    cands = [_cand("k0")]
    plan = plan_batch(cands, ["k0"], {KINETIC: BUCKET_CAPACITY})
    assert plan.staged == []
    assert plan.deferred == ["k0"]


def test_buckets_are_budgeted_independently():
    cands = [_cand(f"k{i}", KINETIC) for i in range(10)] + [_cand("e0", ENERGY), _cand("p0", POWER)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert "e0" in plan.staged and "p0" in plan.staged
    assert plan.deferred == ["k9"]


def test_per_bucket_reports_free_and_staged_counts():
    cands = [_cand(f"k{i}") for i in range(4)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {KINETIC: 6})
    assert plan.per_bucket[KINETIC] == {"free": 3, "staged": 3, "name": "Kinetic"}


def test_unknown_bucket_is_deferred_rather_than_staged():
    """Defensive: a non-weapon bucket must never be staged."""
    plan = plan_batch([_cand("x", 999)], ["x"], {})
    assert plan.staged == []
    assert plan.deferred == ["x"]


def test_bucket_occupancy_counts_only_the_target_character_weapon_buckets():
    profile = {"characterInventories": {"data": {
        "char-1": {"items": [
            {"bucketHash": KINETIC}, {"bucketHash": KINETIC}, {"bucketHash": POWER},
            {"bucketHash": 138197802},  # general/vault-ish bucket, must be ignored
        ]},
        "char-2": {"items": [{"bucketHash": KINETIC}]},
    }}}
    assert bucket_occupancy(profile, "char-1") == {KINETIC: 2, ENERGY: 0, POWER: 1}


def test_bucket_occupancy_of_an_unknown_character_is_all_zero():
    assert bucket_occupancy({"characterInventories": {"data": {}}}, "nope") == {
        KINETIC: 0, ENERGY: 0, POWER: 0,
    }
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_dismantle_batching.py -v
```

Expected: FAIL — `ImportError: cannot import name 'plan_batch'`.

- [ ] **Step 3: Write the implementation**

Append to `backend/app/dismantle.py`:

```python
@dataclass
class BatchPlan:
    staged: list[str]
    deferred: list[str]
    per_bucket: dict[int, dict]


def bucket_occupancy(profile: dict, character_id: str) -> dict[int, int]:
    """Count weapons already sitting unequipped in each of the target
    character's weapon buckets. Equipped items live in characterEquipment and
    do not consume inventory space, so they are correctly not counted here."""
    occupancy = {bucket: 0 for bucket in WEAPON_BUCKETS}
    inventories = profile.get("characterInventories", {}).get("data", {})
    for item in inventories.get(character_id, {}).get("items", []):
        bucket = item.get("bucketHash")
        if bucket in occupancy:
            occupancy[bucket] += 1
    return occupancy


def plan_batch(
    candidates: list[Candidate], allowed_ids: list[str], occupancy: dict[int, int],
) -> BatchPlan:
    """Split an approved sweep into what fits on the character now and what
    waits for the next pass. Preserves request order within each bucket."""
    by_id = {c.instance_id: c for c in candidates}
    free = {
        bucket: max(0, BUCKET_CAPACITY - occupancy.get(bucket, 0))
        for bucket in WEAPON_BUCKETS
    }
    staged_per_bucket = {bucket: 0 for bucket in WEAPON_BUCKETS}
    staged: list[str] = []
    deferred: list[str] = []

    for instance_id in allowed_ids:
        candidate = by_id.get(instance_id)
        bucket = candidate.bucket_hash if candidate else None
        if bucket not in free or free[bucket] <= 0:
            deferred.append(instance_id)
            continue
        free[bucket] -= 1
        staged_per_bucket[bucket] += 1
        staged.append(instance_id)

    per_bucket = {
        bucket: {
            "name": name,
            "free": max(0, BUCKET_CAPACITY - occupancy.get(bucket, 0)),
            "staged": staged_per_bucket[bucket],
        }
        for bucket, name in WEAPON_BUCKETS.items()
    }
    return BatchPlan(staged=staged, deferred=deferred, per_bucket=per_bucket)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_dismantle_batching.py tests/test_dismantle_blocklist.py -v
```

Expected: PASS, all tests in both files.

- [ ] **Step 5: Commit**

```bash
git add app/dismantle.py tests/test_dismantle_batching.py
git commit -m "feat(dismantle): batch planner respecting per-bucket capacity"
```

---

### Task 5: Sweep persistence

Undo has to restore the lock state each weapon had *before* the sweep, which means recording it at stage time.

**Files:**
- Create: `backend/migrations/0004_dismantle_sweeps.sql`
- Modify: `backend/app/repositories/user_tables.py` (append a new section)
- Modify: `backend/tests/conftest.py:44` (add the table to `_DATA_TABLES`)
- Test: `backend/tests/test_dismantle_undo.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `async stage_sweep_items(pool, user_id: int, rows: list[tuple[str, bool]]) -> None` — rows are `(instance_id, was_locked)`; upserts.
  - `async get_staged_sweep(pool, user_id: int) -> dict[str, bool]` — `{instance_id: was_locked}`.
  - `async clear_sweep_items(pool, user_id: int, instance_ids: list[str]) -> None` — empty list is a no-op.

- [ ] **Step 1: Write the migration**

Create `backend/migrations/0004_dismantle_sweeps.sql`:

```sql
CREATE TABLE IF NOT EXISTS user_sweep_items (
    user_id BIGINT(20) UNSIGNED NOT NULL,
    instance_id VARCHAR(32) NOT NULL,
    was_locked TINYINT(1) NOT NULL DEFAULT 0,
    staged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, instance_id),
    CONSTRAINT fk_user_sweep_items_user FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

- [ ] **Step 2: Register the table for test truncation**

In `backend/tests/conftest.py`, add `"user_sweep_items",` to the `_DATA_TABLES` tuple, immediately after `"user_item_tags",`.

- [ ] **Step 3: Write the failing test**

Create `backend/tests/test_dismantle_undo.py`:

```python
"""Sweep persistence: prior lock state must survive so undo can restore it.

Follows the two_users fixture pattern from test_user_data_repos.py — users are
created with users_repo.upsert against the clean_db pool.
"""
import pytest
import pytest_asyncio

from app.repositories import user_tables
from app.repositories import users as users_repo

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def two_users(clean_db):
    """Create two users and return (pool, user_a_id, user_b_id)."""
    pool = clean_db
    uid_a = await users_repo.upsert(pool, "sweepA", "SweepA", 3, "mbrSweepA")
    uid_b = await users_repo.upsert(pool, "sweepB", "SweepB", 3, "mbrSweepB")
    return pool, uid_a, uid_b


async def test_staged_rows_round_trip_with_lock_state(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, [("a", True), ("b", False)])
    assert await user_tables.get_staged_sweep(pool, uid) == {"a": True, "b": False}


async def test_staging_the_same_instance_twice_updates_rather_than_duplicates(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, [("a", True)])
    await user_tables.stage_sweep_items(pool, uid, [("a", False)])
    assert await user_tables.get_staged_sweep(pool, uid) == {"a": False}


async def test_clear_removes_only_the_named_instances(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, [("a", True), ("b", True)])
    await user_tables.clear_sweep_items(pool, uid, ["a"])
    assert await user_tables.get_staged_sweep(pool, uid) == {"b": True}


async def test_clear_with_an_empty_list_is_a_no_op(two_users):
    pool, uid, _ = two_users
    await user_tables.stage_sweep_items(pool, uid, [("a", True)])
    await user_tables.clear_sweep_items(pool, uid, [])
    assert await user_tables.get_staged_sweep(pool, uid) == {"a": True}


async def test_sweeps_are_isolated_per_user(two_users):
    pool, uid_a, uid_b = two_users
    await user_tables.stage_sweep_items(pool, uid_a, [("a", True)])
    assert await user_tables.get_staged_sweep(pool, uid_b) == {}
```

- [ ] **Step 4: Run test to verify it fails**

```bash
python -m pytest tests/test_dismantle_undo.py -v
```

Expected: FAIL — `AttributeError: module 'app.repositories.user_tables' has no attribute 'stage_sweep_items'`.

- [ ] **Step 5: Write the implementation**

Append to `backend/app/repositories/user_tables.py`:

```python
# ---------------------------------------------------------------------------
# Dismantle sweeps
# ---------------------------------------------------------------------------


async def stage_sweep_items(pool, user_id: int, rows: list[tuple[str, bool]]) -> None:
    """Record staged items and the lock state each held before the sweep, so
    undo can put it back exactly as it was."""
    if not rows:
        return
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO user_sweep_items (user_id, instance_id, was_locked) "
            "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE was_locked=VALUES(was_locked)",
            [(user_id, instance_id, int(was_locked)) for instance_id, was_locked in rows],
        )
        await conn.commit()


async def get_staged_sweep(pool, user_id: int) -> dict[str, bool]:
    """Return {instance_id: was_locked} for this user's currently staged sweep."""
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT instance_id, was_locked FROM user_sweep_items WHERE user_id=%s",
            (user_id,),
        )
        rows = await cur.fetchall()
    return {instance_id: bool(was_locked) for instance_id, was_locked in rows}


async def clear_sweep_items(pool, user_id: int, instance_ids: list[str]) -> None:
    """Drop staged rows — after a successful undo, or once the user confirms
    the batch was dismantled in-game."""
    if not instance_ids:
        return
    placeholders = ", ".join(["%s"] * len(instance_ids))
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.execute(
            f"DELETE FROM user_sweep_items WHERE user_id=%s AND instance_id IN ({placeholders})",
            (user_id, *instance_ids),
        )
        await conn.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_dismantle_undo.py tests/test_migrate.py -v
```

Expected: PASS. `test_migrate.py` confirms the new migration applies cleanly.

- [ ] **Step 7: Commit**

```bash
git add migrations/0004_dismantle_sweeps.sql app/repositories/user_tables.py tests/conftest.py tests/test_dismantle_undo.py
git commit -m "feat(dismantle): user_sweep_items table and repository"
```

---

### Task 6: Preview endpoint

**Files:**
- Modify: `backend/app/main.py` (request models near the other `BaseModel`s ~line 120; handler after the tags endpoints ~line 388)
- Test: `backend/tests/test_endpoints_dismantle.py`

**Interfaces:**
- Consumes: `classify` (Task 3), `bucket_occupancy`/`plan_batch` (Task 4), `get_tags` (existing).
- Produces: `POST /api/dismantle/preview`, body `{"characterId": str}`, returns
  `{"candidates": [...], "plan": {"staged": [...], "deferred": [...], "perBucket": {...}}, "staged": {...}}`.
  Each candidate is `{instanceId, itemHash, name, icon, power, verdict, source, reason, blocked, overridable}`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_endpoints_dismantle.py`. Model the auth/CSRF/profile-cache setup on `tests/test_endpoints_transfer.py` — **open that file and copy its `login_user` usage, its CSRF header handling, and its cached-profile seeding verbatim** rather than reinventing them.

```python
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


async def test_preview_returns_junk_tagged_weapon_as_a_candidate(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
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


async def test_preview_requires_a_cached_profile(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]


async def test_preview_requires_authentication(app_client):
    resp = await app_client.post("/api/dismantle/preview", json={"characterId": _CHAR_ID})
    assert resp.status_code == 401
```

**Fixtures:** `conftest.py` provides `db_pool` (session), `clean_db` (truncates between tests), `app_client` (built on `clean_db`), and the helper `login_user(app_client, monkeypatch, bungie_id="bm1") -> int`. Use `app_client` + `clean_db` + `monkeypatch` as above; there is no `client` fixture and no `make_user` helper.

The weapon-scoring path needs a cached manifest containing item hash `777` as a weapon (`itemType: 3`). Look at how `tests/test_endpoints_read.py` seeds `manifest_cache` for the weapons endpoint and reuse that helper; the manifest entry must include `inventory.bucketTypeHash = 1498876634` so the batch planner sees a real bucket.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_endpoints_dismantle.py -v
```

Expected: FAIL — 404, the route does not exist.

- [ ] **Step 3: Add the request models**

In `backend/app/main.py`, alongside the other `BaseModel` definitions:

```python
class DismantlePreviewBody(BaseModel):
    characterId: str


class DismantleSweepBody(BaseModel):
    characterId: str
    instanceIds: list[str]
    overrides: list[str] = []


class DismantleUndoBody(BaseModel):
    characterId: str
```

- [ ] **Step 4: Add the imports**

In `backend/app/main.py`, add to the imports:

```python
from app import dismantle as dismantle_logic
from app.bungie_client import set_item_lock_state
```

- [ ] **Step 5: Write the handler**

Add to `backend/app/main.py`, after the tags endpoints:

```python
def _candidate_to_dict(c) -> dict:
    return {
        "instanceId": c.instance_id,
        "itemHash": c.item_hash,
        "name": c.name,
        "icon": c.icon,
        "power": c.power,
        # Serialised as a string so it keys directly into plan.perBucket, whose
        # keys are stringified bucket hashes. Without this the UI cannot tell
        # which bucket a candidate consumes and can only sum free space across
        # all three, overstating what fits for a bucket-concentrated selection.
        "bucketHash": str(c.bucket_hash),
        "verdict": c.verdict,
        "source": c.source,
        "reason": c.reason,
        "blocked": c.blocked,
        "overridable": c.overridable,
    }


async def _sweep_candidates(pool, uid: int, profile: dict) -> list:
    """Score the cached inventory and classify it into sweep candidates."""
    manifest = await load_cached_manifest(pool)
    if manifest is None:
        raise HTTPException(status_code=400, detail="Manifest not loaded yet — open Weapons and Refresh.")
    weapons = assemble_weapons(profile, manifest)
    ratings = await perk_ratings_repo.load(pool, uid)
    scored = score_by_perks(weapons, ratings)
    tags = await user_tables.get_tags(pool, uid)
    return dismantle_logic.classify(scored, tags)


@app.post("/api/dismantle/preview")
async def dismantle_preview(
    body: DismantlePreviewBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    """What a sweep would stage. Reports blocked items rather than hiding them."""
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    candidates = await _sweep_candidates(pool, uid, profile)
    occupancy = dismantle_logic.bucket_occupancy(profile, body.characterId)
    # Plan over the non-blocked candidates so the UI can show what would fit.
    plan = dismantle_logic.plan_batch(
        candidates, [c.instance_id for c in candidates if not c.blocked], occupancy
    )
    return {
        "candidates": [_candidate_to_dict(c) for c in candidates],
        "plan": {"staged": plan.staged, "deferred": plan.deferred,
                 "perBucket": {str(k): v for k, v in plan.per_bucket.items()}},
        "staged": await user_tables.get_staged_sweep(pool, uid),
    }
```

`perk_ratings_repo.load` is the accessor used elsewhere in `main.py` to build a `PerkRatings`; **check the existing weapons endpoint for the exact call and match it** — if it differs, use the existing one.

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/test_endpoints_dismantle.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/test_endpoints_dismantle.py
git commit -m "feat(dismantle): preview endpoint"
```

---

### Task 7: Sweep endpoint

**Files:**
- Modify: `backend/app/main.py` (after the preview handler)
- Test: `backend/tests/test_endpoints_dismantle.py` (append)

**Interfaces:**
- Consumes: `enforce_blocklist`, `plan_batch`, `_move_one` (existing, `main.py:564`), `set_item_lock_state` (Task 2), `stage_sweep_items` (Task 5).
- Produces: `POST /api/dismantle/sweep`, body `{"characterId", "instanceIds", "overrides"}`, returns
  `{"staged": [...], "deferred": [...], "rejected": [...], "failed": [{"instanceId", "error"}]}`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_endpoints_dismantle.py`:

```python
async def test_sweep_transfers_then_unlocks_in_that_order(app_client, clean_db, monkeypatch):
    """The ordering guarantee: an interrupted sweep must never leave an
    unlocked weapon sitting in the vault."""
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)

    uid = await login_user(app_client, clean_db, monkeypatch)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777, locked=True)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    })
    assert resp.status_code == 200
    assert resp.json()["staged"] == ["inst-1"]

    kinds = [c[0] for c in calls]
    assert kinds.index("transfer") < kinds.index("lock")
    assert ("lock", "inst-1", False) in calls


async def test_sweep_records_prior_lock_state_for_undo(app_client, clean_db, monkeypatch):
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)

    uid = await login_user(app_client, clean_db, monkeypatch)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777, locked=True)), 3600)
    await user_tables.set_tag(clean_db, uid, "inst-1", "junk")

    await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    })
    assert await user_tables.get_staged_sweep(clean_db, uid) == {"inst-1": True}


async def test_sweep_rejects_an_instance_the_preview_never_offered(app_client, clean_db, monkeypatch):
    """Server-side re-check: a client cannot smuggle in an arbitrary item."""
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)

    uid = await login_user(app_client, clean_db, monkeypatch)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    # no junk tag, so inst-1 is not a candidate at all

    resp = await app_client.post("/api/dismantle/sweep", json={
        "characterId": _CHAR_ID, "instanceIds": ["inst-1"], "overrides": [],
    })
    assert resp.json()["staged"] == []
    assert resp.json()["rejected"] == [
        {"instanceId": "inst-1", "reason": "not_a_candidate"},
    ]
```

Define the two shared no-op fakes near the top of the file:

```python
async def _noop_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                         access, settings, http_client):
    return None


async def _noop_lock(mtype, instance_id, character_id, state, access, settings, http_client):
    return None
```

These tests also need the Bungie token path faked. `tests/test_endpoints_transfer.py` already monkeypatches `valid_access_token` and `get_profile` — **copy that setup**; without it the sweep will try to reach Bungie.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_endpoints_dismantle.py -k sweep -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Write the handler**

Add to `backend/app/main.py`, after `dismantle_preview`:

Import the lock bitmask rather than redefining it — `app/bungie_client.py` already
owns `_LOCKED_STATE` (added in the Task 3 fix round, alongside `_MASTERWORK_STATE`).
Add it to the existing `from app.bungie_client import (...)` block:

```python
from app.bungie_client import _LOCKED_STATE
```

```python
def _locked_instance_ids(profile: dict) -> set[str]:
    """Instance ids currently locked, read from the item state bitmask."""
    locked = set()
    buckets = [profile.get("profileInventory", {}).get("data", {})]
    buckets += list(profile.get("characterInventories", {}).get("data", {}).values())
    buckets += list(profile.get("characterEquipment", {}).get("data", {}).values())
    for entry in buckets:
        for item in entry.get("items", []):
            instance_id = item.get("itemInstanceId")
            if instance_id and item.get("state", 0) & _LOCKED_STATE:
                locked.add(instance_id)
    return locked


@app.post("/api/dismantle/sweep")
async def dismantle_sweep(
    request: Request,
    body: DismantleSweepBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Stage a batch: move each approved weapon to the character, then unlock it.

    Transfer precedes unlock so an interrupted sweep leaves weapons locked on a
    character rather than unlocked in the vault.
    """
    settings = get_settings()
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    candidates = await _sweep_candidates(pool, uid, profile)

    allowed, rejected = dismantle_logic.enforce_blocklist(
        candidates, body.instanceIds, body.overrides
    )
    occupancy = dismantle_logic.bucket_occupancy(profile, body.characterId)
    plan = dismantle_logic.plan_batch(candidates, allowed, occupancy)

    by_id = {c.instance_id: c for c in candidates}
    locked_now = _locked_instance_ids(profile)
    # Never re-record lock state for an instance already staged. Staging unlocks
    # the item, so a second pass would read it as unlocked and overwrite the true
    # original with False — destroying exactly what undo needs to restore.
    already_staged = await user_tables.get_staged_sweep(pool, uid)
    throttle = request.app.state.throttle
    staged: list[str] = []
    failed: list[dict] = []
    staged_rows: list[tuple[str, bool]] = []

    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(
            pool, uid, settings, client, settings.token_enc_key
        )
        cached_mid = await cache.get(pool, uid, "profile_membership_id")
        if cached_mid != mid:
            raise HTTPException(status_code=400, detail="Your cached inventory is for a "
                                "different account — open Weapons and Refresh, then retry.")
        for instance_id in plan.staged:
            candidate = by_id[instance_id]
            try:
                await _move_one(client, settings, access, mtype, profile, instance_id,
                                candidate.item_hash, body.characterId, False, throttle)
                await throttle.run(lambda iid=instance_id: set_item_lock_state(
                    mtype, iid, body.characterId, False, access, settings, client
                ))
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                failed.append({"instanceId": instance_id, "error": str(exc)})
                continue
            staged.append(instance_id)
            if instance_id not in already_staged:
                staged_rows.append((instance_id, instance_id in locked_now))
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))

    await user_tables.stage_sweep_items(pool, uid, staged_rows)
    await _save_profile(pool, uid, fresh, mid)
    return {"staged": staged, "deferred": plan.deferred,
            "rejected": rejected, "failed": failed}
```

Note the partial-failure contract: a failed item is reported and skipped, the loop continues, and successfully staged items stay staged. There is no automatic rollback.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_endpoints_dismantle.py -v
```

Expected: PASS, all tests in the file.

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_endpoints_dismantle.py
git commit -m "feat(dismantle): sweep endpoint staging weapons to a character"
```

---

### Task 8: Undo endpoint

**Files:**
- Modify: `backend/app/main.py` (after the sweep handler)
- Test: `backend/tests/test_endpoints_dismantle.py` (append)

**Interfaces:**
- Consumes: `get_staged_sweep`, `clear_sweep_items` (Task 5), `set_item_lock_state` (Task 2), `_move_one`.
- Produces: `POST /api/dismantle/undo`, body `{"characterId": str}`, returns `{"restored": [...], "failed": [...]}`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_endpoints_dismantle.py`:

```python
async def test_undo_relocks_then_returns_items_to_the_vault(app_client, clean_db, monkeypatch):
    calls = []

    async def fake_transfer(mtype, item_hash, instance_id, character_id, to_vault,
                            access, settings, http_client):
        calls.append(("transfer", instance_id, to_vault))

    async def fake_lock(mtype, instance_id, character_id, state, access, settings, http_client):
        calls.append(("lock", instance_id, state))

    monkeypatch.setattr("app.main.transfer_item", fake_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", fake_lock)

    uid = await login_user(app_client, clean_db, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await user_tables.stage_sweep_items(clean_db, uid, [("inst-1", True)])

    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID})
    assert resp.status_code == 200
    assert resp.json()["restored"] == ["inst-1"]

    kinds = [c[0] for c in calls]
    assert kinds.index("lock") < kinds.index("transfer")
    assert ("lock", "inst-1", True) in calls


async def test_undo_clears_the_staged_rows(app_client, clean_db, monkeypatch):
    monkeypatch.setattr("app.main.transfer_item", _noop_transfer)
    monkeypatch.setattr("app.main.set_item_lock_state", _noop_lock)

    uid = await login_user(app_client, clean_db, monkeypatch)
    profile = _profile_with("inst-1", 777)
    profile["characterInventories"]["data"][_CHAR_ID]["items"] = [
        {"itemInstanceId": "inst-1", "itemHash": 777, "state": 0, "bucketHash": _KINETIC},
    ]
    profile["profileInventory"]["data"]["items"] = []
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await user_tables.stage_sweep_items(clean_db, uid, [("inst-1", True)])

    await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID})
    assert await user_tables.get_staged_sweep(clean_db, uid) == {}


async def test_undo_with_nothing_staged_is_a_no_op(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, clean_db, monkeypatch)
    await cache_repo.set(clean_db, uid, "profile_cache",
                         json.dumps(_profile_with("inst-1", 777)), 3600)
    resp = await app_client.post("/api/dismantle/undo", json={"characterId": _CHAR_ID})
    assert resp.json() == {"restored": [], "failed": []}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_endpoints_dismantle.py -k undo -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Write the handler**

Add to `backend/app/main.py`, after `dismantle_sweep`:

```python
@app.post("/api/dismantle/undo")
async def dismantle_undo(
    request: Request,
    body: DismantleUndoBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Reverse a staged sweep: restore each item's prior lock state, then send
    it back to the vault. Re-locking first mirrors the sweep's safety ordering."""
    settings = get_settings()
    uid = current_user["user_id"]
    staged = await user_tables.get_staged_sweep(pool, uid)
    if not staged:
        return {"restored": [], "failed": []}

    profile = await _load_profile_or_400(pool, uid)
    item_hashes = _instance_item_hashes(profile)
    throttle = request.app.state.throttle
    restored: list[str] = []
    failed: list[dict] = []

    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(
            pool, uid, settings, client, settings.token_enc_key
        )
        for instance_id, was_locked in staged.items():
            item_hash = item_hashes.get(instance_id)
            if item_hash is None:
                # Already dismantled in-game — nothing to restore.
                restored.append(instance_id)
                continue
            try:
                if was_locked:
                    await throttle.run(lambda iid=instance_id: set_item_lock_state(
                        mtype, iid, body.characterId, True, access, settings, client
                    ))
                await _move_one(client, settings, access, mtype, profile, instance_id,
                                item_hash, "vault", False, throttle)
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                failed.append({"instanceId": instance_id, "error": str(exc)})
                continue
            restored.append(instance_id)
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))

    await user_tables.clear_sweep_items(pool, uid, restored)
    await _save_profile(pool, uid, fresh, mid)
    return {"restored": restored, "failed": failed}
```

Add the helper it needs, next to `_locked_instance_ids`:

```python
def _instance_item_hashes(profile: dict) -> dict[str, int]:
    """Map instance id -> item hash across every inventory bucket."""
    out: dict[str, int] = {}
    buckets = [profile.get("profileInventory", {}).get("data", {})]
    buckets += list(profile.get("characterInventories", {}).get("data", {}).values())
    buckets += list(profile.get("characterEquipment", {}).get("data", {}).values())
    for entry in buckets:
        for item in entry.get("items", []):
            instance_id = item.get("itemInstanceId")
            if instance_id:
                out[instance_id] = item.get("itemHash", 0)
    return out
```

An item missing from the profile is treated as restored rather than failed: the user already dismantled it in-game, which is the whole point of the feature, so the staged row should simply clear.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_endpoints_dismantle.py -v
```

Expected: PASS, all tests in the file.

- [ ] **Step 5: Run the whole backend suite**

```bash
python -m pytest -q
```

Expected: PASS. No pre-existing test may regress.

- [ ] **Step 6: Commit**

```bash
git add app/main.py tests/test_endpoints_dismantle.py
git commit -m "feat(dismantle): undo endpoint restoring lock state and vault location"
```

---

### Task 9: Frontend API client

**Files:**
- Modify: `frontend/src/api.ts` (append; follow the existing `bulkMove` / `saveTag` shape for CSRF headers)

**Interfaces:**
- Consumes: the three endpoints from Tasks 6–8.
- Produces:
  - `type DismantleCandidate = { instanceId, itemHash, name, icon, power, verdict, source, reason, blocked, overridable }`
  - `type BatchPlan = { staged: string[]; deferred: string[]; perBucket: Record<string, { name: string; free: number; staged: number }> }`
  - `fetchDismantlePreview(characterId: string): Promise<{ candidates: DismantleCandidate[]; plan: BatchPlan; staged: Record<string, boolean> }>`
  - `runDismantleSweep(characterId: string, instanceIds: string[], overrides: string[]): Promise<{ staged: string[]; deferred: string[]; rejected: { instanceId: string; reason: string }[]; failed: { instanceId: string; error: string }[] }>`
  - `undoDismantleSweep(characterId: string): Promise<{ restored: string[]; failed: { instanceId: string; error: string }[] }>`

- [ ] **Step 1: Read the existing pattern**

Open `frontend/src/api.ts`. All requests go through the module-private `apiFetch` wrapper, which attaches the `X-CSRF-Token` header on mutating methods and redirects to login on 401. `moveItem` (~line 171) is the closest model: it POSTs JSON and unwraps `detail` from an error body. There is no `postJson` helper — use `apiFetch` directly.

- [ ] **Step 2: Add the types and functions**

Append to `frontend/src/api.ts`:

```ts
export type DismantleCandidate = {
  instanceId: string;
  itemHash: number;
  name: string;
  icon: string;
  power: number;
  verdict: string;
  source: "tagged" | "suggested";
  reason: string;
  blocked: "" | "locked" | "exotic" | "high_verdict" | "equipped";
  overridable: boolean;
};

export type BatchPlan = {
  staged: string[];
  deferred: string[];
  perBucket: Record<string, { name: string; free: number; staged: number }>;
};

async function dismantlePost(url: string, body: unknown): Promise<any> {
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

export async function fetchDismantlePreview(characterId: string): Promise<{
  candidates: DismantleCandidate[];
  plan: BatchPlan;
  staged: Record<string, boolean>;
}> {
  return dismantlePost("/api/dismantle/preview", { characterId });
}

export async function runDismantleSweep(
  characterId: string, instanceIds: string[], overrides: string[],
): Promise<{
  staged: string[];
  deferred: string[];
  rejected: { instanceId: string; reason: string }[];
  failed: { instanceId: string; error: string }[];
}> {
  return dismantlePost("/api/dismantle/sweep", { characterId, instanceIds, overrides });
}

export async function undoDismantleSweep(characterId: string): Promise<{
  restored: string[];
  failed: { instanceId: string; error: string }[];
}> {
  return dismantlePost("/api/dismantle/undo", { characterId });
}
```

- [ ] **Step 3: Verify it compiles**

```bash
cd destiny-weapon-advisor/frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/api.ts
git commit -m "feat(dismantle): frontend API client"
```

---

### Task 10: Dismantle page and navigation

**Files:**
- Create: `frontend/src/components/DismantlePage.tsx`
- Modify: `frontend/src/components/Nav.tsx:5-15`
- Modify: `frontend/src/components/AppShell.tsx:13,45`

**Interfaces:**
- Consumes: everything from Task 9; `fetchCharacters` (existing); `TagChip` from `./TagSelect`.
- Produces: `DismantlePage` component; `"dismantle"` added to the `Section` union.

- [ ] **Step 1: Add the nav section**

In `frontend/src/components/Nav.tsx`, extend the union and the list:

```ts
export type Section = "weapons" | "recommend" | "perks" | "armor" | "builds" | "activities" | "loadouts" | "dismantle";
```

Add to `SECTIONS`, after the `loadouts` entry:

```ts
  { id: "dismantle", label: "Dismantle" },
```

- [ ] **Step 2: Write the page**

Create `frontend/src/components/DismantlePage.tsx`:

```tsx
import { useEffect, useState } from "react";
import {
  DismantleCandidate, BatchPlan,
  fetchCharacters, fetchDismantlePreview, runDismantleSweep, undoDismantleSweep,
} from "../api";
import { Character } from "../types";

const BLOCK_LABEL: Record<string, string> = {
  locked: "Locked in-game",
  exotic: "Exotic",
  high_verdict: "High-value roll",
  equipped: "Equipped — cannot be swept",
};

export function DismantlePage() {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [candidates, setCandidates] = useState<DismantleCandidate[]>([]);
  const [plan, setPlan] = useState<BatchPlan | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [overrides, setOverrides] = useState<Set<string>>(new Set());
  const [stagedCount, setStagedCount] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetchCharacters()
      .then((chars) => {
        setCharacters(chars);
        if (chars.length) setCharacterId(chars[0].characterId);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!characterId) return;
    fetchDismantlePreview(characterId)
      .then((res) => {
        setCandidates(res.candidates);
        setPlan(res.plan);
        setStagedCount(Object.keys(res.staged).length);
        // Junk-tagged start checked; engine suggestions start unchecked.
        setSelected(new Set(
          res.candidates.filter((c) => c.source === "tagged" && !c.blocked)
            .map((c) => c.instanceId),
        ));
      })
      .catch((e) => setError(String(e)));
  }, [characterId]);

  function toggle(set: Set<string>, id: string): Set<string> {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  }

  async function sweep() {
    setBusy(true);
    setError("");
    try {
      const res = await runDismantleSweep(
        characterId, [...selected], [...overrides],
      );
      setStagedCount(res.staged.length);
      if (res.failed.length) {
        setError(`${res.failed.length} item(s) failed: ${res.failed.map((f) => f.error).join("; ")}`);
      }
      const refreshed = await fetchDismantlePreview(characterId);
      setCandidates(refreshed.candidates);
      setPlan(refreshed.plan);
      setSelected(new Set());
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function undo() {
    setBusy(true);
    try {
      await undoDismantleSweep(characterId);
      setStagedCount(0);
      const refreshed = await fetchDismantlePreview(characterId);
      setCandidates(refreshed.candidates);
      setPlan(refreshed.plan);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const selectable = candidates.filter((c) => !c.blocked || (c.overridable && overrides.has(c.instanceId)));
  const fitting = plan ? Object.values(plan.perBucket).reduce((n, b) => n + b.free, 0) : 0;

  return (
    <div>
      <h1 style={{ marginTop: 0 }}>Dismantle Sweep</h1>
      <p style={{ color: "var(--muted)", maxWidth: 680 }}>
        Bungie's API cannot dismantle items. This moves what you pick onto one
        character and unlocks it, so you can dismantle the whole batch from a
        single screen in-game.
      </p>

      <label>
        Character{" "}
        <select value={characterId} onChange={(e) => setCharacterId(e.target.value)}>
          {characters.map((c) => (
            <option key={c.characterId} value={c.characterId}>
              {c.className} — {c.light}
            </option>
          ))}
        </select>
      </label>

      {stagedCount > 0 && (
        <div style={{ margin: "16px 0", padding: 12, border: "1px solid var(--border)", borderRadius: 6 }}>
          <strong>{stagedCount} weapon(s) staged.</strong> Dismantle them in-game,
          then run the next batch.{" "}
          <button onClick={undo} disabled={busy}>Undo sweep</button>
        </div>
      )}

      {plan && (
        <p style={{ color: "var(--muted)" }}>
          {selected.size} selected · about {Math.min(selected.size, fitting)} fit this batch ·{" "}
          {Object.entries(plan.perBucket).map(([k, b]) => `${b.name} ${b.free} free`).join(" · ")}
        </p>
      )}

      {error && <p style={{ color: "crimson" }}>{error}</p>}

      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ textAlign: "left", color: "var(--muted)" }}>
            <th /><th>Weapon</th><th>Power</th><th>Verdict</th><th>Why</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((c) => {
            const overridden = overrides.has(c.instanceId);
            const usable = !c.blocked || (c.overridable && overridden);
            return (
              <tr key={c.instanceId} style={{
                opacity: usable ? 1 : 0.45,
                borderTop: "1px solid var(--border)",
              }}>
                <td>
                  <input
                    type="checkbox"
                    disabled={!usable}
                    checked={selected.has(c.instanceId)}
                    onChange={() => setSelected(toggle(selected, c.instanceId))}
                  />
                </td>
                <td>
                  {c.icon && <img src={`https://www.bungie.net${c.icon}`} alt="" width={28} height={28} />}
                  {" "}{c.name}
                </td>
                <td>{c.power}</td>
                <td>{c.verdict}</td>
                <td>
                  {c.blocked ? (
                    <>
                      <span style={{ color: "crimson", fontWeight: 700 }}>
                        {BLOCK_LABEL[c.blocked] ?? c.blocked}
                      </span>
                      {c.overridable && (
                        <button
                          style={{ marginLeft: 8 }}
                          onClick={() => setOverrides(toggle(overrides, c.instanceId))}
                        >
                          {overridden ? "Cancel override" : "Override"}
                        </button>
                      )}
                    </>
                  ) : c.reason}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {candidates.length === 0 && (
        <p style={{ color: "var(--muted)" }}>
          Nothing to sweep. Tag weapons "junk" on the Weapons tab to queue them here.
        </p>
      )}

      <button
        onClick={sweep}
        disabled={busy || selected.size === 0 || !characterId}
        style={{ marginTop: 16, padding: "8px 18px", fontWeight: 700 }}
      >
        {busy ? "Staging…" : `Stage ${selected.size} weapon(s)`}
      </button>
    </div>
  );
}
```

`Character` is the exported interface in `frontend/src/types.ts:70` — check its field names (`characterId`, `className`, `light`) and adjust the `<select>` and labels if they differ.

- [ ] **Step 3: Wire it into AppShell**

In `frontend/src/components/AppShell.tsx`, add the import:

```tsx
import { DismantlePage } from "./DismantlePage";
```

and the render branch, after the `loadouts` line:

```tsx
        {section === "dismantle" && <DismantlePage />}
```

- [ ] **Step 4: Verify it compiles and builds**

```bash
cd destiny-weapon-advisor/frontend
npx tsc --noEmit && npm run build
```

Expected: no type errors, build succeeds.

- [ ] **Step 5: Run the full test suite**

```bash
cd destiny-weapon-advisor/backend && python -m pytest -q
```

Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/components/DismantlePage.tsx src/components/Nav.tsx src/components/AppShell.tsx
git commit -m "feat(dismantle): sweep page with preview, overrides, and undo"
```

---

## Manual verification

Automated tests never touch a live inventory, so verify once by hand before considering this done:

1. Start the app, sign in, open **Weapons**, and tag two low-value weapons `junk`.
2. Open **Dismantle**. Both appear pre-checked. Any exotic or god-roll appears greyed with a reason.
3. Confirm the batch banner reports free space matching the target character's actual inventory.
4. Stage the batch. In-game, confirm both weapons are on that character and **unlocked**.
5. Press **Undo sweep**. Confirm both return to the vault with their original lock state.
6. Re-stage, dismantle one in-game, then press Undo. The dismantled one should clear without error.
