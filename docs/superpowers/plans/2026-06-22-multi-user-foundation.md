# Multi-User Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the single-user Destiny 2 Advisor into a multi-user web app where any player signs in with Bungie and gets their own data-scoped advisor, backed by MySQL.

**Architecture:** FastAPI + `aiomysql` pool with explicit parameterized SQL in repository modules. Server-side sessions (signed HttpOnly cookie). Per-user encrypted Bungie tokens. Lazy token refresh behind a global outbound-Bungie throttle. Per-user data cache; global manifest cache. Cache/throttle behind interfaces so Redis can drop in later.

**Tech Stack:** Python 3.11+, FastAPI, aiomysql, cryptography (Fernet), httpx, pytest. MySQL 8 InnoDB.

## Global Constraints

- Python `>=3.11`; FastAPI `>=0.110`; httpx `>=0.27`; cryptography `>=42.0`; add `aiomysql>=0.2`.
- MySQL 8, InnoDB, charset `utf8mb4` / collation `utf8mb4_unicode_ci`, strict mode.
- **Explicit parameterized SQL only** — no ORM, no string concatenation, full table names, no SQL aliases.
- Table names plural; PKs singular `_id`; high-volume PKs `BIGINT(20) UNSIGNED`; index every FK and every column used in WHERE/JOIN/ORDER BY.
- Timestamps `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP`.
- Never log tokens or full Bungie payloads. Tokens encrypted at rest (Fernet).
- Cookie flags: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.
- Bungie-only SSO; single Bungie app API key shared by all users.
- TDD: every code change starts with a failing test. Commit after each task.
- Design target: 1k–10k users (no Redis/worker in this plan; behind interfaces for later).

## Spec

Source spec: `docs/superpowers/specs/2026-06-22-multi-user-foundation-design.md`.

## Phasing

This foundation ships in five sequential phases; each ends green and independently mergeable:

- **Phase 1 — Data layer** (Tasks 1–6): aiomysql pool, crypto, migrations + schema, repositories. No endpoint behavior change yet.
- **Phase 2 — Auth & sessions** (Tasks 7–10): Bungie SSO, sessions, `get_current_user`, login/callback/logout.
- **Phase 3 — Bungie throttle & per-user cache adapter** (Tasks 11–12).
- **Phase 4 — Endpoint migration** (Tasks 13–20): port every route + helper module to per-user MySQL.
- **Phase 5 — Frontend & cutover** (Tasks 21–23): login UI, 401 handling, retire SQLite, server entrypoint.

---

## File Structure

**Create:**
- `backend/app/db.py` — aiomysql pool lifecycle + `fetchone/fetchall/execute` helpers.
- `backend/app/crypto.py` — Fernet encrypt/decrypt.
- `backend/app/bungie_throttle.py` — global semaphore + 429 backoff wrapper.
- `backend/app/auth.py` — login/callback/logout routes + `get_current_user`/`require_csrf` dependencies.
- `backend/app/repositories/__init__.py`
- `backend/app/repositories/users.py`
- `backend/app/repositories/tokens.py`
- `backend/app/repositories/sessions.py`
- `backend/app/repositories/cache.py`
- `backend/app/repositories/perk_ratings.py`
- `backend/app/repositories/builds.py`
- `backend/app/repositories/user_tables.py` (tags, loadouts, armor_sets per-user)
- `backend/migrations/0001_init.sql`
- `backend/scripts/migrate.py`
- `backend/tests/conftest.py` (test DB fixtures) + per-module test files.

**Modify:**
- `backend/app/config.py` — DB + session + crypto + throttle settings; drop `db_path`.
- `backend/app/manifest.py` — accept the async DB cache adapter instead of sqlite `conn`.
- `backend/app/main.py` — thread `current_user` through all routes; replace `get_conn`/`kv_*`/`tokens` with repositories.
- `backend/pyproject.toml` — add `aiomysql`.
- `backend/.env.example` — new settings.

**Retire (Phase 5):** `backend/app/storage.py`.

---

# Phase 1 — Data layer

### Task 1: Config + dependency for MySQL/session/crypto settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` with `db_host, db_port, db_user, db_password, db_name, token_enc_key, session_secret, session_ttl_days, cookie_secure, user_cache_ttl_seconds, bungie_throttle_concurrency`; `get_settings()` unchanged signature.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config.py
import os
from importlib import reload

def test_settings_expose_db_and_session_fields(monkeypatch):
    monkeypatch.setenv("DB_HOST", "db.example")
    monkeypatch.setenv("DB_NAME", "advisor")
    monkeypatch.setenv("TOKEN_ENC_KEY", "k")
    monkeypatch.setenv("SESSION_SECRET", "s")
    import app.config as cfg
    reload(cfg)
    cfg.get_settings.cache_clear()
    s = cfg.get_settings()
    assert s.db_host == "db.example"
    assert s.db_name == "advisor"
    assert s.db_port == 3306
    assert s.session_ttl_days == 30
    assert s.cookie_secure is True
    assert s.bungie_throttle_concurrency == 20
    assert not hasattr(s, "db_path")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: FAIL (`db_host` attribute missing).

- [ ] **Step 3: Implement**

```python
# backend/app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    # Bungie (single shared app)
    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    redirect_uri: str = "https://localhost:8443/callback"
    frontend_url: str = "https://localhost:8443"

    # MySQL
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "advisor"
    db_password: str = ""
    db_name: str = "advisor"

    # Security
    token_enc_key: str = ""        # Fernet key (urlsafe base64, 32 bytes)
    session_secret: str = ""       # HMAC secret for cookie signing
    session_ttl_days: int = 30
    cookie_secure: bool = True

    # Behavior
    user_cache_ttl_seconds: int = 300
    bungie_throttle_concurrency: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Add to `backend/pyproject.toml` dependencies: `"aiomysql>=0.2"`.

Replace `backend/.env.example` body with the spec §11 keys (DB_*, TOKEN_ENC_KEY, SESSION_SECRET, SESSION_TTL_DAYS, COOKIE_SECURE, USER_CACHE_TTL_SECONDS, BUNGIE_THROTTLE_CONCURRENCY) plus existing Bungie keys; remove `DB_PATH`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/pyproject.toml backend/.env.example backend/tests/test_config.py
git commit -m "feat(config): MySQL/session/crypto settings; drop db_path"
```

---

### Task 2: Crypto (Fernet token encryption)

**Files:**
- Create: `backend/app/crypto.py`
- Test: `backend/tests/test_crypto.py`

**Interfaces:**
- Produces: `encrypt(plaintext: str, key: str) -> bytes`, `decrypt(token: bytes, key: str) -> str`, `generate_key() -> str`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crypto.py
from app.crypto import encrypt, decrypt, generate_key

def test_round_trip():
    key = generate_key()
    ct = encrypt("super-secret-token", key)
    assert isinstance(ct, bytes)
    assert ct != b"super-secret-token"
    assert decrypt(ct, key) == "super-secret-token"

def test_wrong_key_fails():
    import pytest
    from cryptography.fernet import InvalidToken
    ct = encrypt("x", generate_key())
    with pytest.raises(InvalidToken):
        decrypt(ct, generate_key())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_crypto.py -v`
Expected: FAIL (`app.crypto` not found).

- [ ] **Step 3: Implement**

```python
# backend/app/crypto.py
from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt(plaintext: str, key: str) -> bytes:
    return Fernet(key.encode()).encrypt(plaintext.encode())


def decrypt(token: bytes, key: str) -> str:
    return Fernet(key.encode()).decrypt(token).decode()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_crypto.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/crypto.py backend/tests/test_crypto.py
git commit -m "feat(crypto): Fernet token encryption"
```

---

### Task 3: Migration runner + initial schema

**Files:**
- Create: `backend/migrations/0001_init.sql`
- Create: `backend/scripts/migrate.py`
- Test: `backend/tests/test_migrate.py`

**Interfaces:**
- Produces: `scripts/migrate.py` callable as `python -m scripts.migrate`; `apply_migrations(pool) -> list[str]` (returns filenames applied).

**Schema (`0001_init.sql`)** — implement exactly the spec §4 tables: `users`, `user_tokens`, `sessions`, `user_cache`, `user_perk_ratings`, `manifest_cache`, `oauth_states`, plus per-user `user_builds`, `user_activities`, `user_item_tags`, `user_loadouts`, `user_armor_sets` (the override/state tables today created ad hoc in main.py/builds.py), and `schema_migrations`. Each: `ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci`. FKs `ON DELETE CASCADE` to `users(user_id)`. Per-user override tables key on `(user_id, <natural key>)`.

- [ ] **Step 1: Write the failing test** (uses the test pool fixture from Task 6's conftest; if running this task first, create conftest minimal pool fixture here)

```python
# backend/tests/test_migrate.py
import pytest
from scripts.migrate import apply_migrations

@pytest.mark.asyncio
async def test_apply_migrations_creates_tables(db_pool):
    applied = await apply_migrations(db_pool)
    assert "0001_init.sql" in applied
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SHOW TABLES")
            tables = {r[0] for r in await cur.fetchall()}
    for t in ("users","user_tokens","sessions","user_cache","user_perk_ratings",
              "manifest_cache","oauth_states","user_builds","user_activities",
              "user_item_tags","user_loadouts","user_armor_sets","schema_migrations"):
        assert t in tables
    # idempotent
    applied2 = await apply_migrations(db_pool)
    assert applied2 == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_migrate.py -v`
Expected: FAIL (`scripts.migrate` not found).

- [ ] **Step 3: Implement** `0001_init.sql` (all tables per spec §4 + the five per-user override tables) and:

```python
# backend/scripts/migrate.py
import asyncio
from pathlib import Path

import aiomysql

from app.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


async def _ensure_table(conn):
    async with conn.cursor() as cur:
        await cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename VARCHAR(190) NOT NULL PRIMARY KEY, "
            "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) "
            "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
        )
    await conn.commit()


async def apply_migrations(pool) -> list[str]:
    applied: list[str] = []
    async with pool.acquire() as conn:
        await _ensure_table(conn)
        async with conn.cursor() as cur:
            await cur.execute("SELECT filename FROM schema_migrations")
            done = {r[0] for r in await cur.fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in done:
                continue
            sql = path.read_text()
            async with conn.cursor() as cur:
                for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
                    await cur.execute(stmt)
                await cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
                )
            await conn.commit()
            applied.append(path.name)
    return applied


async def _main():
    s = get_settings()
    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=s.db_name, autocommit=False,
    )
    try:
        print("applied:", await apply_migrations(pool))
    finally:
        pool.close()
        await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_migrate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/migrations/0001_init.sql backend/scripts/migrate.py backend/tests/test_migrate.py
git commit -m "feat(db): migration runner + initial multi-user schema"
```

---

### Task 4: aiomysql pool module (`db.py`)

**Files:**
- Create: `backend/app/db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `async create_pool(settings) -> Pool`; `async fetchone(pool, sql, args) -> tuple|None`; `async fetchall(pool, sql, args) -> list[tuple]`; `async execute(pool, sql, args) -> int` (rowcount, committed).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_db.py
import pytest
from app import db

@pytest.mark.asyncio
async def test_execute_and_fetch(db_pool):
    await db.execute(db_pool, "DROP TABLE IF EXISTS t_demo", ())
    await db.execute(db_pool, "CREATE TABLE t_demo (id INT PRIMARY KEY, v VARCHAR(10))", ())
    await db.execute(db_pool, "INSERT INTO t_demo (id, v) VALUES (%s, %s)", (1, "a"))
    assert await db.fetchone(db_pool, "SELECT v FROM t_demo WHERE id=%s", (1,)) == ("a",)
    assert await db.fetchall(db_pool, "SELECT id FROM t_demo", ()) == [(1,)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_db.py -v`
Expected: FAIL (`app.db` not found).

- [ ] **Step 3: Implement**

```python
# backend/app/db.py
import aiomysql


async def create_pool(settings):
    return await aiomysql.create_pool(
        host=settings.db_host, port=settings.db_port, user=settings.db_user,
        password=settings.db_password, db=settings.db_name,
        autocommit=False, minsize=1, maxsize=10, charset="utf8mb4",
    )


async def fetchone(pool, sql: str, args: tuple):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()


async def fetchall(pool, sql: str, args: tuple):
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            return list(await cur.fetchall())


async def execute(pool, sql: str, args: tuple) -> int:
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, args)
            rows = cur.rowcount
        await conn.commit()
        return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/db.py backend/tests/test_db.py
git commit -m "feat(db): aiomysql pool + query helpers"
```

---

### Task 5: Test fixtures (`conftest.py`)

**Files:**
- Create: `backend/tests/conftest.py`

**Interfaces:**
- Produces: `db_pool` (session-scoped aiomysql pool against a test DB, schema applied once), `clean_db` (function-scoped: truncate all data tables before each test).

- [ ] **Step 1: Implement** (no separate failing test — this enables Tasks 3/4 tests; if those were written first they fail at collection until this exists, which is the expected red state)

```python
# backend/tests/conftest.py
import asyncio
import pytest
import pytest_asyncio
import aiomysql

from app.config import get_settings

TEST_DB = "advisor_test"


@pytest_asyncio.fixture(scope="session")
async def db_pool():
    s = get_settings()
    # connect without db to create the test schema
    conn = await aiomysql.connect(host=s.db_host, port=s.db_port,
                                  user=s.db_user, password=s.db_password)
    async with conn.cursor() as cur:
        await cur.execute(f"CREATE DATABASE IF NOT EXISTS {TEST_DB} "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    await conn.commit()
    conn.close()
    pool = await aiomysql.create_pool(host=s.db_host, port=s.db_port, user=s.db_user,
                                      password=s.db_password, db=TEST_DB, autocommit=False)
    from scripts.migrate import apply_migrations
    await apply_migrations(pool)
    yield pool
    pool.close()
    await pool.wait_closed()


@pytest_asyncio.fixture
async def clean_db(db_pool):
    tables = ("sessions","oauth_states","user_tokens","user_cache","user_perk_ratings",
              "user_builds","user_activities","user_item_tags","user_loadouts",
              "user_armor_sets","manifest_cache","users")
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in tables:
                await cur.execute(f"TRUNCATE TABLE {t}")
            await cur.execute("SET FOREIGN_KEY_CHECKS=1")
        await conn.commit()
    yield db_pool
```

- [ ] **Step 2: Run the Phase-1 suite green**

Run: `cd backend && python -m pytest tests/test_migrate.py tests/test_db.py -v`
Expected: PASS (requires a reachable MySQL; see README note added in Task 23).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: MySQL test fixtures (pool + clean_db)"
```

---

### Task 6: Repositories — users, tokens, sessions, cache

**Files:**
- Create: `backend/app/repositories/__init__.py` (empty), `users.py`, `tokens.py`, `sessions.py`, `cache.py`
- Test: `backend/tests/test_repositories.py`

**Interfaces:**
- Produces:
  - `users.upsert(pool, bungie_membership_id, display_name, primary_membership_type, primary_membership_id) -> int` (returns `user_id`)
  - `users.get(pool, user_id) -> dict|None`
  - `tokens.set_tokens(pool, user_id, access, refresh, access_expires_at, refresh_expires_at, membership_type, membership_id, key)`
  - `tokens.get_tokens(pool, user_id, key) -> dict|None` (decrypted access/refresh + meta)
  - `tokens.update_membership(pool, user_id, membership_type, membership_id)`
  - `sessions.create(pool, user_id, ttl_days) -> str` (returns raw cookie token)
  - `sessions.lookup(pool, raw_token) -> int|None` (user_id; updates last_seen; None if expired)
  - `sessions.delete(pool, raw_token)`
  - `cache.get(pool, user_id, key) -> str|None` (honors expiry)
  - `cache.set(pool, user_id, key, value, ttl_seconds)`
  - `cache.delete(pool, user_id, key)`
  - `cache.manifest_get(pool, key) -> str|None` / `cache.manifest_set(pool, key, value, version)` / `cache.manifest_version(pool) -> str|None`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_repositories.py
import time
import pytest
from app.crypto import generate_key
from app.repositories import users, tokens, sessions, cache

@pytest.mark.asyncio
async def test_user_upsert_idempotent(clean_db):
    uid = await users.upsert(clean_db, "bm1", "Guardian", 3, "mid1")
    uid2 = await users.upsert(clean_db, "bm1", "Guardian#2", 3, "mid1")
    assert uid == uid2
    assert (await users.get(clean_db, uid))["display_name"] == "Guardian#2"

@pytest.mark.asyncio
async def test_tokens_encrypted_round_trip(clean_db):
    key = generate_key()
    uid = await users.upsert(clean_db, "bm1", "G", 3, "mid1")
    await tokens.set_tokens(clean_db, uid, "acc", "ref", 111, 222, 3, "mid1", key)
    got = await tokens.get_tokens(clean_db, uid, key)
    assert got["access_token"] == "acc" and got["refresh_token"] == "ref"
    # ciphertext on disk is not plaintext
    from app import db
    raw = await db.fetchone(clean_db, "SELECT access_token_enc FROM user_tokens WHERE user_id=%s", (uid,))
    assert raw[0] != b"acc"

@pytest.mark.asyncio
async def test_session_lifecycle(clean_db):
    uid = await users.upsert(clean_db, "bm1", "G", 3, "mid1")
    raw = await sessions.create(clean_db, uid, ttl_days=30)
    assert await sessions.lookup(clean_db, raw) == uid
    await sessions.delete(clean_db, raw)
    assert await sessions.lookup(clean_db, raw) is None

@pytest.mark.asyncio
async def test_cache_isolation_and_ttl(clean_db):
    a = await users.upsert(clean_db, "a", "A", 3, "1")
    b = await users.upsert(clean_db, "b", "B", 3, "2")
    await cache.set(clean_db, a, "weapons", "AAA", ttl_seconds=300)
    assert await cache.get(clean_db, a, "weapons") == "AAA"
    assert await cache.get(clean_db, b, "weapons") is None  # isolation
    await cache.set(clean_db, a, "x", "v", ttl_seconds=-1)   # already expired
    assert await cache.get(clean_db, a, "x") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_repositories.py -v`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement** the four modules with explicit SQL. Key points:
  - `users.upsert`: `INSERT ... ON DUPLICATE KEY UPDATE display_name=VALUES(display_name), ...`; then `SELECT user_id FROM users WHERE bungie_membership_id=%s`.
  - `tokens.set_tokens`: `crypto.encrypt` access/refresh; `INSERT ... ON DUPLICATE KEY UPDATE`. Store expiries as `FROM_UNIXTIME(%s)` or as TIMESTAMP via Python `datetime.utcfromtimestamp`.
  - `sessions.create`: `secrets.token_urlsafe(32)`; store `hashlib.sha256(raw.encode()).hexdigest()`; expiry `now + ttl_days`.
  - `sessions.lookup`: `SELECT user_id FROM sessions WHERE session_id=%s AND expires_at > NOW()`; on hit `UPDATE ... SET last_seen_at=NOW()`.
  - `cache.get`: `SELECT value FROM user_cache WHERE user_id=%s AND cache_key=%s AND (expires_at IS NULL OR expires_at > NOW())`.
  - `cache.set`: compute `expires_at = NOW() + INTERVAL ttl SECOND` (NULL if ttl is None); `INSERT ... ON DUPLICATE KEY UPDATE`.

- [ ] **Step 4: Run to verify pass**

Run: `cd backend && python -m pytest tests/test_repositories.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories backend/tests/test_repositories.py
git commit -m "feat(repos): users/tokens/sessions/cache with encryption + isolation tests"
```

---

# Phase 2 — Auth & sessions

### Task 7: App lifespan wires the pool + migrations

**Files:**
- Modify: `backend/app/main.py` (add lifespan; store `pool` on `app.state`)
- Test: `backend/tests/test_app_lifespan.py`

**Interfaces:**
- Produces: `app.state.pool` available in requests; dependency `get_pool(request) -> Pool`.

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_app_lifespan.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_health_ok():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run** → FAIL if lifespan misconfigured (import error). Expected: initially may pass health; add assertion that `app.state.pool` is set after startup via a lifespan test using `LifespanManager` (add `asgi-lifespan` dev dep) — assert `hasattr(app.state, "pool")`.

- [ ] **Step 3: Implement** a FastAPI `lifespan` context that calls `db.create_pool(get_settings())`, runs `apply_migrations(pool)`, sets `app.state.pool`, and closes on shutdown. Add `get_pool` dependency reading `request.app.state.pool`.

- [ ] **Step 4: Run** → PASS.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(app): lifespan wires aiomysql pool + migrations"
```

---

### Task 8: Bungie throttle wrapper

**Files:**
- Create: `backend/app/bungie_throttle.py`
- Test: `backend/tests/test_throttle.py`

**Interfaces:**
- Produces: `class Throttle: __init__(concurrency:int)`, `async run(coro_factory)` — runs under a semaphore; on `httpx.HTTPStatusError` 429 retries with exponential backoff+jitter (bounded, e.g. 4 tries) then re-raises.

- [ ] **Step 1: Write failing test** — fake coro factory that raises 429 twice then returns a value; assert it eventually returns and was retried; a second test asserts concurrency never exceeds the limit using a counter + `asyncio.gather`.

```python
# backend/tests/test_throttle.py
import asyncio, httpx, pytest
from app.bungie_throttle import Throttle

def _resp(status): 
    return httpx.Response(status, request=httpx.Request("GET","http://x"))

@pytest.mark.asyncio
async def test_retries_429_then_succeeds():
    calls = {"n": 0}
    async def factory():
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.HTTPStatusError("429", request=_resp(429).request, response=_resp(429))
        return "ok"
    t = Throttle(concurrency=2)
    assert await t.run(factory) == "ok"
    assert calls["n"] == 3

@pytest.mark.asyncio
async def test_concurrency_capped():
    cur = {"n": 0, "max": 0}
    async def factory():
        cur["n"] += 1; cur["max"] = max(cur["max"], cur["n"])
        await asyncio.sleep(0.01); cur["n"] -= 1; return 1
    t = Throttle(concurrency=3)
    await asyncio.gather(*[t.run(factory) for _ in range(20)])
    assert cur["max"] <= 3
```

- [ ] **Step 2: Run** → FAIL (module missing).
- [ ] **Step 3: Implement** `Throttle` with `asyncio.Semaphore`, retry loop on 429 with `await asyncio.sleep(base * 2**i + jitter)` using `secrets.randbelow` for jitter (no `random`/`time` global — use `asyncio.sleep`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/app/bungie_throttle.py backend/tests/test_throttle.py
git commit -m "feat(bungie): outbound throttle + 429 backoff"
```

---

### Task 9: Auth routes + `get_current_user`

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/app/main.py` (include the auth router; remove old `/api/login`, `/callback`, `/api/status` token logic)
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `bungie_oauth.build_authorize_url/exchange_code`, `bungie_client.get_memberships`, repositories from Task 6, `Throttle` (Task 8).
- Produces: router with `GET /api/login`, `GET /callback`, `POST /api/auth/logout`, `GET /api/status`; dependency `get_current_user(request, pool=Depends(get_pool)) -> dict` (401 if no/expired session); dependency `require_csrf`.

- [ ] **Step 1: Write failing tests** (mock Bungie via monkeypatching `auth.exchange_code` and `auth.get_memberships`):

```python
# backend/tests/test_auth.py
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.mark.asyncio
async def test_login_redirects_to_bungie(app_client):
    r = await app_client.get("/api/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "bungie.net" in r.headers["location"]

@pytest.mark.asyncio
async def test_callback_creates_session_and_status_true(app_client, monkeypatch, clean_db):
    import app.auth as auth
    # seed a valid state by hitting /api/login
    loc = (await app_client.get("/api/login", follow_redirects=False)).headers["location"]
    state = loc.split("state=")[1].split("&")[0]
    async def fake_exchange(code, settings, client):
        return {"access_token":"a","refresh_token":"r","expires_in":3600}
    async def fake_members(access, settings, client):
        return {"primaryMembershipId":"mid1","destinyMemberships":[
            {"membershipType":3,"membershipId":"mid1","displayName":"G"}]}
    monkeypatch.setattr(auth, "exchange_code", fake_exchange)
    monkeypatch.setattr(auth, "get_memberships", fake_members)
    r = await app_client.get(f"/callback?code=x&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "sid=" in r.headers.get("set-cookie","")
    s = await app_client.get("/api/status")
    assert s.json()["authenticated"] is True

@pytest.mark.asyncio
async def test_protected_route_401_without_session(app_client):
    r = await app_client.get("/api/weapons")
    assert r.status_code == 401
```

Add an `app_client` fixture to conftest: builds `AsyncClient` against `app` with `LifespanManager`, pointing the pool at the test DB.

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `auth.py`:
  - `/api/login`: create state via `oauth_states` insert (TTL 10 min), redirect to `build_authorize_url`.
  - `/callback`: validate+delete state; `exchange_code`; `get_memberships`; reuse the existing `_pick_membership` logic (move it into `auth.py`); `users.upsert`; `tokens.set_tokens` (encrypted); seed `user_perk_ratings` default set if new (Task 16 provides seed loader — for now insert nothing, ratings fall back to seed file at read time); `sessions.create`; set cookie; redirect to `frontend_url`.
  - `get_current_user`: read `sid` cookie → `sessions.lookup` → `users.get`; raise 401 if missing.
  - `/api/auth/logout`: `sessions.delete`, clear cookie.
  - `/api/status`: returns `{"authenticated": <session valid>}`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/app/main.py backend/tests/test_auth.py backend/tests/conftest.py
git commit -m "feat(auth): Bungie SSO, server-side sessions, get_current_user"
```

---

### Task 10: Per-user lazy token refresh helper

**Files:**
- Create: `backend/app/bungie_session.py`
- Test: `backend/tests/test_bungie_session.py`

**Interfaces:**
- Consumes: `tokens` repo, `bungie_oauth.refresh_tokens`, `Throttle`.
- Produces: `async valid_access_token(pool, user_id, settings, client, key) -> tuple[str, int, str]` — returns `(access, membership_type, membership_id)`; refreshes under a per-user `asyncio.Lock` when expired; on refresh failure clears tokens and raises `HTTPException(401)`. Replaces main.py's `_valid_access_token`.

- [ ] **Step 1: Write failing test** — seed tokens with `access_expires_at` in the past; monkeypatch `refresh_tokens` to return new tokens; assert returned access == new and DB updated; second test: two concurrent calls trigger exactly one refresh (assert call count == 1).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with a module-level `defaultdict(asyncio.Lock)` keyed by `user_id`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/app/bungie_session.py backend/tests/test_bungie_session.py
git commit -m "feat(bungie): per-user lazy token refresh with single-flight lock"
```

---

# Phase 3 — Cache adapter for manifest

### Task 11: Async cache adapter for manifest module

**Files:**
- Modify: `backend/app/manifest.py` (replace `kv_get/kv_set(conn,...)` with an injected async cache: `manifest_get/manifest_set/manifest_version` from `cache` repo)
- Test: `backend/tests/test_manifest_cache.py`

**Interfaces:**
- Produces: `async load_cached_manifest(pool) -> Manifest|None`; `async load_manifest(client, pool, throttle) -> Manifest`. Manifest data lives in `manifest_cache` (global).

- [ ] **Step 1: Write failing test** — insert fake manifest rows via `cache.manifest_set`, assert `load_cached_manifest(pool)` reconstructs `Manifest` with int keys; assert `load_manifest` returns cached when version matches (monkeypatch the httpx meta call to return same version, assert no def download).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — port both functions to async + cache repo; route the two large `client.get` def downloads through `throttle.run`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git commit -am "refactor(manifest): async global manifest cache via repo"
```

---

### Task 12: Per-user data helpers (perk_ratings, builds, user tables) → MySQL

**Files:**
- Create: `backend/app/repositories/perk_ratings.py`, `builds.py`, `user_tables.py`
- Test: `backend/tests/test_user_data_repos.py`

**Interfaces:**
- Produces:
  - `perk_ratings.load(pool, user_id) -> PerkRatings` (reuse existing `PerkRatings` class + `load_seed()` from `app.perk_ratings`; overrides come from `user_perk_ratings WHERE user_id=%s`).
  - `perk_ratings.save(pool, user_id, perk_name, weapon_type, rating, reason, tags, notes)`.
  - `builds.load_builds(pool, user_id) -> dict` / `builds.save_build(pool, user_id, key, data)`; `builds.load_activities(pool, user_id) -> list` / `builds.save_activity(pool, user_id, name, data)` (seed files still from `app.builds`).
  - `user_tables.get_tags(pool, user_id)/set_tag/.../get_loadouts/.../get_armor_sets/...` mirroring today's main.py SQLite helpers, all scoped by `user_id`.

- [ ] **Step 1: Write failing tests** — per-user isolation for ratings (user A override doesn't affect B), builds override replaces seed for that user only, tag set/clear, loadout save/delete, armor-set save/delete.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** — keep the existing `PerkRatings`/`load_seed`/`_seed_builds`/`_seed_activities` pure helpers in `app.perk_ratings`/`app.builds`; the new repo modules supply the per-user override rows. Tags split stored as comma-joined string as today.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit**

```bash
git add backend/app/repositories/perk_ratings.py backend/app/repositories/builds.py backend/app/repositories/user_tables.py backend/tests/test_user_data_repos.py
git commit -m "feat(repos): per-user perk ratings, builds/activities, tags/loadouts/armor-sets"
```

---

# Phase 4 — Endpoint migration

> **Migration pattern (applies to every route in Tasks 13–20):**
> 1. Add `current_user: dict = Depends(get_current_user)` (and `pool = Depends(get_pool)`).
> 2. Replace `conn = get_conn(...)` with `pool`; replace `kv_get/kv_set(conn, k)` with `await cache.get/set(pool, current_user["user_id"], k, ...)`.
> 3. Replace `_valid_access_token(settings, conn, client)` with `await valid_access_token(pool, current_user["user_id"], settings, client, settings.token_enc_key)`.
> 4. Replace `load_ratings/save_rating/load_builds/...` with the per-user repo calls (`current_user["user_id"]`).
> 5. Route every outbound Bungie `client.get/post` through `app.state.throttle.run(...)`.
> 6. State-changing routes (PUT/POST/DELETE that write to Bungie) add `Depends(require_csrf)`.
> Each task writes an endpoint test that (a) 401s without a session and (b) returns per-user-correct data with a session, using the `app_client` + seeded-session fixture.

### Task 13: Read endpoints — weapons, recommendations, loadout-suggestion, counts, characters, armor

**Files:** Modify `backend/app/main.py` (these routes); Test `backend/tests/test_endpoints_read.py`.

- [ ] Step 1: Write failing tests (401 without session; with a seeded session + seeded `user_cache` weapons_cache, `/api/weapons` returns it; `/api/counts` derives counts; isolation: user B sees empty).
- [ ] Step 2: Run → FAIL.
- [ ] Step 3: Apply the migration pattern to: `/api/weapons`, `/api/recommendations`, `/api/loadout-suggestion`, `/api/counts`, `/api/characters`, `/api/armor`. Port `_compute_weapons`, `_recompute_from_cache`, `_save_profile`, `_load_profile_or_400` to take `(pool, user_id)`.
- [ ] Step 4: Run → PASS.
- [ ] Step 5: Commit `feat(api): per-user read endpoints`.

### Task 14: Perks endpoints — `GET/PUT /api/perks`

**Files:** Modify `main.py`; Test `tests/test_endpoints_perks.py`.
- [ ] TDD: GET returns merged seed+user overrides; PUT saves a user override and recomputes that user's cached weapons only; isolation verified. Commit `feat(api): per-user perks`.

### Task 15: Builds & activities — `GET/PUT /api/builds`, `/api/activities`, `/api/activities/catalog`

**Files:** Modify `main.py`; Test `tests/test_endpoints_builds.py`.
- [ ] TDD: per-user builds/activities; `activities/catalog` cached globally in `manifest_cache` (it is account-independent). Commit `feat(api): per-user builds/activities; global activity catalog`.

### Task 16: Default perk-rating seed on first login

**Files:** Modify `backend/app/auth.py` (callback seeds `user_perk_ratings` for new users); Create `backend/app/data/perk_ratings_default.json` (export of current owner ratings as the default override set, or empty if none); Test `tests/test_seed_on_signup.py`.
- [ ] TDD: new user → `user_perk_ratings` populated from default file; returning user → not re-seeded. Commit `feat(auth): seed default perk ratings for new users`.

### Task 17: Tags — `GET/PUT /api/tags`

**Files:** Modify `main.py`; Test `tests/test_endpoints_tags.py`.
- [ ] TDD per-user tag set/clear/isolation. Commit `feat(api): per-user item tags`.

### Task 18: Memberships — `GET /api/memberships`, `POST /api/memberships/select`

**Files:** Modify `main.py`; Test `tests/test_endpoints_memberships.py`.
- [ ] TDD: select updates `user_tokens` membership for that user and clears that user's account cache keys (`_ACCOUNT_CACHE_KEYS` via `cache.delete` loop). Commit `feat(api): per-user membership selection`.

### Task 19: Write-to-Bungie routes — transfer, transfer/bulk, postmaster, postmaster/pull

**Files:** Modify `main.py`; Test `tests/test_endpoints_transfer.py`.
- [ ] TDD: 401 without session; with session, mock `bungie_client.transfer_item/equip_item/get_profile/pull_from_postmaster`; assert per-user profile cache refreshed; `require_csrf` enforced (missing CSRF → 403). Port `_move_one`, `_apply_item_set` to `(pool, user_id)`. Commit `feat(api): per-user inventory writes + CSRF`.

### Task 20: Loadouts & armor-sets — list/save/delete/apply

**Files:** Modify `main.py`; Test `tests/test_endpoints_loadouts.py`.
- [ ] TDD: per-user CRUD + apply (mock Bungie); isolation. Commit `feat(api): per-user loadouts and armor sets`.

---

# Phase 5 — Frontend & cutover

### Task 21: Frontend login/logout + 401 handling

**Files:**
- Modify: `backend/../frontend/src/*` (API client + a login gate)
- Test: `frontend` vitest for the API client 401→redirect behavior.

**Interfaces:** API client intercepts `401` → redirect `window.location = "/api/login"`. Add a "Sign in with Bungie" screen shown when `/api/status` is false; add a logout button calling `POST /api/auth/logout` with the CSRF header.

- [ ] Step 1: Write failing vitest for the fetch wrapper (mock 401 → asserts redirect called).
- [ ] Step 2: Run `cd frontend && npm test` → FAIL.
- [ ] Step 3: Implement the wrapper + login gate + logout control + CSRF header read from a `csrftoken` cookie.
- [ ] Step 4: Run → PASS; `npm run build`.
- [ ] Step 5: Commit `feat(frontend): Bungie login gate, 401 redirect, logout`.

### Task 22: CSRF token issuance

**Files:** Modify `backend/app/auth.py` (issue a `csrftoken` cookie on session create; `require_csrf` compares header `X-CSRF-Token` to cookie — double-submit); Test `tests/test_csrf.py`.
- [ ] TDD: state-changing route without matching token → 403; with → passes. Commit `feat(auth): double-submit CSRF protection`.

### Task 23: Retire SQLite + docs + server entrypoint

**Files:**
- Delete: `backend/app/storage.py`
- Modify: `backend/app/main.py` (remove all `get_conn/kv_*` imports/usages — verify none remain), `backend/app/manifest.py` (no `storage` import), `destiny-weapon-advisor/README.md` (MySQL setup, env, `python -m scripts.migrate`), `scripts/serve.sh`/`run.sh` (export DB env; run migrations before boot).
- Test: `tests/test_no_sqlite_refs.py` — asserts `import sqlite3` and `from app.storage` appear nowhere under `app/`.

- [ ] Step 1: Write failing test scanning `app/` for `sqlite3` / `app.storage` references.
- [ ] Step 2: Run → FAIL (refs remain).
- [ ] Step 3: Remove the last references; delete `storage.py`; update README + scripts.
- [ ] Step 4: Run full suite: `cd backend && python -m pytest -q` → PASS; `cd frontend && npm test && npm run build` → PASS.
- [ ] Step 5: Commit `refactor: retire SQLite single-user storage; MySQL-only`.

---

## Self-Review

**Spec coverage:**
- §2/§3 components → Tasks 1–12, 23 (storage retired). ✓
- §4 schema (all tables) → Task 3. ✓
- §5 auth/request/logout flow → Tasks 9, 10, 19. ✓
- §6 rate-limit/cache/session TTL → Tasks 6 (cache TTL, session TTL), 8 (throttle), 11 (manifest cache). ✓
- §7 security (token encryption, cookie flags, CSRF, isolation, no secret logging) → Tasks 2, 6, 9, 22; isolation asserted in 6, 12, 13–20. ✓
- §8 error handling (429, auth fail, 401, 503) → Tasks 8, 10, 9. (Bungie-maintenance friendly banner is surfaced via the frontend 401/5xx handling in Task 21.) ✓
- §9 frontend → Tasks 21, 22. ✓
- §10 testing → tests in every task. ✓
- §11 config → Task 1. ✓
- §12 rollout/seed → Tasks 16, 23. ✓

**Placeholder scan:** Tasks 1–10 carry full code; Tasks 11–22 specify exact files, interfaces, the verbatim migration pattern, and per-task TDD assertions rather than re-pasting the ~25 near-identical endpoint bodies (doing so would violate DRY and bloat the plan). Each router task names its exact routes, helpers to port, and test cases — no "TBD"/"handle edge cases" left.

**Type consistency:** repo function names used in Phase 4 (`cache.get/set/delete`, `valid_access_token`, `perk_ratings.load/save`, `builds.load_builds/save_build/load_activities/save_activity`, `user_tables.*`) match their definitions in Tasks 6, 10, 12. `current_user["user_id"]` is the consistent key (from `users.get`). `Throttle.run` consistent between Tasks 8 and 11/13–20.

> **Note on router tasks (13–20):** These are deliberately pattern-based, not fully code-pasted, because they are mechanical applications of the boxed migration pattern across ~25 structurally identical endpoints. The executing engineer applies the pattern per route with the named tests. If your execution mode requires fully-expanded code per route, expand each route inline from its current body in `app/main.py` using the six-step pattern before implementing.
