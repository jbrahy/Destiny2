from app import db, crypto


async def set_tokens(
    pool,
    user_id: int,
    access: str,
    refresh: str,
    access_expires_at: float,
    refresh_expires_at: float,
    membership_type: int,
    membership_id: str,
    key: str,
) -> None:
    """Encrypt and store OAuth tokens for user_id."""
    access_enc = crypto.encrypt(access, key)
    refresh_enc = crypto.encrypt(refresh, key)
    await db.execute(
        pool,
        "INSERT INTO user_tokens "
        "(user_id, access_token_enc, refresh_token_enc, "
        "access_expires_at, refresh_expires_at, membership_type, membership_id) "
        "VALUES (%s, %s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s), %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "access_token_enc=VALUES(access_token_enc), "
        "refresh_token_enc=VALUES(refresh_token_enc), "
        "access_expires_at=VALUES(access_expires_at), "
        "refresh_expires_at=VALUES(refresh_expires_at), "
        "membership_type=VALUES(membership_type), "
        "membership_id=VALUES(membership_id)",
        (
            user_id,
            access_enc,
            refresh_enc,
            access_expires_at,
            refresh_expires_at,
            membership_type,
            membership_id,
        ),
    )


async def get_tokens(pool, user_id: int, key: str) -> dict | None:
    """Retrieve and decrypt tokens for user_id; return dict or None."""
    row = await db.fetchone(
        pool,
        "SELECT access_token_enc, refresh_token_enc, "
        "UNIX_TIMESTAMP(access_expires_at), UNIX_TIMESTAMP(refresh_expires_at), "
        "membership_type, membership_id "
        "FROM user_tokens WHERE user_id=%s",
        (user_id,),
    )
    if row is None:
        return None
    access_enc, refresh_enc, access_exp, refresh_exp, mtype, mid = row
    # access_enc / refresh_enc may arrive as bytes (BLOB)
    if isinstance(access_enc, str):
        access_enc = access_enc.encode()
    if isinstance(refresh_enc, str):
        refresh_enc = refresh_enc.encode()
    return {
        "access_token": crypto.decrypt(access_enc, key),
        "refresh_token": crypto.decrypt(refresh_enc, key),
        "access_expires_at": float(access_exp) if access_exp is not None else None,
        "refresh_expires_at": float(refresh_exp) if refresh_exp is not None else None,
        "membership_type": mtype,
        "membership_id": mid,
    }


async def delete(pool, user_id: int) -> None:
    """Delete the token row for user_id (used on refresh failure)."""
    await db.execute(pool, "DELETE FROM user_tokens WHERE user_id=%s", (user_id,))


async def update_membership(
    pool,
    user_id: int,
    membership_type: int,
    membership_id: str,
) -> None:
    """Update the membership_type and membership_id for an existing token row."""
    await db.execute(
        pool,
        "UPDATE user_tokens SET membership_type=%s, membership_id=%s WHERE user_id=%s",
        (membership_type, membership_id, user_id),
    )
