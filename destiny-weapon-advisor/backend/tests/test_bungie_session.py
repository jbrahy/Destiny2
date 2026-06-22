import asyncio
import time
import pytest

import app.bungie_session as bungie_session
from app.config import get_settings
from app.repositories import users, tokens

pytestmark = pytest.mark.asyncio(loop_scope="session")

settings = get_settings()


async def test_refresh_when_expired(clean_db, monkeypatch):
    """Expired access token triggers refresh; DB and return value updated."""
    uid = await users.upsert(clean_db, "bm_refresh", "RefreshUser", 3, "mid_refresh")
    key = settings.token_enc_key
    await tokens.set_tokens(
        clean_db, uid,
        "OLD_ACCESS", "OLD_REFRESH",
        time.time() - 100,   # expired
        time.time() + 7776000,
        3, "mid_refresh",
        key,
    )

    async def fake_refresh(refresh_token, s, client):
        return {"access_token": "NEW", "refresh_token": "NEWREF", "expires_in": 3600}

    monkeypatch.setattr(bungie_session, "refresh_tokens", fake_refresh)

    access, mtype, mid = await bungie_session.valid_access_token(
        clean_db, uid, settings, client=None, key=key
    )

    assert access == "NEW"
    # DB should also reflect the new token
    stored = await tokens.get_tokens(clean_db, uid, key)
    assert stored["access_token"] == "NEW"


async def test_single_flight(clean_db, monkeypatch):
    """Two concurrent calls on an expired token trigger exactly one refresh."""
    uid = await users.upsert(clean_db, "bm_single", "SingleUser", 3, "mid_single")
    key = settings.token_enc_key
    await tokens.set_tokens(
        clean_db, uid,
        "OLD", "OLD_REF",
        time.time() - 100,
        time.time() + 7776000,
        3, "mid_single",
        key,
    )

    call_count = 0

    async def counting_refresh(refresh_token, s, client):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)   # brief pause to allow second coroutine to enter lock
        return {"access_token": "FRESH", "refresh_token": "FRESHREF", "expires_in": 3600}

    monkeypatch.setattr(bungie_session, "refresh_tokens", counting_refresh)

    # Remove any cached lock for this user so the test is isolated
    bungie_session._locks.pop(uid, None)

    results = await asyncio.gather(
        bungie_session.valid_access_token(clean_db, uid, settings, client=None, key=key),
        bungie_session.valid_access_token(clean_db, uid, settings, client=None, key=key),
    )

    assert call_count == 1
    assert results[0][0] == "FRESH"
    assert results[1][0] == "FRESH"


async def test_no_tokens_401(clean_db):
    """User with no token row raises HTTPException(401)."""
    from fastapi import HTTPException

    uid = await users.upsert(clean_db, "bm_notoken", "NoTokenUser", 3, "mid_notoken")
    # Deliberately do NOT insert a token row.

    with pytest.raises(HTTPException) as exc_info:
        await bungie_session.valid_access_token(
            clean_db, uid, settings, client=None, key=settings.token_enc_key
        )

    assert exc_info.value.status_code == 401
