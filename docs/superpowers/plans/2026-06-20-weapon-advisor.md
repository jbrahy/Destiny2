# Destiny 2 Weapon Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web app that logs into the user's Bungie account, reads every weapon they own with its rolled perks, scores each against community god-roll wishlists, and shows a ranked, filterable view with keep/upgrade/dismantle advice and the reasoning why.

**Architecture:** Python/FastAPI backend serves a React/TypeScript (Vite) frontend. The backend handles Bungie OAuth, fetches the inventory via `GetProfile`, caches the Destiny manifest and the parsed wishlist in SQLite, and runs a pure scoring engine. The frontend renders the scored weapons. No writes to the Bungie account; advice only.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, pydantic-settings, pytest; React 18 + TypeScript + Vite; SQLite (stdlib `sqlite3`).

## Global Constraints

- **No write OAuth scopes.** Only `ReadBasicUserProfile` + `ReadDestinyInventoryAndVault`. The app must never request or call account-modifying endpoints.
- **Secrets only in `.env`** (gitignored). Never commit API key, client_id, or client_secret. A committed `.env.example` documents the keys.
- **OAuth redirect must be HTTPS**, even locally: `https://localhost:8443/callback`. Backend serves HTTPS with a self-signed cert.
- **Bungie API base:** `https://www.bungie.net/Platform`. Every request sends header `X-API-Key: <api_key>`; user-auth requests also send `Authorization: Bearer <token>`.
- **Bungie response envelope:** every response is `{"Response": ..., "ErrorCode": int, "Message": str, ...}`. `ErrorCode == 1` means success; anything else is an error to surface.
- **Python:** type hints + dataclasses; line length 100; tests via `pytest` from `backend/`.
- **Commit after every task** with a Conventional Commits message.

---

## File Structure

```
destiny-weapon-advisor/
  backend/
    pyproject.toml
    .env.example
    app/
      __init__.py
      config.py          # pydantic-settings: loads .env
      models.py          # dataclasses: Verdict, WishlistRoll, Wishlist, OwnedWeapon, Recommendation
      scoring.py         # PURE scoring engine (no I/O)
      wishlist.py        # fetch + parse DIM voltron wishlist
      manifest.py        # download/cache manifest, hash -> item def lookup
      storage.py         # sqlite: tokens + manifest cache + wishlist cache
      bungie_oauth.py    # authorize URL, token exchange, refresh
      bungie_client.py   # memberships, GetProfile, assemble OwnedWeapon list
      certs.py           # self-signed cert generation for local HTTPS
      main.py            # FastAPI app + routes
    tests/
      conftest.py
      fixtures/
        wishlist_sample.txt
        manifest_sample.json
        profile_sample.json
      test_scoring.py
      test_wishlist.py
      test_manifest.py
      test_bungie_client.py
  frontend/
    package.json
    tsconfig.json
    vite.config.ts
    index.html
    src/
      main.tsx
      App.tsx
      api.ts
      types.ts
      components/
        Login.tsx
        Filters.tsx
        WeaponGrid.tsx
        WeaponCard.tsx
        WeaponDetail.tsx
```

**Build order rationale:** The scoring engine (the brain) is pure and testable with fixtures, so it is built first (Task 2) before any network code. Network/manifest/OAuth layers follow, then the integration endpoint, then the UI.

---

## Task 1: Backend scaffold + config + health endpoint + local HTTPS

**Files:**
- Create: `destiny-weapon-advisor/backend/pyproject.toml`
- Create: `destiny-weapon-advisor/backend/.env.example`
- Create: `destiny-weapon-advisor/backend/app/__init__.py` (empty)
- Create: `destiny-weapon-advisor/backend/app/config.py`
- Create: `destiny-weapon-advisor/backend/app/certs.py`
- Create: `destiny-weapon-advisor/backend/app/main.py`
- Create: `destiny-weapon-advisor/backend/tests/conftest.py`
- Test: `destiny-weapon-advisor/backend/tests/test_health.py`

**Interfaces:**
- Produces: `app.config.Settings` (pydantic settings with `bungie_api_key`, `bungie_client_id`, `bungie_client_secret`, `redirect_uri`, `wishlist_url`, `db_path`); `app.config.get_settings() -> Settings`. `app.main.app` (FastAPI instance). `app.certs.ensure_self_signed_cert(cert_dir: str) -> tuple[str, str]` returning `(cert_path, key_path)`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "weapon-advisor-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.29",
  "httpx>=0.27",
  "pydantic-settings>=2.2",
  "cryptography>=42.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Bungie app credentials from https://www.bungie.net/en/Application
BUNGIE_API_KEY=your_api_key_here
BUNGIE_CLIENT_ID=your_oauth_client_id_here
BUNGIE_CLIENT_SECRET=your_oauth_client_secret_here
# Must exactly match the redirect URL registered on the Bungie app
REDIRECT_URI=https://localhost:8443/callback
# Default community wishlist (DIM voltron format)
WISHLIST_URL=https://raw.githubusercontent.com/48klocs/dim-wish-list-sources/master/voltron.txt
DB_PATH=weapon_advisor.sqlite
```

- [ ] **Step 3: Create `app/config.py`**

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    redirect_uri: str = "https://localhost:8443/callback"
    wishlist_url: str = (
        "https://raw.githubusercontent.com/48klocs/"
        "dim-wish-list-sources/master/voltron.txt"
    )
    db_path: str = "weapon_advisor.sqlite"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create `app/certs.py`**

```python
import datetime
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def ensure_self_signed_cert(cert_dir: str) -> tuple[str, str]:
    """Create a self-signed localhost cert if absent. Returns (cert_path, key_path)."""
    os.makedirs(cert_dir, exist_ok=True)
    cert_path = os.path.join(cert_dir, "localhost.crt")
    key_path = os.path.join(cert_dir, "localhost.key")
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
        .not_valid_after(
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=825)
        )
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    with open(key_path, "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path
```

- [ ] **Step 5: Create `app/main.py`**

```python
from fastapi import FastAPI

app = FastAPI(title="Destiny 2 Weapon Advisor")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def run() -> None:
    import uvicorn

    from app.certs import ensure_self_signed_cert

    cert_path, key_path = ensure_self_signed_cert(".certs")
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8443,
        ssl_certfile=cert_path,
        ssl_keyfile=key_path,
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 6: Create `tests/conftest.py`**

```python
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```

- [ ] **Step 7: Write the failing test `tests/test_health.py`**

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 8: Install and run the test**

Run:
```bash
cd destiny-weapon-advisor/backend && pip install -e ".[dev]" && pytest tests/test_health.py -v
```
Expected: PASS (1 passed).

- [ ] **Step 9: Verify HTTPS server boots manually (smoke check)**

Run:
```bash
cd destiny-weapon-advisor/backend && timeout 4 python -m app.main || true
```
Expected: log line `Uvicorn running on https://localhost:8443`, and a `.certs/localhost.crt` file now exists. (`timeout` stops it.)

- [ ] **Step 10: Commit**

```bash
git add destiny-weapon-advisor/backend
git commit -m "feat: backend scaffold with config, health endpoint, local HTTPS"
```

---

## Task 2: Domain models + scoring engine (the brain)

This is the core. Pure functions, no I/O, exhaustively unit-tested with fixtures.

**Files:**
- Create: `destiny-weapon-advisor/backend/app/models.py`
- Create: `destiny-weapon-advisor/backend/app/scoring.py`
- Test: `destiny-weapon-advisor/backend/tests/test_scoring.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `models.Verdict` (str Enum): `GOD_ROLL`, `GOOD`, `UPGRADE`, `NO_DATA`, `DISMANTLE`.
  - `models.WishlistRoll(item_hash: int, perks: frozenset[int], notes: str, is_trash: bool, tags: frozenset[str])`.
  - `models.Wishlist(rolls_by_item: dict[int, list[WishlistRoll]], trash_by_item: dict[int, list[WishlistRoll]])`.
  - `models.OwnedWeapon(instance_id: str, item_hash: int, name: str, weapon_type: str, element: str, is_masterworked: bool, is_random_roll: bool, perks: frozenset[int], location: str)`.
  - `models.Recommendation(weapon: OwnedWeapon, verdict: Verdict, matched_perks: list[int], note: str, tags: list[str], is_duplicate: bool)`.
  - `scoring.score_inventory(weapons: list[OwnedWeapon], wishlist: Wishlist) -> list[Recommendation]`.

- [ ] **Step 1: Create `app/models.py`**

```python
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    GOD_ROLL = "god_roll"
    GOOD = "good"
    UPGRADE = "upgrade"
    NO_DATA = "no_data"
    DISMANTLE = "dismantle"


@dataclass(frozen=True)
class WishlistRoll:
    item_hash: int
    perks: frozenset[int]
    notes: str = ""
    is_trash: bool = False
    tags: frozenset[str] = field(default_factory=frozenset)


@dataclass
class Wishlist:
    rolls_by_item: dict[int, list[WishlistRoll]] = field(default_factory=dict)
    trash_by_item: dict[int, list[WishlistRoll]] = field(default_factory=dict)


@dataclass
class OwnedWeapon:
    instance_id: str
    item_hash: int
    name: str
    weapon_type: str
    element: str
    is_masterworked: bool
    is_random_roll: bool
    perks: frozenset[int]
    location: str


@dataclass
class Recommendation:
    weapon: OwnedWeapon
    verdict: Verdict
    matched_perks: list[int]
    note: str
    tags: list[str]
    is_duplicate: bool
```

- [ ] **Step 2: Write the failing tests `tests/test_scoring.py`**

```python
from app.models import OwnedWeapon, Verdict, Wishlist, WishlistRoll
from app.scoring import score_inventory


def weapon(perks, *, item_hash=100, instance="i1", mw=False, random=True, name="Gun"):
    return OwnedWeapon(
        instance_id=instance,
        item_hash=item_hash,
        name=name,
        weapon_type="Hand Cannon",
        element="Solar",
        is_masterworked=mw,
        is_random_roll=random,
        perks=frozenset(perks),
        location="Vault",
    )


def wl(god=None, trash=None):
    return Wishlist(rolls_by_item=god or {}, trash_by_item=trash or {})


def test_full_match_masterworked_is_god_roll():
    w = weapon([1, 2, 3], mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "great pve", tags=frozenset({"pve"}))]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.GOD_ROLL
    assert set(rec.matched_perks) == {2, 3}
    assert rec.note == "great pve"
    assert rec.tags == ["pve"]


def test_full_match_not_masterworked_is_upgrade():
    w = weapon([1, 2, 3], mw=False)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    assert score_inventory([w], lists)[0].verdict == Verdict.UPGRADE


def test_partial_match_is_good():
    w = weapon([1, 2], mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.GOOD
    assert rec.matched_perks == [2]


def test_no_wishlist_entry_is_no_data():
    w = weapon([1, 2])
    assert score_inventory([w], wl())[0].verdict == Verdict.NO_DATA


def test_trash_roll_is_dismantle():
    w = weapon([7, 8])
    lists = wl(trash={100: [WishlistRoll(100, frozenset({7, 8}), "bad", is_trash=True)]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.DISMANTLE
    assert rec.note == "bad"


def test_random_dupe_with_better_sibling_is_dismantle():
    keeper = weapon([2, 3], instance="keep", mw=True)
    junk = weapon([4, 5], instance="junk")
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    recs = {r.weapon.instance_id: r for r in score_inventory([keeper, junk], lists)}
    assert recs["keep"].verdict == Verdict.GOD_ROLL
    assert recs["junk"].verdict == Verdict.DISMANTLE
    assert recs["keep"].is_duplicate is True


def test_exotic_no_match_stays_no_data_not_dismantle():
    a = weapon([4, 5], instance="a", random=False)
    b = weapon([2, 3], instance="b", random=False, mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    recs = {r.weapon.instance_id: r for r in score_inventory([a, b], lists)}
    assert recs["a"].verdict == Verdict.NO_DATA
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.scoring'`.

- [ ] **Step 4: Create `app/scoring.py`**

```python
from app.models import OwnedWeapon, Recommendation, Verdict, Wishlist, WishlistRoll


def _best_god_match(weapon: OwnedWeapon, rolls: list[WishlistRoll]):
    """Return (roll, matched_perks) for the strongest match, or (None, [])."""
    best_roll = None
    best_matched: list[int] = []
    best_full = False
    for roll in rolls:
        matched = weapon.perks & roll.perks
        if not matched:
            continue
        is_full = roll.perks <= weapon.perks
        if is_full and not best_full:
            best_roll, best_matched, best_full = roll, sorted(matched), True
        elif is_full and best_full and len(matched) > len(best_matched):
            best_roll, best_matched = roll, sorted(matched)
        elif not best_full and len(matched) > len(best_matched):
            best_roll, best_matched = roll, sorted(matched)
    return best_roll, best_matched, best_full


def _trash_match(weapon: OwnedWeapon, rolls: list[WishlistRoll]):
    for roll in rolls:
        if roll.perks and roll.perks <= weapon.perks:
            return roll
    return None


def score_inventory(weapons: list[OwnedWeapon], wishlist: Wishlist) -> list[Recommendation]:
    counts: dict[int, int] = {}
    for w in weapons:
        counts[w.item_hash] = counts.get(w.item_hash, 0) + 1

    # Pass 1: base verdicts.
    base: list[Recommendation] = []
    for w in weapons:
        is_dupe = counts[w.item_hash] > 1
        trash = _trash_match(w, wishlist.trash_by_item.get(w.item_hash, []))
        if trash is not None:
            base.append(Recommendation(w, Verdict.DISMANTLE, sorted(trash.perks),
                                       trash.notes, sorted(trash.tags), is_dupe))
            continue
        roll, matched, full = _best_god_match(w, wishlist.rolls_by_item.get(w.item_hash, []))
        if roll is None:
            base.append(Recommendation(w, Verdict.NO_DATA, [], "", [], is_dupe))
        elif full:
            verdict = Verdict.GOD_ROLL if w.is_masterworked else Verdict.UPGRADE
            base.append(Recommendation(w, verdict, matched, roll.notes, sorted(roll.tags), is_dupe))
        else:
            base.append(Recommendation(w, Verdict.GOOD, matched, roll.notes, sorted(roll.tags), is_dupe))

    # Pass 2: demote random-roll NO_DATA weapons to DISMANTLE when a better
    # sibling of the same item exists.
    keepers = {Verdict.GOD_ROLL, Verdict.UPGRADE, Verdict.GOOD}
    has_keeper = {r.weapon.item_hash for r in base if r.verdict in keepers}
    for rec in base:
        if (
            rec.verdict == Verdict.NO_DATA
            and rec.weapon.is_random_roll
            and rec.weapon.item_hash in has_keeper
        ):
            rec.verdict = Verdict.DISMANTLE
            rec.note = "A better copy of this weapon exists in your inventory."
    return base
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_scoring.py -v`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add destiny-weapon-advisor/backend/app/models.py destiny-weapon-advisor/backend/app/scoring.py destiny-weapon-advisor/backend/tests/test_scoring.py
git commit -m "feat: domain models and pure scoring engine with tests"
```

---

## Task 3: Wishlist fetch + parser

**Files:**
- Create: `destiny-weapon-advisor/backend/app/wishlist.py`
- Create: `destiny-weapon-advisor/backend/tests/fixtures/wishlist_sample.txt`
- Test: `destiny-weapon-advisor/backend/tests/test_wishlist.py`

**Interfaces:**
- Consumes: `models.Wishlist`, `models.WishlistRoll`.
- Produces:
  - `wishlist.parse_wishlist(text: str) -> Wishlist`
  - `async wishlist.fetch_wishlist(url: str, client: httpx.AsyncClient) -> Wishlist`

Wishlist line syntax (DIM voltron): `dimwishlist:item=HASH&perks=P1,P2#notes:some text`. A negative `item` (e.g. `-69420` wildcard or `-1234` specific) marks a trash roll for `abs(HASH)`. `pve`/`pvp`/`gambit` mentioned in the note become tags. Lines not starting with `dimwishlist:` are ignored.

- [ ] **Step 1: Create fixture `tests/fixtures/wishlist_sample.txt`**

```text
title:Sample
// A comment line that must be ignored
dimwishlist:item=100&perks=2,3#notes:great pve roll
dimwishlist:item=100&perks=2#notes:decent pvp option
dimwishlist:item=-100&perks=9,9#notes:trash roll, dismantle
dimwishlist:item=200&perks=5,6
not a wishlist line at all
```

- [ ] **Step 2: Write the failing tests `tests/test_wishlist.py`**

```python
from pathlib import Path

from app.wishlist import parse_wishlist

SAMPLE = (Path(__file__).parent / "fixtures" / "wishlist_sample.txt").read_text()


def test_parses_god_rolls_grouped_by_item():
    wl = parse_wishlist(SAMPLE)
    assert set(wl.rolls_by_item.keys()) == {100, 200}
    rolls = wl.rolls_by_item[100]
    assert frozenset({2, 3}) in {r.perks for r in rolls}


def test_extracts_notes_and_tags():
    wl = parse_wishlist(SAMPLE)
    pve = next(r for r in wl.rolls_by_item[100] if r.perks == frozenset({2, 3}))
    assert pve.notes == "great pve roll"
    assert "pve" in pve.tags
    pvp = next(r for r in wl.rolls_by_item[100] if r.perks == frozenset({2}))
    assert "pvp" in pvp.tags


def test_negative_item_is_trash_keyed_by_absolute_hash():
    wl = parse_wishlist(SAMPLE)
    assert 100 in wl.trash_by_item
    assert wl.trash_by_item[100][0].is_trash is True


def test_roll_without_notes_has_empty_note():
    wl = parse_wishlist(SAMPLE)
    assert wl.rolls_by_item[200][0].notes == ""


def test_ignores_non_wishlist_lines():
    wl = parse_wishlist(SAMPLE)
    total = sum(len(v) for v in wl.rolls_by_item.values())
    total += sum(len(v) for v in wl.trash_by_item.values())
    assert total == 4
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_wishlist.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.wishlist'`.

- [ ] **Step 4: Create `app/wishlist.py`**

```python
import re

import httpx

from app.models import Wishlist, WishlistRoll

_LINE = re.compile(r"^dimwishlist:item=(-?\d+)&perks=([\d,]*)(?:#notes:(.*))?$")
_TAG_WORDS = ("pve", "pvp", "gambit")


def _tags_from_notes(notes: str) -> frozenset[str]:
    low = notes.lower()
    return frozenset(t for t in _TAG_WORDS if t in low)


def parse_wishlist(text: str) -> Wishlist:
    wl = Wishlist()
    for raw in text.splitlines():
        line = raw.strip()
        m = _LINE.match(line)
        if not m:
            continue
        item_raw = int(m.group(1))
        perks = frozenset(int(p) for p in m.group(2).split(",") if p)
        notes = (m.group(3) or "").strip()
        is_trash = item_raw < 0
        item_hash = abs(item_raw)
        roll = WishlistRoll(
            item_hash=item_hash,
            perks=perks,
            notes=notes,
            is_trash=is_trash,
            tags=_tags_from_notes(notes),
        )
        target = wl.trash_by_item if is_trash else wl.rolls_by_item
        target.setdefault(item_hash, []).append(roll)
    return wl


async def fetch_wishlist(url: str, client: httpx.AsyncClient) -> Wishlist:
    resp = await client.get(url, timeout=60.0)
    resp.raise_for_status()
    return parse_wishlist(resp.text)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_wishlist.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add destiny-weapon-advisor/backend/app/wishlist.py destiny-weapon-advisor/backend/tests/test_wishlist.py destiny-weapon-advisor/backend/tests/fixtures/wishlist_sample.txt
git commit -m "feat: DIM wishlist fetch and parser"
```

---

## Task 4: Manifest store

The manifest maps item/perk hashes to definitions. We download only `DestinyInventoryItemDefinition` (covers weapons AND perk/plug items, since plugs are items), cache it as JSON in SQLite keyed by manifest version, and expose lookups.

**Files:**
- Create: `destiny-weapon-advisor/backend/app/storage.py`
- Create: `destiny-weapon-advisor/backend/app/manifest.py`
- Create: `destiny-weapon-advisor/backend/tests/fixtures/manifest_sample.json`
- Test: `destiny-weapon-advisor/backend/tests/test_manifest.py`

**Interfaces:**
- Consumes: `config.Settings`.
- Produces:
  - `storage.get_conn(db_path: str) -> sqlite3.Connection` (creates tables `kv(key TEXT PRIMARY KEY, value TEXT)` and `tokens(id INTEGER PRIMARY KEY CHECK (id=1), access_token TEXT, refresh_token TEXT, expires_at REAL, membership_type INTEGER, membership_id TEXT)`).
  - `storage.kv_get(conn, key) -> str | None`, `storage.kv_set(conn, key, value) -> None`.
  - `manifest.Manifest` wrapping `items: dict[int, dict]` with `name(hash) -> str`, `item_type(hash) -> str`, `tier_type(hash) -> int`, `is_weapon(hash) -> bool`.
  - `async manifest.load_manifest(client, conn) -> Manifest` (downloads+caches if version changed; else loads from cache).

- [ ] **Step 1: Create fixture `tests/fixtures/manifest_sample.json`**

```json
{
  "100": {"displayProperties": {"name": "Fatebringer"}, "itemType": 3, "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 5}, "defaultDamageType": 3},
  "2": {"displayProperties": {"name": "Explosive Payload"}, "itemType": 19, "itemTypeDisplayName": "Trait", "inventory": {"tierType": 2}},
  "999": {"displayProperties": {"name": "Hawkmoon"}, "itemType": 3, "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 6}, "defaultDamageType": 1}
}
```

- [ ] **Step 2: Create `app/storage.py`**

```python
import sqlite3


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tokens ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), "
        "access_token TEXT, refresh_token TEXT, expires_at REAL, "
        "membership_type INTEGER, membership_id TEXT)"
    )
    conn.commit()
    return conn


def kv_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
```

- [ ] **Step 3: Write the failing tests `tests/test_manifest.py`**

```python
import json
from pathlib import Path

from app.manifest import Manifest

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "manifest_sample.json").read_text())


def test_name_lookup():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.name(100) == "Fatebringer"
    assert m.name(2) == "Explosive Payload"


def test_is_weapon_true_only_for_item_type_3():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.is_weapon(100) is True
    assert m.is_weapon(2) is False


def test_tier_type_distinguishes_legendary_from_exotic():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.tier_type(100) == 5
    assert m.tier_type(999) == 6


def test_item_type_display_name():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.item_type(100) == "Hand Cannon"


def test_unknown_hash_name_is_safe():
    m = Manifest(items={})
    assert m.name(123) == "Unknown (123)"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.manifest'`.

- [ ] **Step 5: Create `app/manifest.py`**

```python
import json
import sqlite3
from dataclasses import dataclass, field

import httpx

from app.storage import kv_get, kv_set

_BASE = "https://www.bungie.net"
_API_KEY_HEADER = "X-API-Key"


@dataclass
class Manifest:
    items: dict[int, dict] = field(default_factory=dict)

    def _def(self, item_hash: int) -> dict:
        return self.items.get(item_hash, {})

    def name(self, item_hash: int) -> str:
        dp = self._def(item_hash).get("displayProperties", {})
        return dp.get("name") or f"Unknown ({item_hash})"

    def item_type(self, item_hash: int) -> str:
        return self._def(item_hash).get("itemTypeDisplayName", "")

    def tier_type(self, item_hash: int) -> int:
        return self._def(item_hash).get("inventory", {}).get("tierType", 0)

    def is_weapon(self, item_hash: int) -> bool:
        return self._def(item_hash).get("itemType") == 3


async def load_manifest(client: httpx.AsyncClient, conn: sqlite3.Connection) -> Manifest:
    meta = await client.get(f"{_BASE}/Platform/Destiny2/Manifest/")
    meta.raise_for_status()
    data = meta.json()["Response"]
    version = data["version"]
    cached_version = kv_get(conn, "manifest_version")

    if cached_version == version:
        raw = kv_get(conn, "manifest_items")
        if raw:
            return Manifest(items={int(k): v for k, v in json.loads(raw).items()})

    path = data["jsonWorldComponentContentPaths"]["en"]["DestinyInventoryItemDefinition"]
    defs = await client.get(f"{_BASE}{path}", timeout=120.0)
    defs.raise_for_status()
    items = defs.json()
    kv_set(conn, "manifest_items", json.dumps(items))
    kv_set(conn, "manifest_version", version)
    return Manifest(items={int(k): v for k, v in items.items()})
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_manifest.py -v`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add destiny-weapon-advisor/backend/app/storage.py destiny-weapon-advisor/backend/app/manifest.py destiny-weapon-advisor/backend/tests/test_manifest.py destiny-weapon-advisor/backend/tests/fixtures/manifest_sample.json
git commit -m "feat: sqlite storage and manifest store with caching"
```

---

## Task 5: Bungie OAuth flow

**Files:**
- Create: `destiny-weapon-advisor/backend/app/bungie_oauth.py`
- Test: `destiny-weapon-advisor/backend/tests/test_oauth.py`

**Interfaces:**
- Consumes: `config.Settings`.
- Produces:
  - `bungie_oauth.build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str`
  - `async bungie_oauth.exchange_code(code, settings, client) -> dict` returning `{"access_token", "refresh_token", "expires_in", "refresh_expires_in"}`.
  - `async bungie_oauth.refresh_tokens(refresh_token, settings, client) -> dict` (same shape).

- [ ] **Step 1: Write the failing test `tests/test_oauth.py`**

```python
from urllib.parse import parse_qs, urlparse

from app.bungie_oauth import build_authorize_url


def test_authorize_url_has_required_params():
    url = build_authorize_url("my_client", "https://localhost:8443/callback", "xyz")
    parsed = urlparse(url)
    q = parse_qs(parsed.query)
    assert parsed.netloc == "www.bungie.net"
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["my_client"]
    assert q["state"] == ["xyz"]
    assert q["redirect_uri"] == ["https://localhost:8443/callback"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_oauth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.bungie_oauth'`.

- [ ] **Step 3: Create `app/bungie_oauth.py`**

```python
from urllib.parse import urlencode

import httpx

from app.config import Settings

AUTHORIZE_URL = "https://www.bungie.net/en/OAuth/Authorize"
TOKEN_URL = "https://www.bungie.net/Platform/App/OAuth/Token/"


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": redirect_uri,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


async def _post_token(data: dict, settings: Settings, client: httpx.AsyncClient) -> dict:
    resp = await client.post(
        TOKEN_URL,
        data=data,
        auth=(settings.bungie_client_id, settings.bungie_client_secret),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-API-Key": settings.bungie_api_key,
        },
    )
    resp.raise_for_status()
    return resp.json()


async def exchange_code(code: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    return await _post_token(
        {"grant_type": "authorization_code", "code": code}, settings, client
    )


async def refresh_tokens(refresh_token: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    return await _post_token(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}, settings, client
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_oauth.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/backend/app/bungie_oauth.py destiny-weapon-advisor/backend/tests/test_oauth.py
git commit -m "feat: Bungie OAuth authorize URL and token exchange/refresh"
```

---

## Task 6: Bungie API client + profile-to-weapons assembler

**Files:**
- Create: `destiny-weapon-advisor/backend/app/bungie_client.py`
- Create: `destiny-weapon-advisor/backend/tests/fixtures/profile_sample.json`
- Test: `destiny-weapon-advisor/backend/tests/test_bungie_client.py`

**Interfaces:**
- Consumes: `models.OwnedWeapon`, `manifest.Manifest`.
- Produces:
  - `bungie_client.DAMAGE_TYPES: dict[int, str]` (1 Kinetic, 2 Arc, 3 Solar, 4 Void, 6 Stasis, 7 Strand).
  - `bungie_client.PROFILE_COMPONENTS = "102,201,205,300,302,305,310"`.
  - `bungie_client.assemble_weapons(profile: dict, manifest: Manifest) -> list[OwnedWeapon]` — pure; turns a `GetProfile` response's `Response` object into weapons.
  - `async bungie_client.get_memberships(access_token, settings, client) -> dict`.
  - `async bungie_client.get_profile(membership_type, membership_id, access_token, settings, client) -> dict`.

The `state` bitmask flag for Masterwork is `4`. Perk plug hashes come from each instance's `sockets.data[instanceId].sockets[*].plugHash`. Item location/character is taken from which inventory bucket the item came in; for MVP we tag vault items "Vault" and character items with the character id.

- [ ] **Step 1: Create fixture `tests/fixtures/profile_sample.json`**

This mirrors the shape of a real `GetProfile` `Response` with two instances of item 100 (one masterworked god roll, one junk) and one exotic 999.

```json
{
  "profileInventory": {"data": {"items": [
    {"itemHash": 100, "itemInstanceId": "i1", "state": 4},
    {"itemHash": 100, "itemInstanceId": "i2", "state": 0},
    {"itemHash": 999, "itemInstanceId": "i3", "state": 0}
  ]}},
  "characterInventories": {"data": {}},
  "characterEquipment": {"data": {}},
  "itemComponents": {
    "instances": {"data": {
      "i1": {"damageType": 3}, "i2": {"damageType": 3}, "i3": {"damageType": 1}
    }},
    "sockets": {"data": {
      "i1": {"sockets": [{"plugHash": 2}, {"plugHash": 3}, {"plugHash": 50}]},
      "i2": {"sockets": [{"plugHash": 8}, {"plugHash": 9}]},
      "i3": {"sockets": [{"plugHash": 2}, {"plugHash": 3}]}
    }}
  }
}
```

- [ ] **Step 2: Write the failing tests `tests/test_bungie_client.py`**

```python
import json
from pathlib import Path

from app.bungie_client import assemble_weapons
from app.manifest import Manifest

PROFILE = json.loads((Path(__file__).parent / "fixtures" / "profile_sample.json").read_text())
MANIFEST = Manifest(items={
    100: {"displayProperties": {"name": "Fatebringer"}, "itemType": 3,
          "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 5}},
    999: {"displayProperties": {"name": "Hawkmoon"}, "itemType": 3,
          "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 6}},
})


def test_assembles_only_weapons_with_instances():
    weapons = assemble_weapons(PROFILE, MANIFEST)
    assert {w.instance_id for w in weapons} == {"i1", "i2", "i3"}


def test_reads_perks_from_sockets():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].perks == frozenset({2, 3, 50})


def test_masterwork_flag_from_state_bitmask():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].is_masterworked is True
    assert weapons["i2"].is_masterworked is False


def test_random_roll_true_for_legendary_false_for_exotic():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].is_random_roll is True
    assert weapons["i3"].is_random_roll is False


def test_element_mapped_from_damage_type():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].element == "Solar"
    assert weapons["i3"].element == "Kinetic"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_bungie_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.bungie_client'`.

- [ ] **Step 4: Create `app/bungie_client.py`**

```python
import httpx

from app.config import Settings
from app.manifest import Manifest
from app.models import OwnedWeapon

_BASE = "https://www.bungie.net/Platform"
_MASTERWORK_STATE = 4
PROFILE_COMPONENTS = "102,201,205,300,302,305,310"

DAMAGE_TYPES = {1: "Kinetic", 2: "Arc", 3: "Solar", 4: "Void", 6: "Stasis", 7: "Strand"}


def _headers(settings: Settings, access_token: str | None = None) -> dict:
    headers = {"X-API-Key": settings.bungie_api_key}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def assemble_weapons(profile: dict, manifest: Manifest) -> list[OwnedWeapon]:
    instances = profile.get("itemComponents", {}).get("instances", {}).get("data", {})
    sockets = profile.get("itemComponents", {}).get("sockets", {}).get("data", {})

    raw: list[tuple[dict, str]] = []
    pi = profile.get("profileInventory", {}).get("data", {}).get("items", [])
    raw += [(item, "Vault") for item in pi]
    for char_id, bucket in profile.get("characterInventories", {}).get("data", {}).items():
        raw += [(item, char_id) for item in bucket.get("items", [])]
    for char_id, bucket in profile.get("characterEquipment", {}).get("data", {}).items():
        raw += [(item, char_id) for item in bucket.get("items", [])]

    weapons: list[OwnedWeapon] = []
    for item, location in raw:
        instance_id = item.get("itemInstanceId")
        item_hash = item.get("itemHash")
        if not instance_id or not manifest.is_weapon(item_hash):
            continue
        socket_list = sockets.get(instance_id, {}).get("sockets", [])
        perks = frozenset(
            s["plugHash"] for s in socket_list if s.get("plugHash") is not None
        )
        damage = instances.get(instance_id, {}).get("damageType", 0)
        weapons.append(
            OwnedWeapon(
                instance_id=instance_id,
                item_hash=item_hash,
                name=manifest.name(item_hash),
                weapon_type=manifest.item_type(item_hash),
                element=DAMAGE_TYPES.get(damage, "Unknown"),
                is_masterworked=bool(item.get("state", 0) & _MASTERWORK_STATE),
                is_random_roll=manifest.tier_type(item_hash) == 5,
                perks=perks,
                location=location,
            )
        )
    return weapons


async def get_memberships(access_token: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    resp = await client.get(
        f"{_BASE}/User/GetMembershipsForCurrentUser/",
        headers=_headers(settings, access_token),
    )
    resp.raise_for_status()
    return resp.json()["Response"]


async def get_profile(
    membership_type: int,
    membership_id: str,
    access_token: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> dict:
    resp = await client.get(
        f"{_BASE}/Destiny2/{membership_type}/Profile/{membership_id}/",
        params={"components": PROFILE_COMPONENTS},
        headers=_headers(settings, access_token),
    )
    resp.raise_for_status()
    return resp.json()["Response"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_bungie_client.py -v`
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add destiny-weapon-advisor/backend/app/bungie_client.py destiny-weapon-advisor/backend/tests/test_bungie_client.py destiny-weapon-advisor/backend/tests/fixtures/profile_sample.json
git commit -m "feat: Bungie API client and profile-to-weapons assembler"
```

---

## Task 7: Wire it together — OAuth routes + `/api/weapons` endpoint

This task adds the FastAPI routes that drive the real flow and serialize `Recommendation`s to JSON. It reuses everything above.

**Files:**
- Modify: `destiny-weapon-advisor/backend/app/main.py`
- Test: `destiny-weapon-advisor/backend/tests/test_api.py`

**Interfaces:**
- Consumes: all prior modules.
- Produces routes:
  - `GET /api/login` → 307 redirect to Bungie authorize URL (sets a `state`).
  - `GET /callback?code=&state=` → exchanges code, stores tokens + membership, redirects to `/`.
  - `GET /api/weapons` → `{"weapons": [ {instanceId, name, weaponType, element, location, isMasterworked, verdict, matchedPerks: [names], note, tags, isDuplicate} ]}`.
  - `GET /api/status` → `{"authenticated": bool}`.
  - `recommendation_to_dict(rec, manifest) -> dict` (pure helper, perk hashes resolved to names).

- [ ] **Step 1: Write the failing test `tests/test_api.py`**

```python
from app.main import recommendation_to_dict
from app.manifest import Manifest
from app.models import OwnedWeapon, Recommendation, Verdict


def test_recommendation_serialization_resolves_perk_names():
    manifest = Manifest(items={2: {"displayProperties": {"name": "Explosive Payload"}}})
    weapon = OwnedWeapon("i1", 100, "Fatebringer", "Hand Cannon", "Solar",
                         True, True, frozenset({2}), "Vault")
    rec = Recommendation(weapon, Verdict.GOD_ROLL, [2], "great pve", ["pve"], False)
    out = recommendation_to_dict(rec, manifest)
    assert out["name"] == "Fatebringer"
    assert out["verdict"] == "god_roll"
    assert out["matchedPerks"] == ["Explosive Payload"]
    assert out["note"] == "great pve"
    assert out["tags"] == ["pve"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_api.py -v`
Expected: FAIL with `ImportError: cannot import name 'recommendation_to_dict'`.

- [ ] **Step 3: Replace `app/main.py` with the full app**

```python
import secrets
import time

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.bungie_client import assemble_weapons, get_memberships, get_profile
from app.bungie_oauth import build_authorize_url, exchange_code, refresh_tokens
from app.config import get_settings
from app.manifest import Manifest, load_manifest
from app.scoring import score_inventory
from app.storage import get_conn, kv_get, kv_set
from app.wishlist import fetch_wishlist

app = FastAPI(title="Destiny 2 Weapon Advisor")
_states: set[str] = set()


def recommendation_to_dict(rec, manifest: Manifest) -> dict:
    return {
        "instanceId": rec.weapon.instance_id,
        "name": rec.weapon.name,
        "weaponType": rec.weapon.weapon_type,
        "element": rec.weapon.element,
        "location": rec.weapon.location,
        "isMasterworked": rec.weapon.is_masterworked,
        "verdict": rec.verdict.value,
        "matchedPerks": [manifest.name(p) for p in rec.matched_perks],
        "note": rec.note,
        "tags": rec.tags,
        "isDuplicate": rec.is_duplicate,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, bool]:
    conn = get_conn(get_settings().db_path)
    row = conn.execute("SELECT access_token FROM tokens WHERE id = 1").fetchone()
    return {"authenticated": bool(row and row[0])}


@app.get("/api/login")
def login() -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(16)
    _states.add(state)
    url = build_authorize_url(settings.bungie_client_id, settings.redirect_uri, state)
    return RedirectResponse(url, status_code=307)


@app.get("/callback")
async def callback(code: str, state: str) -> RedirectResponse:
    if state not in _states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _states.discard(state)
    settings = get_settings()
    conn = get_conn(settings.db_path)
    async with httpx.AsyncClient() as client:
        tokens = await exchange_code(code, settings, client)
        access = tokens["access_token"]
        memberships = await get_memberships(access, settings, client)
        primary = memberships["destinyMemberships"][0]
    conn.execute("DELETE FROM tokens")
    conn.execute(
        "INSERT INTO tokens (id, access_token, refresh_token, expires_at, "
        "membership_type, membership_id) VALUES (1, ?, ?, ?, ?, ?)",
        (
            access,
            tokens["refresh_token"],
            time.time() + tokens["expires_in"],
            primary["membershipType"],
            primary["membershipId"],
        ),
    )
    conn.commit()
    return RedirectResponse("/", status_code=307)


async def _valid_access_token(settings, conn, client) -> tuple[str, int, str]:
    row = conn.execute(
        "SELECT access_token, refresh_token, expires_at, membership_type, membership_id "
        "FROM tokens WHERE id = 1"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    access, refresh, expires_at, mtype, mid = row
    if time.time() > expires_at - 60:
        tokens = await refresh_tokens(refresh, settings, client)
        access = tokens["access_token"]
        conn.execute(
            "UPDATE tokens SET access_token = ?, refresh_token = ?, expires_at = ? WHERE id = 1",
            (access, tokens["refresh_token"], time.time() + tokens["expires_in"]),
        )
        conn.commit()
    return access, mtype, mid


@app.get("/api/weapons")
async def weapons() -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    async with httpx.AsyncClient(timeout=120.0) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        manifest = await load_manifest(client, conn)
        wishlist = await fetch_wishlist(settings.wishlist_url, client)
        profile = await get_profile(mtype, mid, access, settings, client)
    owned = assemble_weapons(profile, manifest)
    recs = score_inventory(owned, wishlist)
    return {"weapons": [recommendation_to_dict(r, manifest) for r in recs]}


def run() -> None:
    import uvicorn

    from app.certs import ensure_self_signed_cert

    cert_path, key_path = ensure_self_signed_cert(".certs")
    uvicorn.run(
        "app.main:app", host="localhost", port=8443,
        ssl_certfile=cert_path, ssl_keyfile=key_path,
    )


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd destiny-weapon-advisor/backend && pytest tests/test_api.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full backend suite**

Run: `cd destiny-weapon-advisor/backend && pytest -v`
Expected: PASS (all tests across all files).

- [ ] **Step 6: Commit**

```bash
git add destiny-weapon-advisor/backend/app/main.py destiny-weapon-advisor/backend/tests/test_api.py
git commit -m "feat: OAuth routes and /api/weapons endpoint"
```

---

## Task 8: Frontend scaffold + login + API types

**Files:**
- Create: `destiny-weapon-advisor/frontend/package.json`
- Create: `destiny-weapon-advisor/frontend/tsconfig.json`
- Create: `destiny-weapon-advisor/frontend/vite.config.ts`
- Create: `destiny-weapon-advisor/frontend/index.html`
- Create: `destiny-weapon-advisor/frontend/src/main.tsx`
- Create: `destiny-weapon-advisor/frontend/src/types.ts`
- Create: `destiny-weapon-advisor/frontend/src/api.ts`
- Create: `destiny-weapon-advisor/frontend/src/components/Login.tsx`
- Create: `destiny-weapon-advisor/frontend/src/App.tsx`

**Interfaces:**
- Produces: `types.WeaponDto`, `api.fetchStatus()`, `api.fetchWeapons()`, `api.loginUrl`.

The Vite dev server proxies `/api` and `/callback` to the backend so OAuth redirects land correctly.

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "weapon-advisor-frontend",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.3",
    "vite": "^5.3.4"
  }
}
```

- [ ] **Step 2: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create `vite.config.ts`**

```typescript
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "https://localhost:8443", changeOrigin: true, secure: false },
      "/callback": { target: "https://localhost:8443", changeOrigin: true, secure: false },
    },
  },
});
```

- [ ] **Step 4: Create `index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Destiny 2 Weapon Advisor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `src/types.ts`**

```typescript
export type Verdict = "god_roll" | "good" | "upgrade" | "no_data" | "dismantle";

export interface WeaponDto {
  instanceId: string;
  name: string;
  weaponType: string;
  element: string;
  location: string;
  isMasterworked: boolean;
  verdict: Verdict;
  matchedPerks: string[];
  note: string;
  tags: string[];
  isDuplicate: boolean;
}
```

- [ ] **Step 6: Create `src/api.ts`**

```typescript
import { WeaponDto } from "./types";

export const loginUrl = "/api/login";

export async function fetchStatus(): Promise<boolean> {
  const res = await fetch("/api/status");
  const data = await res.json();
  return data.authenticated as boolean;
}

export async function fetchWeapons(): Promise<WeaponDto[]> {
  const res = await fetch("/api/weapons");
  if (!res.ok) throw new Error(`Failed to load weapons (${res.status})`);
  const data = await res.json();
  return data.weapons as WeaponDto[];
}
```

- [ ] **Step 7: Create `src/components/Login.tsx`**

```typescript
import { loginUrl } from "../api";

export function Login() {
  return (
    <div style={{ padding: 40, textAlign: "center" }}>
      <h1>Destiny 2 Weapon Advisor</h1>
      <p>Log in with your Bungie account to analyze your weapons.</p>
      <a href={loginUrl}>
        <button style={{ fontSize: 18, padding: "10px 24px" }}>Login with Bungie</button>
      </a>
    </div>
  );
}
```

- [ ] **Step 8: Create `src/App.tsx`**

```typescript
import { useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { Login } from "./components/Login";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;
  return <div style={{ padding: 40 }}>Authenticated. Weapon view added in Task 9.</div>;
}
```

- [ ] **Step 9: Create `src/main.tsx`**

```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 10: Install and verify the build**

Run:
```bash
cd destiny-weapon-advisor/frontend && npm install && npm run build
```
Expected: build completes with no TypeScript errors and a `dist/` directory is produced.

- [ ] **Step 11: Commit**

```bash
git add destiny-weapon-advisor/frontend
git commit -m "feat: frontend scaffold with login and API client"
```

---

## Task 9: Weapon grid + filters + detail panel

**Files:**
- Create: `destiny-weapon-advisor/frontend/src/components/WeaponCard.tsx`
- Create: `destiny-weapon-advisor/frontend/src/components/Filters.tsx`
- Create: `destiny-weapon-advisor/frontend/src/components/WeaponDetail.tsx`
- Create: `destiny-weapon-advisor/frontend/src/components/WeaponGrid.tsx`
- Modify: `destiny-weapon-advisor/frontend/src/App.tsx`

**Interfaces:**
- Consumes: `types.WeaponDto`, `api.fetchWeapons`.
- Produces: `WeaponGrid` component that loads, filters, sorts, and displays weapons with a detail panel.

- [ ] **Step 1: Create `src/components/WeaponCard.tsx`**

```typescript
import { Verdict, WeaponDto } from "../types";

const BADGE: Record<Verdict, { label: string; color: string }> = {
  god_roll: { label: "God Roll", color: "#2e7d32" },
  upgrade: { label: "Upgrade", color: "#1565c0" },
  good: { label: "Good", color: "#f9a825" },
  no_data: { label: "No Data", color: "#9e9e9e" },
  dismantle: { label: "Dismantle", color: "#c62828" },
};

export function WeaponCard({ w, onClick }: { w: WeaponDto; onClick: () => void }) {
  const badge = BADGE[w.verdict];
  return (
    <div
      onClick={onClick}
      style={{
        border: "1px solid #ddd", borderRadius: 8, padding: 12, cursor: "pointer",
        borderLeft: `6px solid ${badge.color}`,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <strong>{w.name}</strong>
        <span style={{ color: badge.color, fontWeight: 600 }}>{badge.label}</span>
      </div>
      <div style={{ fontSize: 12, color: "#666" }}>
        {w.weaponType} · {w.element} · {w.location}
        {w.isMasterworked ? " · ★" : ""}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `src/components/WeaponDetail.tsx`**

```typescript
import { WeaponDto } from "../types";

export function WeaponDetail({ w, onClose }: { w: WeaponDto; onClose: () => void }) {
  return (
    <div style={{ border: "1px solid #ccc", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      <button onClick={onClose} style={{ float: "right" }}>Close</button>
      <h2>{w.name}</h2>
      <p>{w.weaponType} · {w.element} · {w.location}</p>
      <p><strong>Verdict:</strong> {w.verdict}</p>
      <p><strong>Matched perks:</strong> {w.matchedPerks.join(", ") || "—"}</p>
      <p><strong>Why:</strong> {w.note || "No community note."}</p>
      {w.tags.length > 0 && <p><strong>Tags:</strong> {w.tags.join(", ")}</p>}
    </div>
  );
}
```

- [ ] **Step 3: Create `src/components/Filters.tsx`**

```typescript
import { Verdict } from "../types";

export interface FilterState {
  verdict: Verdict | "all";
  weaponType: string;
  search: string;
}

export function Filters({
  state, types, onChange,
}: {
  state: FilterState;
  types: string[];
  onChange: (s: FilterState) => void;
}) {
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
      <input
        placeholder="Search name…"
        value={state.search}
        onChange={(e) => onChange({ ...state, search: e.target.value })}
      />
      <select
        value={state.verdict}
        onChange={(e) => onChange({ ...state, verdict: e.target.value as FilterState["verdict"] })}
      >
        <option value="all">All verdicts</option>
        <option value="god_roll">God Roll</option>
        <option value="upgrade">Upgrade</option>
        <option value="good">Good</option>
        <option value="no_data">No Data</option>
        <option value="dismantle">Dismantle</option>
      </select>
      <select
        value={state.weaponType}
        onChange={(e) => onChange({ ...state, weaponType: e.target.value })}
      >
        <option value="all">All types</option>
        {types.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
    </div>
  );
}
```

- [ ] **Step 4: Create `src/components/WeaponGrid.tsx`**

```typescript
import { useEffect, useMemo, useState } from "react";
import { fetchWeapons } from "../api";
import { Verdict, WeaponDto } from "../types";
import { FilterState, Filters } from "./Filters";
import { WeaponCard } from "./WeaponCard";
import { WeaponDetail } from "./WeaponDetail";

const ORDER: Record<Verdict, number> = {
  god_roll: 0, upgrade: 1, good: 2, no_data: 3, dismantle: 4,
};

export function WeaponGrid() {
  const [weapons, setWeapons] = useState<WeaponDto[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<WeaponDto | null>(null);
  const [filters, setFilters] = useState<FilterState>({
    verdict: "all", weaponType: "all", search: "",
  });

  useEffect(() => {
    fetchWeapons()
      .then(setWeapons)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const types = useMemo(
    () => Array.from(new Set(weapons.map((w) => w.weaponType))).sort(),
    [weapons],
  );

  const shown = useMemo(() => {
    return weapons
      .filter((w) => filters.verdict === "all" || w.verdict === filters.verdict)
      .filter((w) => filters.weaponType === "all" || w.weaponType === filters.weaponType)
      .filter((w) => w.name.toLowerCase().includes(filters.search.toLowerCase()))
      .sort((a, b) => ORDER[a.verdict] - ORDER[b.verdict] || a.name.localeCompare(b.name));
  }, [weapons, filters]);

  if (loading) return <div>Analyzing your inventory… (first run downloads the manifest)</div>;
  if (error) return <div style={{ color: "#c62828" }}>Error: {error}</div>;

  return (
    <div>
      <Filters state={filters} types={types} onChange={setFilters} />
      {selected && <WeaponDetail w={selected} onClose={() => setSelected(null)} />}
      <p style={{ color: "#666" }}>{shown.length} of {weapons.length} weapons</p>
      <div
        style={{
          display: "grid", gap: 8,
          gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
        }}
      >
        {shown.map((w) => (
          <WeaponCard key={w.instanceId} w={w} onClick={() => setSelected(w)} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Update `src/App.tsx` to render the grid when authenticated**

```typescript
import { useEffect, useState } from "react";
import { fetchStatus } from "./api";
import { Login } from "./components/Login";
import { WeaponGrid } from "./components/WeaponGrid";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    fetchStatus().then(setAuthed).catch(() => setAuthed(false));
  }, []);

  if (authed === null) return <div style={{ padding: 40 }}>Loading…</div>;
  if (!authed) return <Login />;
  return (
    <div style={{ padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1>Your Weapons</h1>
      <WeaponGrid />
    </div>
  );
}
```

- [ ] **Step 6: Verify the build**

Run:
```bash
cd destiny-weapon-advisor/frontend && npm run build
```
Expected: build completes with no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add destiny-weapon-advisor/frontend/src
git commit -m "feat: weapon grid with filters and detail panel"
```

---

## Task 10: End-to-end manual verification + setup guide

This task has no automated test — it is the real-account smoke test plus the user-facing setup doc.

**Files:**
- Create: `destiny-weapon-advisor/README.md`

- [ ] **Step 1: Write `README.md` with the full setup walkthrough**

Include, in order:
1. Register an app at `https://www.bungie.net/en/Application`:
   - OAuth Client Type: **Confidential**
   - Redirect URL: `https://localhost:8443/callback` (must match exactly)
   - Scope: **Read your Destiny vault and inventory** + basic profile
   - Copy the API Key, Client ID, Client Secret.
2. Backend: `cd backend && cp .env.example .env`, paste the three secrets, then
   `pip install -e ".[dev]" && python -m app.main`.
3. Frontend: `cd frontend && npm install && npm run dev`.
4. Open `http://localhost:5173`, click **Login with Bungie**, accept the one-time
   self-signed-cert browser warning for `https://localhost:8443`, approve on Bungie.
5. Note: first weapon load downloads the manifest (~tens of MB) and may take a minute.

- [ ] **Step 2: Start the backend**

Run: `cd destiny-weapon-advisor/backend && python -m app.main`
Expected: `Uvicorn running on https://localhost:8443`.

- [ ] **Step 3: Start the frontend (separate terminal)**

Run: `cd destiny-weapon-advisor/frontend && npm run dev`
Expected: `Local: http://localhost:5173/`.

- [ ] **Step 4: Manual end-to-end check**

In a browser:
1. Open `http://localhost:5173` → see the Login screen.
2. Click **Login with Bungie** → accept the cert warning → approve on Bungie → redirected back authenticated.
3. The grid loads and shows weapons with colored verdict badges.
4. Filter by "God Roll" → only god rolls show.
5. Click a weapon → detail panel shows matched perks + the community note.

Expected: all five behaviors work against the real account. If the inventory is empty or perks look wrong, re-check the `components` string and the manifest download.

- [ ] **Step 5: Commit**

```bash
git add destiny-weapon-advisor/README.md
git commit -m "docs: add setup guide and end-to-end verification steps"
```

---

## Self-Review Notes

- **Spec coverage:** OAuth login (Tasks 5,7) · inventory+perks read (Task 6) · manifest hash resolution (Task 4) · wishlist source (Task 3) · scoring engine with the five badges incl. "why" (Task 2) · web UI with sort/filter/detail (Tasks 8,9) · no-write scope constraint (Global Constraints, Task 6 omits write endpoints) · local HTTPS gotcha (Task 1) · error handling: token refresh (Task 7), manifest version check/cache (Task 4), no-data badge (Task 2), wishlist absence (Task 2). All spec sections map to a task.
- **Resolved open items from the spec:** default wishlist = 48klocs voltron.txt (Task 1 `.env.example`); GetProfile components = `102,201,205,300,302,305,310` (Task 6); local cert via the `cryptography` library (Task 1 `certs.py`).
- **Type consistency:** `Verdict`, `OwnedWeapon`, `Wishlist`, `WishlistRoll`, `Recommendation` field names are identical across Tasks 2/3/6/7; the frontend `WeaponDto` matches the keys emitted by `recommendation_to_dict` in Task 7.
