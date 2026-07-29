"""Per-user item tags, loadouts, and armor sets repositories backed by MySQL."""
import json

from app import db


# ---------------------------------------------------------------------------
# Item tags
# ---------------------------------------------------------------------------

async def get_tags(pool, user_id: int) -> dict:
    """Return {instance_id: tag} for this user."""
    rows = await db.fetchall(
        pool,
        "SELECT instance_id, tag FROM user_item_tags WHERE user_id=%s",
        (user_id,),
    )
    return {instance_id: tag for instance_id, tag in rows}


async def set_tag(pool, user_id: int, instance_id: str, tag: str) -> None:
    """Upsert a tag for an item instance; if tag is falsy, delete the row."""
    if tag:
        await db.execute(
            pool,
            "INSERT INTO user_item_tags (user_id, instance_id, tag) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE tag=VALUES(tag)",
            (user_id, instance_id, tag),
        )
    else:
        await db.execute(
            pool,
            "DELETE FROM user_item_tags WHERE user_id=%s AND instance_id=%s",
            (user_id, instance_id),
        )


# ---------------------------------------------------------------------------
# Loadouts
# ---------------------------------------------------------------------------

async def get_loadouts(pool, user_id: int) -> list:
    """Return list of loadout dicts, each including the 'name' key."""
    rows = await db.fetchall(
        pool,
        "SELECT name, data FROM user_loadouts WHERE user_id=%s",
        (user_id,),
    )
    return [{"name": name, **json.loads(data)} for name, data in rows]


async def save_loadout(pool, user_id: int, name: str, data_dict: dict) -> None:
    """Upsert a loadout by name for this user."""
    await db.execute(
        pool,
        "INSERT INTO user_loadouts (user_id, name, data) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE data=VALUES(data)",
        (user_id, name, json.dumps(data_dict)),
    )


async def delete_loadout(pool, user_id: int, name: str) -> None:
    """Delete a loadout by name for this user."""
    await db.execute(
        pool,
        "DELETE FROM user_loadouts WHERE user_id=%s AND name=%s",
        (user_id, name),
    )


# ---------------------------------------------------------------------------
# Armor sets
# ---------------------------------------------------------------------------

async def get_armor_sets(pool, user_id: int) -> list:
    """Return list of armor set dicts, each including the 'name' key."""
    rows = await db.fetchall(
        pool,
        "SELECT name, data FROM user_armor_sets WHERE user_id=%s",
        (user_id,),
    )
    return [{"name": name, **json.loads(data)} for name, data in rows]


async def save_armor_set(pool, user_id: int, name: str, data_dict: dict) -> None:
    """Upsert an armor set by name for this user."""
    await db.execute(
        pool,
        "INSERT INTO user_armor_sets (user_id, name, data) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE data=VALUES(data)",
        (user_id, name, json.dumps(data_dict)),
    )


async def delete_armor_set(pool, user_id: int, name: str) -> None:
    """Delete an armor set by name for this user."""
    await db.execute(
        pool,
        "DELETE FROM user_armor_sets WHERE user_id=%s AND name=%s",
        (user_id, name),
    )


# ---------------------------------------------------------------------------
# Dismantle sweeps
# ---------------------------------------------------------------------------


async def stage_sweep_items(pool, user_id: int, membership_id: str, rows: list[tuple[str, bool]]) -> None:
    """Record staged items and the lock state each held before the sweep, so
    undo can put it back exactly as it was. Keyed by membership_id as well as
    user_id: a user can hold sweeps staged against more than one Destiny
    account, and rows from one must never bleed into another's undo."""
    if not rows:
        return
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO user_sweep_items (user_id, membership_id, instance_id, was_locked) "
            "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE was_locked=VALUES(was_locked)",
            [(user_id, membership_id, instance_id, int(was_locked)) for instance_id, was_locked in rows],
        )
        await conn.commit()


async def get_staged_sweep(pool, user_id: int, membership_id: str) -> dict[str, bool]:
    """Return {instance_id: was_locked} for this user's currently staged sweep
    on the given Destiny membership."""
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT instance_id, was_locked FROM user_sweep_items WHERE user_id=%s AND membership_id=%s",
            (user_id, membership_id),
        )
        rows = await cur.fetchall()
    return {instance_id: bool(was_locked) for instance_id, was_locked in rows}


async def clear_sweep_items(pool, user_id: int, membership_id: str, instance_ids: list[str]) -> None:
    """Drop staged rows — after a successful undo, or once the user confirms
    the batch was dismantled in-game."""
    if not instance_ids:
        return
    placeholders = ", ".join(["%s"] * len(instance_ids))
    async with pool.acquire() as conn, conn.cursor() as cur:
        await cur.execute(
            f"DELETE FROM user_sweep_items WHERE user_id=%s AND membership_id=%s AND instance_id IN ({placeholders})",
            (user_id, membership_id, *instance_ids),
        )
        await conn.commit()
