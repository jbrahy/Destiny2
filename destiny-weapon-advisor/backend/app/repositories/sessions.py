import hashlib
import secrets

from app import db


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create(pool, user_id: int, ttl_days: int) -> str:
    """Create a session; return the raw (unhashed) token."""
    raw = secrets.token_urlsafe(32)
    session_id = _hash(raw)
    await db.execute(
        pool,
        "INSERT INTO sessions (session_id, user_id, expires_at) "
        "VALUES (%s, %s, NOW() + INTERVAL %s DAY)",
        (session_id, user_id, ttl_days),
    )
    return raw


async def lookup(pool, raw_token: str) -> int | None:
    """Return user_id for a valid session, or None if missing/expired."""
    session_id = _hash(raw_token)
    row = await db.fetchone(
        pool,
        "SELECT user_id FROM sessions WHERE session_id=%s AND expires_at > NOW()",
        (session_id,),
    )
    if row is None:
        return None
    user_id = row[0]
    await db.execute(
        pool,
        "UPDATE sessions SET last_seen_at=NOW() WHERE session_id=%s",
        (session_id,),
    )
    return user_id


async def delete(pool, raw_token: str) -> None:
    """Delete a session by raw token."""
    session_id = _hash(raw_token)
    await db.execute(
        pool,
        "DELETE FROM sessions WHERE session_id=%s",
        (session_id,),
    )
