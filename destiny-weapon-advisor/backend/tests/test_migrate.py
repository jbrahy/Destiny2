import pytest
from scripts.migrate import apply_migrations

pytestmark = pytest.mark.asyncio(loop_scope="session")


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
