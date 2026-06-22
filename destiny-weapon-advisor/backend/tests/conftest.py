import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pytest_asyncio
import aiomysql

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
