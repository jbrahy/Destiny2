from app import db


async def get(pool, user_id: int, key: str) -> str | None:
    """Return cached value for user_id/key if not expired, else None."""
    row = await db.fetchone(
        pool,
        "SELECT value FROM user_cache "
        "WHERE user_id=%s AND cache_key=%s "
        "AND (expires_at IS NULL OR expires_at > NOW())",
        (user_id, key),
    )
    return row[0] if row is not None else None


async def set(pool, user_id: int, key: str, value: str, ttl_seconds: int | None) -> None:
    """Upsert a cache entry with optional TTL in seconds."""
    if ttl_seconds is None:
        await db.execute(
            pool,
            "INSERT INTO user_cache (user_id, cache_key, value, expires_at) "
            "VALUES (%s, %s, %s, NULL) "
            "ON DUPLICATE KEY UPDATE value=VALUES(value), expires_at=NULL",
            (user_id, key, value),
        )
    else:
        await db.execute(
            pool,
            "INSERT INTO user_cache (user_id, cache_key, value, expires_at) "
            "VALUES (%s, %s, %s, NOW() + INTERVAL %s SECOND) "
            "ON DUPLICATE KEY UPDATE value=VALUES(value), expires_at=VALUES(expires_at)",
            (user_id, key, value, ttl_seconds),
        )


async def delete(pool, user_id: int, key: str) -> None:
    """Delete a cache entry."""
    await db.execute(
        pool,
        "DELETE FROM user_cache WHERE user_id=%s AND cache_key=%s",
        (user_id, key),
    )


async def manifest_get(pool, key: str) -> str | None:
    """Return manifest cache value for key, or None."""
    row = await db.fetchone(
        pool,
        "SELECT value FROM manifest_cache WHERE cache_key=%s",
        (key,),
    )
    return row[0] if row is not None else None


async def manifest_set(pool, key: str, value: str, version: str) -> None:
    """Upsert a manifest cache entry with version."""
    await db.execute(
        pool,
        "INSERT INTO manifest_cache (cache_key, value, version) "
        "VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE value=VALUES(value), version=VALUES(version)",
        (key, value, version),
    )


async def manifest_version(pool) -> str | None:
    """Return the version string for the manifest_items cache row, or None."""
    row = await db.fetchone(
        pool,
        "SELECT version FROM manifest_cache WHERE cache_key=%s",
        ("manifest_items",),
    )
    return row[0] if row is not None else None
