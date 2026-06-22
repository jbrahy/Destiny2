"""Per-user lazy token refresh with single-flight lock.

Public surface:
    valid_access_token(pool, user_id, settings, client, key)
        -> tuple[access_token: str, membership_type: int, membership_id: str]

Refreshes under a per-user asyncio.Lock so concurrent requests for the same
user trigger only one Bungie token-refresh call (single-flight pattern).
"""

import asyncio
import time

from fastapi import HTTPException

from app.bungie_oauth import refresh_tokens  # importable at module level so tests can monkeypatch
from app.repositories import tokens

# Module-level registry of per-user asyncio locks.
_locks: dict[int, asyncio.Lock] = {}


async def valid_access_token(
    pool,
    user_id: int,
    settings,
    client,
    key: str,
) -> tuple[str, int, str]:
    """Return (access_token, membership_type, membership_id) for user_id.

    Refreshes the access token when it is expired or within 60 s of expiry.
    A per-user lock ensures only one refresh runs concurrently (single-flight).
    Raises HTTPException(401) when:
    - the user has no token row, or
    - the refresh attempt fails (token row is deleted before raising).
    """
    tok = await tokens.get_tokens(pool, user_id, key)
    if tok is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    access = tok["access_token"]

    if time.time() > tok["access_expires_at"] - 60:
        # Acquire per-user lock (create lazily if absent).
        lock = _locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            # Double-checked locking: re-read after acquiring the lock in case
            # another coroutine already refreshed while we were waiting.
            tok = await tokens.get_tokens(pool, user_id, key)
            if tok is None:
                raise HTTPException(status_code=401, detail="Not authenticated")

            if time.time() > tok["access_expires_at"] - 60:
                # Still expired — we are the one that must refresh.
                try:
                    new = await refresh_tokens(tok["refresh_token"], settings, client)
                except Exception:
                    await tokens.delete(pool, user_id)
                    raise HTTPException(
                        status_code=401,
                        detail="Session expired; please log in again.",
                    )

                await tokens.set_tokens(
                    pool,
                    user_id,
                    new["access_token"],
                    new["refresh_token"],
                    time.time() + new["expires_in"],
                    time.time() + 7776000,
                    tok["membership_type"],
                    tok["membership_id"],
                    key,
                )
                access = new["access_token"]
                tok = await tokens.get_tokens(pool, user_id, key)
            else:
                # Another coroutine already refreshed; use the fresh token.
                access = tok["access_token"]

    return access, tok["membership_type"], tok["membership_id"]
