# Multi-User Foundation — Design Spec

**Sub-project:** A (of program: C → A → B → D)
**Date:** 2026-06-22
**Status:** Approved design — pending implementation plan
**Scope target:** Medium scale (1k–10k users) · MySQL 8 InnoDB · Bungie-only SSO · FastAPI + aiomysql (Approach 1: Lean async-MySQL)

---

## 1. Problem & Goal

The Destiny 2 Advisor is today a **single-user local app**:

- `app/storage.py` defines a `tokens` table constrained to exactly one row (`CHECK (id = 1)`).
- The `kv` table is a **global** cache (inventory, manifest, perk ratings) — nothing is scoped per user.
- There is **no session concept**; the OAuth `state` is CSRF-only. The app assumes "the one user is the server owner."
- Bungie OAuth tokens are stored **plaintext** in SQLite. TLS is self-signed for `localhost:8443`.

**Goal:** Turn this into a public, multi-user web app at `destinyopt.com` where any Destiny player can sign in with Bungie and get their own scoped advisor, designed to hold 1k–10k users on a single Bungie app API key.

**Non-goals (handled by other sub-projects):**
- Rotating ad/offer system → **B**.
- nginx, TLS (Let's Encrypt), systemd, prod secrets (SSM) → **D**.
- No automated SQLite→MySQL data migration: the public DB starts fresh; only default perk ratings are seeded.

---

## 2. Architecture

FastAPI (unchanged) with:

- An **async MySQL pool** (`aiomysql`) created/closed in the FastAPI lifespan.
- **Explicit, parameterized SQL** in small repository modules (no ORM — matches house "explicit over magic / parameterized queries only").
- **Server-side sessions** in MySQL, addressed by a signed HttpOnly cookie.
- **Per-user encrypted** Bungie tokens (Fernet).
- **Lazy token refresh** guarded by a global outbound-Bungie **throttle**.
- A **per-user cache** table; a **global manifest** cache.

The cache + throttle live behind a thin interface so a Redis-backed implementation (Approach 2) can drop in later without changing call sites.

```
Browser ──cookie(sid)──> FastAPI
                           ├─ auth.get_current_user (session lookup)
                           ├─ routers (weapons/perks/armor/builds/moves)
                           ├─ repositories/* ──> MySQL (users, tokens, sessions, user_cache, ...)
                           └─ bungie_client ──throttle──> Bungie API
                                                   ├─ lazy token refresh (per-user lock)
                                                   └─ response cache (user_cache / manifest_cache, TTL)
```

---

## 3. Components

| Path | Responsibility |
|---|---|
| `app/db.py` | aiomysql pool lifecycle (lifespan), acquire/release helper. |
| `app/crypto.py` | Fernet encrypt/decrypt for tokens (key from `TOKEN_ENC_KEY`). |
| `app/auth.py` | `/auth/login`, `/callback`, `/auth/logout`; `get_current_user` dependency; CSRF token issue/verify. |
| `app/bungie_throttle.py` | `asyncio.Semaphore` + 429 exponential backoff wrapper around outbound Bungie calls. |
| `app/repositories/users.py` | upsert/get user by `bungie_membership_id`. |
| `app/repositories/tokens.py` | get/set encrypted tokens per user. |
| `app/repositories/sessions.py` | create/lookup/delete/expire sessions. |
| `app/repositories/cache.py` | per-user + global cache get/set with TTL. |
| `app/repositories/perk_ratings.py` | per-user perk ratings CRUD + default seed. |
| `migrations/0001_init.sql` | initial schema. |
| `scripts/migrate.py` | tiny forward-only migration runner (applies un-applied `migrations/*.sql`, tracked in a `schema_migrations` table). |
| `app/main.py` (refactor) | mount routers + frontend; remove single-user assumptions. Extract routers: `weapons`, `perks`, `armor`, `builds`, `moves`. |
| `app/storage.py` | **retired** (SQLite kv/tokens). |

**New dependency:** `aiomysql>=0.2`. Keep existing `cryptography`.

---

## 4. Data model (MySQL 8, InnoDB, `utf8mb4` / `utf8mb4_unicode_ci`)

All tables InnoDB, strict mode. PKs singular `_id`. All FKs indexed. Timestamps `TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP`.

### `users`
| column | type | notes |
|---|---|---|
| `user_id` | BIGINT(20) UNSIGNED PK AUTO_INCREMENT | |
| `bungie_membership_id` | VARCHAR(32) NOT NULL UNIQUE | stable Bungie.net identity |
| `display_name` | VARCHAR(190) | Bungie global display name |
| `primary_membership_type` | INT(11) UNSIGNED | destiny platform |
| `primary_membership_id` | VARCHAR(32) | destiny membership |
| `status` | ENUM('active','disabled') DEFAULT 'active' | |
| `created_at` / `updated_at` | TIMESTAMP | `updated_at` ON UPDATE CURRENT_TIMESTAMP |

### `user_tokens` (1:1 with users)
| column | type | notes |
|---|---|---|
| `user_id` | BIGINT(20) UNSIGNED PK, FK→users | ON DELETE CASCADE |
| `access_token_enc` | BLOB NOT NULL | Fernet ciphertext |
| `refresh_token_enc` | BLOB NOT NULL | Fernet ciphertext |
| `access_expires_at` | TIMESTAMP | |
| `refresh_expires_at` | TIMESTAMP | Bungie refresh ~90 days |
| `membership_type` | INT(11) UNSIGNED | destiny |
| `membership_id` | VARCHAR(32) | destiny |
| `updated_at` | TIMESTAMP | |

### `sessions`
| column | type | notes |
|---|---|---|
| `session_id` | CHAR(64) PK | SHA-256 hex of the cookie token; raw token never stored |
| `user_id` | BIGINT(20) UNSIGNED, FK→users, INDEX | ON DELETE CASCADE |
| `expires_at` | TIMESTAMP | sliding or fixed TTL (see §6) |
| `created_at` / `last_seen_at` | TIMESTAMP | |
| `user_agent` | VARCHAR(255) | optional audit |

### `user_cache`
| column | type | notes |
|---|---|---|
| `user_id` | BIGINT(20) UNSIGNED, FK→users | composite PK part; ON DELETE CASCADE |
| `cache_key` | VARCHAR(190) | composite PK part |
| `value` | LONGTEXT | JSON |
| `updated_at` | TIMESTAMP | |
| `expires_at` | TIMESTAMP NULL | TTL; NULL = no expiry |

PK = (`user_id`, `cache_key`).

### `user_perk_ratings`
| column | type | notes |
|---|---|---|
| `user_id` | BIGINT(20) UNSIGNED, FK→users | composite PK part; ON DELETE CASCADE |
| `weapon_type` | VARCHAR(64) | composite PK part |
| `perk_hash` | BIGINT(20) UNSIGNED | composite PK part |
| `rating` | CHAR(1) | S/A/B/C/D |
| `notes` | TEXT | |
| `updated_at` | TIMESTAMP | |

PK = (`user_id`, `weapon_type`, `perk_hash`). Seeded per user from a default rating set on first login.

### `manifest_cache` (global, shared)
| column | type | notes |
|---|---|---|
| `cache_key` | VARCHAR(190) PK | |
| `value` | LONGTEXT | JSON |
| `version` | VARCHAR(64) | Bungie manifest version |
| `updated_at` | TIMESTAMP | |

### `oauth_states` (short-lived login CSRF)
| column | type | notes |
|---|---|---|
| `state` | CHAR(64) PK | random url-safe token |
| `created_at` | TIMESTAMP | |
| `expires_at` | TIMESTAMP | ~10 min TTL; swept on use/expiry |

### `schema_migrations`
| column | type |
|---|---|
| `filename` | VARCHAR(190) PK |
| `applied_at` | TIMESTAMP |

---

## 5. Auth & request flow

**Login**
1. `GET /auth/login` → generate random `state`, insert into `oauth_states`, 302 to Bungie `AUTHORIZE_URL`.
2. `GET /callback?code&state` → validate `state` exists/not expired (delete it), `exchange_code(code)` → tokens.
3. Call Bungie `GetMembershipsForCurrentUser` → `bungie_membership_id` + primary destiny membership.
4. **Upsert** `users` by `bungie_membership_id`; encrypt + store tokens in `user_tokens`; seed `user_perk_ratings` if new user.
5. Create a `sessions` row (store SHA-256 of a fresh random token); set cookie `sid=<rawtoken>`; 302 to `FRONTEND_URL`.

**Authenticated request**
- `get_current_user` dependency: read `sid` cookie → SHA-256 → `sessions` lookup → reject if missing/expired → load `users` row → attach to request state. Missing/expired → `401`.

**Logout**
- `POST /auth/logout` → delete session row, clear cookie.

**Outbound Bungie call (per user)**
- Load tokens; if `access_expires_at` passed, `refresh_tokens()` under a **per-user asyncio lock** (avoid stampede), persist new encrypted tokens.
- All Bungie HTTP goes through `bungie_throttle` (global semaphore + 429 backoff).
- Cache successful responses in `user_cache` (per-user) or `manifest_cache` (global) with TTL. **Refresh** button bypasses cache.

---

## 6. Rate-limit & caching

- **One** Bungie app API key shared by all users.
- Global `asyncio.Semaphore(N≈20)` caps concurrent outbound Bungie requests; 429 → exponential backoff with jitter, bounded retries.
- **Manifest**: fetched once globally, versioned in `manifest_cache`; refetched only on version change.
- **Per-user inventory/profile**: cached in `user_cache` with a short TTL (default 5 min, configurable); **Refresh** forces re-pull.
- **Session TTL**: fixed 30-day expiry, `last_seen_at` updated per request (sliding optional later).
- Cache + throttle behind an interface (`CacheBackend`, `Throttle`) → Redis swap-in later with no call-site changes.

---

## 7. Security

- **Token encryption at rest** — Fernet, key `TOKEN_ENC_KEY` (32-byte url-safe base64) from env; never logged.
- **Cookie** — `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, signed; raw session token only in the cookie, only its hash in the DB.
- **CSRF** — double-submit token required on state-changing routes (move/equip); SameSite=Lax covers the rest.
- **Session revocation** — logout deletes the row; expired rows swept.
- **Per-user isolation** — every `user_cache` / `user_perk_ratings` query is scoped by `user_id`; no cross-user reads.
- **Secrets** — env file with strict perms now; **AWS SSM Parameter Store** recommended for prod (sub-project D).
- **HTTPS mandatory** — cookies are `Secure`; enforced in prod via nginx/Let's Encrypt (sub-project D).
- Never log tokens or full Bungie payloads.

---

## 8. Error handling

| Condition | Behavior |
|---|---|
| Bungie 429 | throttle backoff + bounded retry; then 503 to client with retry hint |
| Bungie auth failure / invalid refresh | clear tokens, force re-login (`401` → frontend redirects to `/auth/login`) |
| Bungie maintenance (5xx / system disabled) | friendly banner; serve cached data if present |
| DB unavailable | `503` |
| Session missing/expired | `401`; frontend redirects to login |

---

## 9. Frontend impact (minimal in A)

- Add a **"Sign in with Bungie"** landing/login screen.
- On any `401`, redirect to `/auth/login`.
- Add a **logout** control.
- Existing multi-membership account-switch UI stays (now per-user).
- No visual redesign in A.

---

## 10. Testing (pytest, mocked Bungie httpx)

- OAuth `state` validation (valid / expired / missing / reused).
- Session lifecycle: create, lookup, expiry, logout revocation.
- **Token encryption round-trip** (encrypt→store→load→decrypt).
- **Per-user isolation**: user A cannot read user B's `user_cache` / ratings.
- Throttle: concurrency cap respected; 429 backoff retries then surfaces 503.
- Lazy refresh: expired access token triggers exactly one refresh under contention (per-user lock).
- Repository CRUD against a test MySQL schema (testcontainers or a dedicated test DB).
- **Preserve** existing scoring / recommend / armor / loadout tests unchanged (pure logic).

---

## 11. Config additions (`.env`)

```
DB_HOST=, DB_PORT=3306, DB_USER=, DB_PASSWORD=, DB_NAME=
TOKEN_ENC_KEY=<fernet key>
SESSION_SECRET=<random>
SESSION_TTL_DAYS=30
COOKIE_SECURE=true
USER_CACHE_TTL_SECONDS=300
BUNGIE_THROTTLE_CONCURRENCY=20
```
Bungie credentials unchanged (single app). `DB_PATH` removed.

---

## 12. Rollout

Build within the existing app; swap the data layer SQLite→MySQL; ship to prod in sub-project **D** (nginx + TLS + systemd + SSM secrets). Seed default perk ratings from the current owner's ratings exported as the default set.
