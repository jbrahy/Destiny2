import pytest
import pytest_asyncio
from scripts.migrate import apply_migrations

pytestmark = pytest.mark.asyncio(loop_scope="session")

_ALL_TABLES = (
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
    "schema_migrations",
)


@pytest_asyncio.fixture(loop_scope="session")
async def empty_pool(db_pool):
    """Drop all tables so apply_migrations starts from scratch, then restore."""
    async with db_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SET FOREIGN_KEY_CHECKS=0")
            for t in _ALL_TABLES:
                await cur.execute(f"DROP TABLE IF EXISTS `{t}`")
            await cur.execute("SET FOREIGN_KEY_CHECKS=1")
        await conn.commit()
    yield db_pool
    # Restore schema for any tests that run after this module.
    await apply_migrations(db_pool)


async def test_apply_migrations_creates_tables(empty_pool):
    applied = await apply_migrations(empty_pool)
    assert "0001_init.sql" in applied
    async with empty_pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SHOW TABLES")
            tables = {r[0] for r in await cur.fetchall()}
    for t in ("users", "user_tokens", "sessions", "user_cache", "user_perk_ratings",
              "manifest_cache", "oauth_states", "user_builds", "user_activities",
              "user_item_tags", "user_loadouts", "user_armor_sets", "schema_migrations"):
        assert t in tables
    # idempotent
    applied2 = await apply_migrations(empty_pool)
    assert applied2 == []
