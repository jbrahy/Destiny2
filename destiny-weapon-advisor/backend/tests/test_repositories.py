import time
import pytest
from app.crypto import generate_key
from app.repositories import users, tokens, sessions, cache

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_user_upsert_idempotent(clean_db):
    uid = await users.upsert(clean_db, "bm1", "Guardian", 3, "mid1")
    uid2 = await users.upsert(clean_db, "bm1", "Guardian#2", 3, "mid1")
    assert uid == uid2
    assert (await users.get(clean_db, uid))["display_name"] == "Guardian#2"


async def test_tokens_encrypted_round_trip(clean_db):
    key = generate_key()
    uid = await users.upsert(clean_db, "bm1", "G", 3, "mid1")
    await tokens.set_tokens(clean_db, uid, "acc", "ref", 111, 222, 3, "mid1", key)
    got = await tokens.get_tokens(clean_db, uid, key)
    assert got["access_token"] == "acc" and got["refresh_token"] == "ref"
    # ciphertext on disk is not plaintext
    from app import db
    raw = await db.fetchone(clean_db, "SELECT access_token_enc FROM user_tokens WHERE user_id=%s", (uid,))
    assert raw[0] != b"acc"


async def test_session_lifecycle(clean_db):
    uid = await users.upsert(clean_db, "bm1", "G", 3, "mid1")
    raw = await sessions.create(clean_db, uid, ttl_days=30)
    assert await sessions.lookup(clean_db, raw) == uid
    await sessions.delete(clean_db, raw)
    assert await sessions.lookup(clean_db, raw) is None


async def test_cache_isolation_and_ttl(clean_db):
    a = await users.upsert(clean_db, "a", "A", 3, "1")
    b = await users.upsert(clean_db, "b", "B", 3, "2")
    await cache.set(clean_db, a, "weapons", "AAA", ttl_seconds=300)
    assert await cache.get(clean_db, a, "weapons") == "AAA"
    assert await cache.get(clean_db, b, "weapons") is None  # isolation
    await cache.set(clean_db, a, "x", "v", ttl_seconds=-1)   # already expired
    assert await cache.get(clean_db, a, "x") is None
