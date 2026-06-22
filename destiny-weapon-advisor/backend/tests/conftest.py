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
    yield pool
    pool.close()
    await pool.wait_closed()
