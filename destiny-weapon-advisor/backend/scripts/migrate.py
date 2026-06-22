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
