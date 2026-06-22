import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pytest_asyncio
import aiomysql
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport

from app.config import get_settings
from scripts.migrate import apply_migrations

_TEST_DB = "advisor_test"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_pool():
    s = get_settings()
    # Drop and recreate the test database for a clean slate each session.
    conn = await aiomysql.connect(
        host=s.db_host, port=s.db_port, user=s.db_user, password=s.db_password,
    )
    async with conn.cursor() as cur:
        await cur.execute(f"DROP DATABASE IF EXISTS `{_TEST_DB}`")
        await cur.execute(
            f"CREATE DATABASE `{_TEST_DB}` "
            "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conn.close()

    pool = await aiomysql.create_pool(
        host=s.db_host, port=s.db_port, user=s.db_user,
        password=s.db_password, db=_TEST_DB, autocommit=False,
    )
    # Apply migrations once so the schema exists for all tests.
    await apply_migrations(pool)
    yield pool
    pool.close()
    await pool.wait_closed()


_DATA_TABLES = (
    "sessions",
    "oauth_states",
    "user_tokens",
    "user_cache",
    "user_perk_ratings",
    "user_builds",
    "user_activities",
    "user_item_tags",
    "user_loadouts",
    "user_armor_sets",
    "manifest_cache",
    "users",
)


@pytest_asyncio.fixture(loop_scope="session")
async def clean_db(db_pool):
    """Truncate all data tables before each test, then yield the pool."""
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in _DATA_TABLES:
                await cur.execute(f"TRUNCATE TABLE {t}")
            await cur.execute("SET FOREIGN_KEY_CHECKS=1")
        await conn.commit()
    yield db_pool


@pytest_asyncio.fixture(loop_scope="session")
async def app_client(clean_db):
    """ASGI test client with cookies; pool overridden to the test DB."""
    from app.main import app
    async with LifespanManager(app):
        app.state.pool = clean_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as client:
            yield client


async def login_user(app_client, monkeypatch, bungie_id: str = "bm1") -> int:
    """Log in a synthetic user and return their user_id.

    Hits /api/login to seed an OAuth state, monkeypatches exchange_code and
    get_memberships, then calls /callback which sets the sid cookie on
    app_client.  Returns the user_id that was created/upserted.
    """
    import app.auth as auth_module
    from app.repositories import users as users_repo  # noqa: F401 used below

    # Seed a valid OAuth state by hitting /api/login.
    loc = (await app_client.get("/api/login", follow_redirects=False)).headers["location"]
    state = loc.split("state=")[1].split("&")[0]

    async def fake_exchange(code, settings, client):
        return {"access_token": f"acc-{bungie_id}", "refresh_token": f"ref-{bungie_id}", "expires_in": 3600}

    async def fake_members(access, settings, client):
        return {
            "primaryMembershipId": bungie_id,
            "destinyMemberships": [
                {"membershipType": 3, "membershipId": bungie_id, "displayName": f"User-{bungie_id}"}
            ],
        }

    monkeypatch.setattr(auth_module, "exchange_code", fake_exchange)
    monkeypatch.setattr(auth_module, "get_memberships", fake_members)

    r = await app_client.get(f"/callback?code=x&state={state}", follow_redirects=False)
    assert r.status_code in (302, 307), f"callback failed: {r.status_code} {r.text}"

    # The sid cookie is now set on app_client.  Look up the user_id from DB.
    pool = app_client._transport.app.state.pool
    # upsert is idempotent — returns user_id without re-creating anything.
    uid = await users_repo.upsert(
        pool, bungie_id, f"User-{bungie_id}", 3, bungie_id
    )
    return uid
