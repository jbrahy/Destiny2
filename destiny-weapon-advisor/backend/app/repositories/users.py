from app import db


async def upsert(
    pool,
    bungie_membership_id: str,
    display_name: str,
    primary_membership_type: int,
    primary_membership_id: str,
) -> int:
    """Insert or update a user by bungie_membership_id; return user_id."""
    await db.execute(
        pool,
        "INSERT INTO users "
        "(bungie_membership_id, display_name, primary_membership_type, primary_membership_id) "
        "VALUES (%s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "display_name=VALUES(display_name), "
        "primary_membership_type=VALUES(primary_membership_type), "
        "primary_membership_id=VALUES(primary_membership_id)",
        (bungie_membership_id, display_name, primary_membership_type, primary_membership_id),
    )
    row = await db.fetchone(
        pool,
        "SELECT user_id FROM users WHERE bungie_membership_id=%s",
        (bungie_membership_id,),
    )
    return row[0]


async def get_by_bungie_id(pool, bungie_membership_id: str) -> dict | None:
    """Return user dict by bungie_membership_id or None if not found."""
    row = await db.fetchone(
        pool,
        "SELECT user_id, bungie_membership_id, display_name, "
        "primary_membership_type, primary_membership_id, status "
        "FROM users WHERE bungie_membership_id=%s",
        (bungie_membership_id,),
    )
    if row is None:
        return None
    return {
        "user_id": row[0],
        "bungie_membership_id": row[1],
        "display_name": row[2],
        "primary_membership_type": row[3],
        "primary_membership_id": row[4],
        "status": row[5],
    }


async def get(pool, user_id: int) -> dict | None:
    """Return user dict or None if not found."""
    row = await db.fetchone(
        pool,
        "SELECT user_id, bungie_membership_id, display_name, "
        "primary_membership_type, primary_membership_id, status "
        "FROM users WHERE user_id=%s",
        (user_id,),
    )
    if row is None:
        return None
    return {
        "user_id": row[0],
        "bungie_membership_id": row[1],
        "display_name": row[2],
        "primary_membership_type": row[3],
        "primary_membership_id": row[4],
        "status": row[5],
    }
