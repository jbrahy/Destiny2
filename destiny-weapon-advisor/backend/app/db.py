import aiomysql


async def create_pool(settings):
    return await aiomysql.create_pool(
        host=settings.db_host, port=settings.db_port, user=settings.db_user,
        password=settings.db_password, db=settings.db_name,
        autocommit=True, minsize=1, maxsize=10, charset="utf8mb4",
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
