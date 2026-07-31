# Armor Sets & Objective Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give armor a real backend scoring engine — an objective, distribution-aware verdict — and surface which set each piece belongs to and what its bonuses do.

**Architecture:** Two new pure modules (`armor_set_bonuses.py`, `armor_scoring.py`) mirroring `dismantle.py` / `roll_pool.py`, fed by two new manifest tables. Scoring is concentration-first: `focus` = sum of the top 3 stats, because armor rolls archetype-spiky and total stats cannot distinguish a focused 95 from a spread-thin 103. The frontend `rate()` heuristic is deleted; the backend becomes the single source of truth.

**Tech Stack:** Python 3.11 / FastAPI / aiomysql (`pytest` + `pytest-asyncio`), React + TypeScript.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-30-armor-sets-and-scoring-design.md`. Read it first.
- **`focus` = sum of the top 3 stats.** Never total. This is the entire point of the feature.
- **Exotics are ALWAYS a keep** — verdict `exotic`, never scored on focus. Confirmed by the user.
- Pure modules (`armor_set_bonuses.py`, `armor_scoring.py`) import **stdlib + `app.models` only**. No I/O, no FastAPI, no httpx.
- **Thresholds are never hardcoded in Python.** They live in `app/data/armor_scoring_seed.json` and are calibrated against real data in Task 6 — do not invent them earlier.
- Real data facts, verified against the live 452-piece collection: stats are `Health, Melee, Grenade, Super, Class, Weapons`; per-stat caps ~30–40; **`Health` can be negative (-2)**; some pieces total **0**. Both edge cases need tests.
- Backend tests run from `destiny-weapon-advisor/backend/` and need MySQL on 127.0.0.1:3307 (Docker container `destiny-mysql`).
- **The full backend suite is pre-existing broken** (~67 failures, cross-file async event-loop pollution, reproduced with all feature files excluded). Validate **per-file**. Never run bare `pytest` and report its failures as yours.
- Surgical changes: every changed line traces to this plan. Do not refactor adjacent code.
- The repo may have uncommitted work by the user. `git add` only the exact paths in each commit step.

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/manifest.py` | *(modify)* download/cache `DestinyEquipableItemSetDefinition` + `DestinySandboxPerkDefinition`; accessors |
| `backend/app/armor_set_bonuses.py` | **new, pure** — item→set index, membership, bonuses, equipped counts |
| `backend/app/armor_scoring.py` | **new, pure** — `focus`, `waste`, verdict |
| `backend/app/data/armor_scoring_seed.json` | **new** — editable thresholds |
| `backend/app/models.py` | *(modify)* `ArmorVerdict` enum; `ArmorPiece.set_name`, `set_hash` |
| `backend/app/bungie_client.py` | *(modify)* populate set fields in `assemble_armor` |
| `backend/app/main.py` | *(modify)* `_armor_to_dict` gains verdict/focus/waste/set fields |
| `backend/app/config.py` | *(modify)* `user_cache_ttl_seconds` 300 → 1800 |
| `backend/scripts/calibrate_armor_bands.py` | **new** — read-only distribution report |
| `frontend/src/types.ts` | *(modify)* `ArmorPiece` DTO fields |
| `frontend/src/components/ArmorList.tsx` | *(modify)* consume backend verdict; **delete `rate()`** |

---

### Task 1: Manifest downloads the set tables

**Files:**
- Modify: `backend/app/manifest.py`
- Test: `backend/tests/test_manifest.py`, `backend/tests/test_manifest_cache.py`

**Interfaces:**
- Consumes: existing `Manifest` dataclass (already has `items`, `stats`, `plug_sets`).
- Produces: `Manifest.item_sets: dict[int, dict]`, `Manifest.sandbox_perks: dict[int, dict]`;
  `Manifest.set_items(set_hash) -> list[int]`, `Manifest.set_perks(set_hash) -> list[dict]`,
  `Manifest.perk_text(perk_hash) -> tuple[str, str]` (name, description).

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_manifest.py`:

```python
# ---------------------------------------------------------------------------
# Armor sets — DestinyEquipableItemSetDefinition + DestinySandboxPerkDefinition.
# Verified shape: setItems is a list of item hashes; setPerks is a list of
# {requiredSetCount, sandboxPerkHash}.
# ---------------------------------------------------------------------------

_ITEM_SETS = {
    900: {
        "displayProperties": {"name": "Techsec"},
        "setItems": [10, 11, 12],
        "setPerks": [
            {"requiredSetCount": 2, "sandboxPerkHash": 7001},
            {"requiredSetCount": 4, "sandboxPerkHash": 7002},
        ],
    },
}
_SANDBOX_PERKS = {
    7001: {"displayProperties": {"name": "Wrecker", "description": "Bonus Kinetic damage."}},
    7002: {"displayProperties": {"name": "Concussive Rounds", "description": "Disorienting burst."}},
}


def test_set_items_returns_member_hashes():
    m = Manifest(item_sets=_ITEM_SETS)
    assert m.set_items(900) == [10, 11, 12]


def test_set_items_of_unknown_set_is_empty():
    assert Manifest(item_sets=_ITEM_SETS).set_items(4242) == []


def test_set_perks_returns_count_and_hash():
    m = Manifest(item_sets=_ITEM_SETS)
    assert m.set_perks(900) == [
        {"requiredSetCount": 2, "sandboxPerkHash": 7001},
        {"requiredSetCount": 4, "sandboxPerkHash": 7002},
    ]


def test_perk_text_resolves_name_and_description():
    m = Manifest(item_sets=_ITEM_SETS, sandbox_perks=_SANDBOX_PERKS)
    assert m.perk_text(7001) == ("Wrecker", "Bonus Kinetic damage.")


def test_perk_text_of_unknown_perk_is_empty_strings():
    assert Manifest().perk_text(4242) == ("", "")


def test_manifest_without_set_tables_degrades_quietly():
    """Caches written before these tables existed must not crash."""
    m = Manifest()
    assert m.set_items(900) == []
    assert m.set_perks(900) == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd destiny-weapon-advisor/backend
python -m pytest tests/test_manifest.py -k "set_items or set_perks or perk_text or set_tables" -v
```

Expected: FAIL — `TypeError: Manifest.__init__() got an unexpected keyword argument 'item_sets'`.

- [ ] **Step 3: Add the fields and accessors**

In `backend/app/manifest.py`, add to the `Manifest` dataclass beside `plug_sets`:

```python
    item_sets: dict[int, dict] = field(default_factory=dict)
    sandbox_perks: dict[int, dict] = field(default_factory=dict)
```

Add accessors next to `plug_set_hashes`:

```python
    def set_items(self, set_hash: int) -> list[int]:
        """Item hashes belonging to an armour set."""
        return self.item_sets.get(set_hash, {}).get("setItems", [])

    def set_perks(self, set_hash: int) -> list[dict]:
        """[{requiredSetCount, sandboxPerkHash}] — the 2pc and 4pc bonuses."""
        return self.item_sets.get(set_hash, {}).get("setPerks", [])

    def perk_text(self, perk_hash: int) -> tuple[str, str]:
        """(name, description) for a sandbox perk; ("", "") when unknown."""
        dp = self.sandbox_perks.get(perk_hash, {}).get("displayProperties", {})
        return dp.get("name", ""), dp.get("description", "")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_manifest.py -v
```

Expected: PASS, including all pre-existing tests in the file.

- [ ] **Step 5: Wire the downloads**

In `load_cached_manifest`, after the plug-set read:

```python
    raw_sets = await cache.manifest_get(pool, "manifest_item_sets")
    raw_perks = await cache.manifest_get(pool, "manifest_sandbox_perks")
```

and pass into the returned `Manifest`:

```python
        item_sets={int(k): v for k, v in json.loads(raw_sets).items()} if raw_sets else {},
        sandbox_perks={int(k): v for k, v in json.loads(raw_perks).items()} if raw_perks else {},
```

In `load_manifest`, extend the cache-hit guard so a cache missing the new tables re-downloads
(same reasoning as plug sets — otherwise sets never appear until Bungie ships a new version):

```python
        raw_sets = await cache.manifest_get(pool, "manifest_item_sets")
        raw_perks = await cache.manifest_get(pool, "manifest_sandbox_perks")
        if raw and raw_stats and raw_plugs and raw_sets and raw_perks:
```

(and include the two new dicts in that early-return `Manifest`).

Then download and persist them alongside the others:

```python
    set_defs = await throttle.run(
        lambda: client.get(f"{_BASE}{paths['DestinyEquipableItemSetDefinition']}", timeout=120.0)
    )
    set_defs.raise_for_status()
    item_sets = set_defs.json()
    perk_defs = await throttle.run(
        lambda: client.get(f"{_BASE}{paths['DestinySandboxPerkDefinition']}", timeout=120.0)
    )
    perk_defs.raise_for_status()
    sandbox_perks = perk_defs.json()
    await cache.manifest_set(pool, "manifest_item_sets", json.dumps(item_sets), version)
    await cache.manifest_set(pool, "manifest_sandbox_perks", json.dumps(sandbox_perks), version)
```

and add both to the final returned `Manifest`.

- [ ] **Step 6: Update the cache tests**

In `backend/tests/test_manifest_cache.py`, add the two paths to `_META_PAYLOAD`:

```python
                "DestinyEquipableItemSetDefinition": "/common/destiny2_content/json/en/itemsets.json",
                "DestinySandboxPerkDefinition": "/common/destiny2_content/json/en/sandboxperks.json",
```

`test_load_manifest_uses_cache_when_version_matches` must seed the two new cache keys, and its
`FakeClient` needs `"itemsets.json"` and `"sandboxperks.json"` responses for the re-download test.
Add:

```python
async def test_load_manifest_redownloads_when_set_tables_are_missing(clean_db):
    """A cache predating the set tables picks them up on next load."""
    await cache.manifest_set(clean_db, "manifest_items", json.dumps({"1": {}}), "v1")
    await cache.manifest_set(clean_db, "manifest_stats", json.dumps({"2": {}}), "v1")
    await cache.manifest_set(clean_db, "manifest_plugsets", json.dumps({"3": {}}), "v1")
    # no manifest_item_sets / manifest_sandbox_perks

    fake_client = FakeClient({
        "/Platform/Destiny2/Manifest/": _META_PAYLOAD,
        "items.json": {"1": {"displayProperties": {"name": "Fresh"}}},
        "stats.json": {"2": {}},
        "plugsets.json": {"3": {}},
        "itemsets.json": {"900": {"displayProperties": {"name": "Techsec"},
                                  "setItems": [10], "setPerks": []}},
        "sandboxperks.json": {"7001": {"displayProperties": {"name": "Wrecker", "description": "x"}}},
    })

    m = await load_manifest(fake_client, clean_db, Throttle(2))

    assert m.set_items(900) == [10]
    assert m.perk_text(7001)[0] == "Wrecker"
    assert await cache.manifest_get(clean_db, "manifest_item_sets") is not None
```

- [ ] **Step 7: Run both files**

```bash
python -m pytest tests/test_manifest.py tests/test_manifest_cache.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add destiny-weapon-advisor/backend/app/manifest.py \
        destiny-weapon-advisor/backend/tests/test_manifest.py \
        destiny-weapon-advisor/backend/tests/test_manifest_cache.py
git commit -m "feat(manifest): download armour set and sandbox perk definitions"
```

---

### Task 2: Pure set-membership module

**Files:**
- Create: `backend/app/armor_set_bonuses.py`
- Test: `backend/tests/test_armor_set_bonuses.py`

**Interfaces:**
- Consumes: `Manifest.set_items`, `set_perks`, `perk_text` (Task 1).
- Produces:
  - `build_index(manifest) -> dict[int, int]` — item hash → set hash
  - `set_for(item_hash, index, manifest) -> tuple[str, int] | None` — (name, set_hash)
  - `set_bonuses(set_hash, manifest) -> list[dict]` — `[{"count": int, "name": str, "description": str}]`
  - `equipped_set_counts(set_hashes) -> dict[int, int]`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_armor_set_bonuses.py`:

```python
"""Armour set membership and bonuses.

Verified against the live manifest: 56 sets, each with setItems[] and setPerks
of the shape [{requiredSetCount: 2|4, sandboxPerkHash}].

Everything here is pure — no I/O — so membership is cheap to test exhaustively.
"""
from app.armor_set_bonuses import build_index, equipped_set_counts, set_bonuses, set_for
from app.manifest import Manifest

_ITEM_SETS = {
    900: {
        "displayProperties": {"name": "Techsec"},
        "setItems": [10, 11, 12],
        "setPerks": [
            {"requiredSetCount": 2, "sandboxPerkHash": 7001},
            {"requiredSetCount": 4, "sandboxPerkHash": 7002},
        ],
    },
    901: {
        "displayProperties": {"name": "AION Renewal"},
        "setItems": [20, 21],
        "setPerks": [{"requiredSetCount": 2, "sandboxPerkHash": 7003}],
    },
}
_PERKS = {
    7001: {"displayProperties": {"name": "Wrecker", "description": "Bonus Kinetic damage."}},
    7002: {"displayProperties": {"name": "Concussive Rounds", "description": "Disorienting burst."}},
    7003: {"displayProperties": {"name": "Force Converter", "description": "Sprint after RL kills."}},
}


def _manifest() -> Manifest:
    return Manifest(item_sets=_ITEM_SETS, sandbox_perks=_PERKS)


def test_index_maps_every_member_item_to_its_set():
    index = build_index(_manifest())
    assert index[10] == 900
    assert index[12] == 900
    assert index[20] == 901


def test_set_for_returns_name_and_hash():
    m = _manifest()
    assert set_for(11, build_index(m), m) == ("Techsec", 900)


def test_set_for_an_item_in_no_set_is_none():
    m = _manifest()
    assert set_for(999, build_index(m), m) is None


def test_set_bonuses_resolve_count_name_and_description():
    assert set_bonuses(900, _manifest()) == [
        {"count": 2, "name": "Wrecker", "description": "Bonus Kinetic damage."},
        {"count": 4, "name": "Concussive Rounds", "description": "Disorienting burst."},
    ]


def test_set_bonuses_are_sorted_by_required_count():
    """4pc must never be listed before 2pc, whatever order the manifest uses."""
    m = Manifest(item_sets={900: {**_ITEM_SETS[900], "setPerks": [
        {"requiredSetCount": 4, "sandboxPerkHash": 7002},
        {"requiredSetCount": 2, "sandboxPerkHash": 7001},
    ]}}, sandbox_perks=_PERKS)
    assert [b["count"] for b in set_bonuses(900, m)] == [2, 4]


def test_set_bonuses_with_an_unresolvable_perk_still_reports_the_count():
    m = Manifest(item_sets=_ITEM_SETS, sandbox_perks={})
    assert set_bonuses(901, m) == [{"count": 2, "name": "", "description": ""}]


def test_set_bonuses_of_unknown_set_is_empty():
    assert set_bonuses(4242, _manifest()) == []


def test_equipped_set_counts_tallies_by_set():
    assert equipped_set_counts([900, 900, 901, None, 900]) == {900: 3, 901: 1}


def test_equipped_set_counts_ignores_pieces_with_no_set():
    assert equipped_set_counts([None, None]) == {}


def test_manifest_without_set_tables_yields_an_empty_index():
    """Old caches degrade to 'no sets', never a crash."""
    assert build_index(Manifest()) == {}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_armor_set_bonuses.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.armor_set_bonuses'`.

- [ ] **Step 3: Write the implementation**

Create `backend/app/armor_set_bonuses.py`:

```python
"""Armour set membership and set bonuses.

Sets live in DestinyEquipableItemSetDefinition: each names its member item
hashes and its 2-piece / 4-piece bonuses, which point at sandbox perks for the
actual rules text. The app never downloaded either table, so it could not show
which set a piece belonged to or what wearing several of them does.

Pure: stdlib + app.manifest only. No I/O.
"""


def build_index(manifest) -> dict[int, int]:
    """item hash -> set hash, built once per manifest load.

    Returns {} for a manifest cached before the set tables existed, so callers
    degrade to "no sets" rather than crashing.
    """
    index: dict[int, int] = {}
    for set_hash in manifest.item_sets:
        for item_hash in manifest.set_items(set_hash):
            index[item_hash] = set_hash
    return index


def set_for(item_hash: int, index: dict[int, int], manifest) -> tuple[str, int] | None:
    """(set name, set hash) for an item, or None when it belongs to no set."""
    set_hash = index.get(item_hash)
    if set_hash is None:
        return None
    name = manifest.item_sets.get(set_hash, {}).get("displayProperties", {}).get("name", "")
    return name, set_hash


def set_bonuses(set_hash: int, manifest) -> list[dict]:
    """[{count, name, description}] for a set, ordered 2-piece before 4-piece.

    An unresolvable perk still reports its count: knowing a 4-piece bonus
    exists is useful even when its text is missing.
    """
    bonuses = []
    for perk in manifest.set_perks(set_hash):
        name, description = manifest.perk_text(perk.get("sandboxPerkHash"))
        bonuses.append({
            "count": perk.get("requiredSetCount", 0),
            "name": name,
            "description": description,
        })
    bonuses.sort(key=lambda b: b["count"])
    return bonuses


def equipped_set_counts(set_hashes: list[int | None]) -> dict[int, int]:
    """How many pieces of each set are present, so the UI can say '3/4'."""
    counts: dict[int, int] = {}
    for set_hash in set_hashes:
        if set_hash is not None:
            counts[set_hash] = counts.get(set_hash, 0) + 1
    return counts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_armor_set_bonuses.py -v
```

Expected: PASS, 10 tests.

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/backend/app/armor_set_bonuses.py \
        destiny-weapon-advisor/backend/tests/test_armor_set_bonuses.py
git commit -m "feat(armor): pure set membership and bonus resolution"
```

---

### Task 3: Armour pieces carry their set

**Files:**
- Modify: `backend/app/models.py` (`ArmorPiece`)
- Modify: `backend/app/bungie_client.py` (`assemble_armor`)
- Test: `backend/tests/test_bungie_client.py`

**Interfaces:**
- Consumes: `build_index`, `set_for` (Task 2).
- Produces: `ArmorPiece.set_name: str`, `ArmorPiece.set_hash: int | None`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_bungie_client.py`:

```python
def test_assemble_armor_tags_pieces_with_their_set():
    manifest = Manifest(
        items={
            500: {
                "displayProperties": {"name": "Techsec Helm", "icon": "/t.jpg"},
                "itemType": 2, "itemTypeDisplayName": "Helmet",
                "inventory": {"tierType": 5}, "classType": 2,
            },
        },
        item_sets={900: {"displayProperties": {"name": "Techsec"},
                         "setItems": [500], "setPerks": []}},
    )
    profile = {
        "characters": {"data": {}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "a1", "itemHash": 500, "state": 0},
        ]}},
        "itemComponents": {},
    }
    pieces = assemble_armor(profile, manifest)
    assert len(pieces) == 1
    assert pieces[0].set_name == "Techsec"
    assert pieces[0].set_hash == 900


def test_assemble_armor_leaves_setless_pieces_blank():
    manifest = Manifest(items={
        501: {"displayProperties": {"name": "Random Helm"}, "itemType": 2,
              "itemTypeDisplayName": "Helmet", "inventory": {"tierType": 5}, "classType": 2},
    })
    profile = {
        "characters": {"data": {}}, "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "a2", "itemHash": 501, "state": 0}]}},
        "itemComponents": {},
    }
    pieces = assemble_armor(profile, manifest)
    assert pieces[0].set_name == ""
    assert pieces[0].set_hash is None
```

Ensure `assemble_armor` is imported at the top of the file alongside `assemble_weapons`.

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_bungie_client.py -k "set" -v
```

Expected: FAIL — `AttributeError: 'ArmorPiece' object has no attribute 'set_name'`.

- [ ] **Step 3: Add the model fields**

In `backend/app/models.py`, append to `ArmorPiece` (after `equipped: bool = False`, keeping
defaults last):

```python
    set_name: str = ""
    set_hash: int | None = None
```

- [ ] **Step 4: Populate them**

In `backend/app/bungie_client.py`, add the import:

```python
from app.armor_set_bonuses import build_index, set_for
```

In `assemble_armor`, before the `for item, holder, equipped in _gather_items(profile):` loop:

```python
    set_index = build_index(manifest)
```

Inside the `ArmorPiece(...)` constructor call, after `equipped=equipped,`:

```python
                set_name=(set_for(item_hash, set_index, manifest) or ("", None))[0],
                set_hash=(set_for(item_hash, set_index, manifest) or ("", None))[1],
```

Note: build the tuple once rather than calling `set_for` twice — assign
`piece_set = set_for(item_hash, set_index, manifest) or ("", None)` just above the
`pieces.append(` call and use `piece_set[0]` / `piece_set[1]`.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_bungie_client.py tests/test_armor_set_bonuses.py -v
```

Expected: PASS, including all pre-existing tests.

- [ ] **Step 6: Commit**

```bash
git add destiny-weapon-advisor/backend/app/models.py \
        destiny-weapon-advisor/backend/app/bungie_client.py \
        destiny-weapon-advisor/backend/tests/test_bungie_client.py
git commit -m "feat(armor): tag armour pieces with their set"
```

---

### Task 4: Objective scoring

**Files:**
- Create: `backend/app/armor_scoring.py`
- Create: `backend/app/data/armor_scoring_seed.json`
- Modify: `backend/app/models.py` (`ArmorVerdict`)
- Test: `backend/tests/test_armor_scoring.py`

**Interfaces:**
- Consumes: `ArmorPiece` (with `is_exotic`, `stats`).
- Produces:
  - `ArmorVerdict` enum: `EXOTIC="exotic"`, `TOP_ROLL="top_roll"`, `GOOD="good"`, `OK="ok"`, `DISMANTLE="dismantle"`
  - `focus(stats: dict[str, int]) -> int`
  - `waste(stats: dict[str, int]) -> int`
  - `load_bands() -> dict[str, int]`
  - `score_armor(piece, bands) -> ArmorVerdict`

**Threshold values are placeholders in this task and are calibrated in Task 6.** Use
`{"top_roll": 999, "good": 999, "ok": 999}` in the seed file for now so the tests that
matter (ordering, exotics, edge cases) can be written against explicit bands passed in.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_armor_scoring.py`:

```python
"""Objective armour scoring.

THE TEST THAT MATTERS: a spread-thin 103 must rank BELOW a focused 95. Armour
rolls archetype-spiky -- two or three stats at 25-35 and the rest pinned at 5-6
-- so total stats cannot distinguish a great piece from a useless one. That is
the entire reason this module exists.

Pure -- no I/O.
"""
from app.armor_scoring import focus, score_armor, waste
from app.models import ArmorPiece, ArmorVerdict

BANDS = {"top_roll": 80, "good": 65, "ok": 50}


def piece(stats: dict, exotic: bool = False) -> ArmorPiece:
    return ArmorPiece(
        instance_id="i1", item_hash=1, name="Piece", slot="Helmet",
        class_name="Warlock", power=2000, is_exotic=exotic,
        is_masterworked=False, stats=stats, location="Vault",
    )


SPREAD_103 = {"Health": 17, "Melee": 17, "Grenade": 17, "Super": 17, "Class": 17, "Weapons": 18}
FOCUSED_95 = {"Health": 6, "Melee": 30, "Grenade": 6, "Super": 6, "Class": 12, "Weapons": 35}


def test_focus_sums_only_the_top_three_stats():
    assert focus(FOCUSED_95) == 30 + 35 + 12


def test_waste_is_everything_outside_the_top_three():
    assert waste(FOCUSED_95) == sum(FOCUSED_95.values()) - focus(FOCUSED_95)


def test_a_spread_thin_103_ranks_BELOW_a_focused_95():
    """The whole point. Total says the 103 is better; focus says otherwise."""
    assert sum(SPREAD_103.values()) > sum(FOCUSED_95.values())
    assert focus(SPREAD_103) < focus(FOCUSED_95)


def test_exotics_are_always_a_keep_regardless_of_stats():
    junk = {"Health": 1, "Melee": 1, "Grenade": 1, "Super": 1, "Class": 1, "Weapons": 1}
    assert score_armor(piece(junk, exotic=True), BANDS) == ArmorVerdict.EXOTIC


def test_bands_map_focus_to_verdicts():
    assert score_armor(piece({"a": 40, "b": 40, "c": 10}), BANDS) == ArmorVerdict.TOP_ROLL
    assert score_armor(piece({"a": 30, "b": 30, "c": 10}), BANDS) == ArmorVerdict.GOOD
    assert score_armor(piece({"a": 20, "b": 20, "c": 15}), BANDS) == ArmorVerdict.OK
    assert score_armor(piece({"a": 10, "b": 10, "c": 5}), BANDS) == ArmorVerdict.DISMANTLE


def test_band_boundaries_are_inclusive():
    """A piece exactly on a threshold takes the higher band."""
    assert score_armor(piece({"a": 80, "b": 0, "c": 0}), BANDS) == ArmorVerdict.TOP_ROLL
    assert score_armor(piece({"a": 65, "b": 0, "c": 0}), BANDS) == ArmorVerdict.GOOD
    assert score_armor(piece({"a": 50, "b": 0, "c": 0}), BANDS) == ArmorVerdict.OK


def test_negative_stats_do_not_break_scoring():
    """Health really can be -2 on live armour."""
    p = piece({"Health": -2, "Melee": 30, "Grenade": 30, "Super": 5, "Class": 5, "Weapons": 5})
    assert focus(p.stats) == 30 + 30 + 5
    assert score_armor(p, BANDS) == ArmorVerdict.GOOD


def test_a_zero_total_piece_is_dismantle_not_a_crash():
    """Some live pieces carry no stats at all."""
    p = piece({"Health": 0, "Melee": 0, "Grenade": 0})
    assert focus(p.stats) == 0
    assert score_armor(p, BANDS) == ArmorVerdict.DISMANTLE


def test_a_piece_with_no_stats_at_all_is_dismantle():
    assert score_armor(piece({}), BANDS) == ArmorVerdict.DISMANTLE


def test_fewer_than_three_stats_sums_what_exists():
    assert focus({"Melee": 30, "Weapons": 20}) == 50
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_armor_scoring.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.armor_scoring'`.

- [ ] **Step 3: Add the verdict enum**

In `backend/app/models.py`, beside the existing `Verdict`:

```python
class ArmorVerdict(str, Enum):
    """Deliberately separate from the weapon Verdict — "god roll" and
    "masterwork" are weapon vocabulary and would mislead here."""
    EXOTIC = "exotic"
    TOP_ROLL = "top_roll"
    GOOD = "good"
    OK = "ok"
    DISMANTLE = "dismantle"
```

- [ ] **Step 4: Write the seed file**

Create `backend/app/data/armor_scoring_seed.json`:

```json
{
  "_meta": "Focus thresholds for armour verdicts. focus = sum of a piece's top 3 stats. A piece scores the highest band whose threshold it meets or exceeds. CALIBRATED against a real 452-piece collection -- see scripts/calibrate_armor_bands.py before changing.",
  "bands": {
    "top_roll": 999,
    "good": 999,
    "ok": 999
  }
}
```

- [ ] **Step 5: Write the implementation**

Create `backend/app/armor_scoring.py`:

```python
"""Objective armour scoring.

Armour rolls archetype-spiky: two or three stats at 25-35 and the rest pinned
at 5-6. Three pieces all totalling 103 can have wildly different usable output,
so total stats -- what the old frontend heuristic used -- is close to
meaningless. `focus` (the top 3 stats) is what a piece actually gives you.

Judged against fixed thresholds rather than against the player's own best
piece, so a verdict never silently changes as their collection improves.

Pure: stdlib + app.models only.
"""
import json
from pathlib import Path

from app.models import ArmorPiece, ArmorVerdict

_SEED_PATH = Path(__file__).parent / "data" / "armor_scoring_seed.json"


def focus(stats: dict[str, int]) -> int:
    """Sum of the top 3 stats — a piece's usable output.

    Fewer than three stats simply sums what exists; negative values (Health
    really can be -2) sort to the bottom and are excluded by the slice.
    """
    return sum(sorted(stats.values(), reverse=True)[:3])


def waste(stats: dict[str, int]) -> int:
    """Everything outside the top 3 — stat points the archetype threw away."""
    return sum(stats.values()) - focus(stats)


def load_bands() -> dict[str, int]:
    """Focus thresholds, editable in app/data/armor_scoring_seed.json."""
    return json.loads(_SEED_PATH.read_text())["bands"]


def score_armor(piece: ArmorPiece, bands: dict[str, int]) -> ArmorVerdict:
    """Objective verdict for one piece.

    Exotics are always a keep: they are build-defining and cannot be re-rolled,
    so scoring their stat roll would be answering the wrong question.
    """
    if piece.is_exotic:
        return ArmorVerdict.EXOTIC
    value = focus(piece.stats)
    if value >= bands["top_roll"]:
        return ArmorVerdict.TOP_ROLL
    if value >= bands["good"]:
        return ArmorVerdict.GOOD
    if value >= bands["ok"]:
        return ArmorVerdict.OK
    return ArmorVerdict.DISMANTLE
```

- [ ] **Step 6: Run test to verify it passes**

```bash
python -m pytest tests/test_armor_scoring.py -v
```

Expected: PASS, 11 tests.

- [ ] **Step 7: Commit**

```bash
git add destiny-weapon-advisor/backend/app/armor_scoring.py \
        destiny-weapon-advisor/backend/app/data/armor_scoring_seed.json \
        destiny-weapon-advisor/backend/app/models.py \
        destiny-weapon-advisor/backend/tests/test_armor_scoring.py
git commit -m "feat(armor): objective concentration-first scoring"
```

---

### Task 5: Serve verdict and set data

**Files:**
- Modify: `backend/app/main.py` (`_armor_to_dict`, `_compute_weapons` armor branch)
- Test: `backend/tests/test_endpoints_armor.py` (create)

**Interfaces:**
- Consumes: `score_armor`, `focus`, `waste`, `load_bands` (Task 4); `set_bonuses` (Task 2).
- Produces: `/api/armor` items gain `verdict`, `focus`, `waste`, `setName`, `setHash`, `setBonuses`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_endpoints_armor.py`:

```python
"""GET /api/armor carries the backend verdict and set data."""
import json

import pytest

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


async def test_armor_requires_authentication(app_client):
    assert (await app_client.get("/api/armor")).status_code == 401


async def test_armor_items_carry_verdict_focus_and_set(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch)
    await _seed(clean_db, uid)
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_endpoints_armor.py -v
```

Expected: FAIL — `KeyError: 'setName'`.

- [ ] **Step 3: Wire the DTO**

In `backend/app/main.py`, add imports:

```python
from app.armor_scoring import focus as armor_focus, load_bands, score_armor, waste as armor_waste
from app.armor_set_bonuses import set_bonuses
```

`_armor_to_dict` takes the manifest and bands so it can resolve bonuses. Change its signature and
body:

```python
def _armor_to_dict(a, manifest: Manifest, bands: dict[str, int]) -> dict:
    return {
        "instanceId": a.instance_id,
        "itemHash": a.item_hash,
        "name": a.name,
        "slot": a.slot,
        "className": a.class_name,
        "power": a.power,
        "isExotic": a.is_exotic,
        "isMasterworked": a.is_masterworked,
        "stats": a.stats,
        "location": a.location,
        "icon": a.icon,
        "equipped": a.equipped,
        "setName": a.set_name,
        "setHash": a.set_hash,
        "setBonuses": set_bonuses(a.set_hash, manifest) if a.set_hash else [],
        "verdict": score_armor(a, bands).value,
        "focus": armor_focus(a.stats),
        "waste": armor_waste(a.stats),
    }
```

Update the single call site in `_compute_weapons`:

```python
    armor = assemble_armor(profile, manifest)
    bands = load_bands()
    await cache.set(pool, uid, "armor_cache",
                    json.dumps([_armor_to_dict(a, manifest, bands) for a in armor]),
                    settings.user_cache_ttl_seconds)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_endpoints_armor.py -v
```

Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/backend/app/main.py \
        destiny-weapon-advisor/backend/tests/test_endpoints_armor.py
git commit -m "feat(armor): serve verdict, focus and set bonuses from /api/armor"
```

---

### Task 6: Calibrate the bands against real data

**This task is the reason thresholds were left at 999.** Do not skip it, and do not
guess values.

**Files:**
- Create: `backend/scripts/calibrate_armor_bands.py`
- Modify: `backend/app/data/armor_scoring_seed.json`

- [ ] **Step 1: Write the report script**

Create `backend/scripts/calibrate_armor_bands.py`:

```python
"""Read-only focus distribution over a real armour collection.

Verdict bands must carve an actual collection sensibly. Guessing them produces
a scorer that calls half a vault "top roll". Run this, read the percentiles,
then set app/data/armor_scoring_seed.json.

    python -m scripts.calibrate_armor_bands --user 1
"""
import argparse
import asyncio
import json

import aiomysql

from app.armor_scoring import focus
from app.bungie_client import assemble_armor
from app.config import get_settings
from app.manifest import load_cached_manifest


def _pct(values: list[int], p: float) -> int:
    return values[min(int(len(values) * p), len(values) - 1)] if values else 0


async def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", type=int, default=1)
    args = parser.parse_args()

    s = get_settings()
    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=s.db_name, autocommit=True,
    )
    try:
        manifest = await load_cached_manifest(pool)
        if manifest is None:
            print("No cached manifest. Open the Weapons tab, then re-run.")
            return
        async with pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT value FROM user_cache WHERE cache_key='profile_cache' AND user_id=%s",
                (args.user,),
            )
            row = await cur.fetchone()
        if not row:
            print("No cached profile. Open the Weapons tab and Refresh, then re-run.")
            return

        armor = assemble_armor(json.loads(row[0]), manifest)
        legendary = [a for a in armor if not a.is_exotic and a.stats]
        values = sorted(focus(a.stats) for a in legendary)
        print(f"legendary pieces with stats: {len(values)}  (exotics are auto-keeps)")
        print()
        for p in (0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99):
            print(f"   p{int(p * 100):<3} focus = {_pct(values, p)}")
        print(f"   max      focus = {values[-1] if values else 0}")
        print()
        print("Suggested starting bands (tune to taste):")
        print(f'   "top_roll": {_pct(values, 0.90)},   # top ~10%')
        print(f'   "good":     {_pct(values, 0.60)},   # top ~40%')
        print(f'   "ok":       {_pct(values, 0.25)}    # bottom ~25% become dismantle')
    finally:
        pool.close()
        await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: Run it against the real collection**

The profile cache expires; if it reports "No cached profile", ask the user to open the
Weapons tab and hit **Refresh**, then re-run immediately.

```bash
cd destiny-weapon-advisor/backend
python -m scripts.calibrate_armor_bands --user 1
```

- [ ] **Step 3: Set the bands**

Replace the `999` placeholders in `backend/app/data/armor_scoring_seed.json` with the
suggested values from the report. **Sanity-check the split before accepting it:** roughly
10% top roll, 30% good, 35% ok, 25% dismantle. If the numbers put most of the collection in
one band, adjust and re-run.

- [ ] **Step 4: Verify the split**

```bash
python -m pytest tests/test_armor_scoring.py -v
```

Expected: PASS (the tests pass explicit bands, so they are unaffected by the seed values).

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/backend/scripts/calibrate_armor_bands.py \
        destiny-weapon-advisor/backend/app/data/armor_scoring_seed.json
git commit -m "feat(armor): calibrate verdict bands against the real collection"
```

---

### Task 7: Frontend consumes the backend verdict

**Files:**
- Modify: `frontend/src/types.ts` (`ArmorPiece`)
- Modify: `frontend/src/components/ArmorList.tsx` — **delete `rate()`**
- Test: `frontend/src/armorSort.test.ts` (update)

**Interfaces:**
- Consumes: the `/api/armor` fields from Task 5.
- Produces: `ArmorPiece.verdict`, `focus`, `waste`, `setName`, `setHash`, `setBonuses`.

- [ ] **Step 1: Extend the DTO type**

In `frontend/src/types.ts`, add to `ArmorPiece`:

```ts
  verdict?: "exotic" | "top_roll" | "good" | "ok" | "dismantle";
  focus?: number;
  waste?: number;
  setName?: string;
  setHash?: number | null;
  setBonuses?: { count: number; name: string; description: string }[];
```

All optional — cached DTOs written by the old backend lack them for up to one cache TTL.

- [ ] **Step 2: Replace the local rating**

In `frontend/src/components/ArmorList.tsx`:

Delete the `rate()` function and the `Rating` interface's `color` derivation from stats.
Replace with a label/colour map driven by the backend verdict:

```ts
const ARMOR_VERDICT: Record<string, { label: string; color: string; rank: number }> = {
  exotic: { label: "Exotic", color: "#caa000", rank: 0 },
  top_roll: { label: "Top Roll", color: "#2e7d32", rank: 1 },
  good: { label: "Good", color: "#1565c0", rank: 2 },
  ok: { label: "OK", color: "#f9a825", rank: 3 },
  dismantle: { label: "Dismantle?", color: "#c62828", rank: 4 },
};

/** Backend verdict, with a safe fallback for DTOs cached before it existed. */
export function ratingOf(a: ArmorPiece): Rating {
  return ARMOR_VERDICT[a.verdict ?? ""] ?? { label: "—", color: "var(--muted)", rank: 5 };
}
```

Replace `.map((a) => ({ a, r: rate(a, maxBySlot[a.slot] || 0) }))` with
`.map((a) => ({ a, r: ratingOf(a) }))`, and delete the now-unused `maxBySlot` memo.

`compareArmor` is unchanged — it already sorts on `r.rank`.

- [ ] **Step 3: Show the set**

In the armour row, beside the name, add:

```tsx
{a.setName && (
  <span style={{ fontSize: 11, color: "var(--muted)" }} title={
    (a.setBonuses ?? []).map((b) => `${b.count}pc ${b.name}: ${b.description}`).join("\n")
  }>
    {a.setName}
  </span>
)}
```

- [ ] **Step 4: Verify**

```bash
cd destiny-weapon-advisor/frontend
npx tsc --noEmit    # exactly ONE pre-existing error: src/main.tsx(6,35) TS2339
npx vitest run
```

Expected: no new type errors; all tests pass. `armorSort.test.ts` constructs `Rating` objects
directly and is unaffected by the source of the rating.

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/frontend/src/types.ts \
        destiny-weapon-advisor/frontend/src/components/ArmorList.tsx
git commit -m "feat(armor): consume the backend verdict; delete the frontend heuristic"
```

---

### Task 8: Raise the inventory cache TTL

**Files:**
- Modify: `backend/app/config.py:34`

- [ ] **Step 1: Change the value**

```python
    user_cache_ttl_seconds: int = 1800
```

The 300-second expiry caused repeated mid-task failures and is the same root cause that made
the "Move to" controls silently vanish from weapon detail. A Refresh button already exists for
when the user has just played.

- [ ] **Step 2: Verify nothing asserts on 300**

```bash
cd destiny-weapon-advisor/backend
grep -rn "300" tests/test_config.py app/config.py
python -m pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add destiny-weapon-advisor/backend/app/config.py
git commit -m "fix(cache): raise inventory TTL from 5 to 30 minutes"
```

---

## Verification

1. Per-file backend runs (never bare `pytest` — the full suite is pre-existing broken):
   ```bash
   cd destiny-weapon-advisor/backend
   python -m pytest tests/test_armor_scoring.py tests/test_armor_set_bonuses.py \
                    tests/test_manifest.py tests/test_manifest_cache.py \
                    tests/test_bungie_client.py tests/test_endpoints_armor.py -v
   ```
2. Frontend: `npx tsc --noEmit` (one pre-existing error) && `npx vitest run`.
3. **Calibration gate (Task 6).** Inspect the verdict split across the real collection before
   accepting the bands. If it calls most of the vault "top roll", the bands are wrong.
4. Manual: open the Armor tab and confirm set names appear, bonuses show on hover, and a
   focused piece outranks a higher-total spread-thin one.

## Rollout

1. Tasks 1–3 (set foundation) — no scoring change, verdicts provably unchanged. Ship.
2. Tasks 4–6 (scoring + calibration). **This changes every armour rating in the UI**, deliberately.
3. Task 7 (frontend), Task 8 (TTL — independent, one line).

Deploys use the known path: build from clean `HEAD`, `COPYFILE_DISABLE=1 tar`, checksum,
preserve `.env`, skip `pip install -e .`, restart, smoke test.
