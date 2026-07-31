"""Per-user builds and activities repository backed by MySQL."""
import json

from app import db
from app.builds import _seed_builds, _seed_activities


async def load_builds(pool, user_id: int) -> dict:
    """Seeded builds overlaid with this user's saved overrides."""
    builds = _seed_builds()
    rows = await db.fetchall(
        pool,
        "SELECT build_key, data FROM user_builds WHERE user_id=%s",
        (user_id,),
    )
    for build_key, data in rows:
        # Merge, don't replace: rows saved before a field was added to the seed
        # would otherwise drop it forever. statPriority was added after users
        # had already saved overrides.
        builds[build_key] = {**builds.get(build_key, {}), **json.loads(data)}
    return builds


async def save_build(pool, user_id: int, key: str, data: dict) -> None:
    """Upsert a build override for this user."""
    await db.execute(
        pool,
        "INSERT INTO user_builds (user_id, build_key, data) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE data=VALUES(data)",
        (user_id, key, json.dumps(data)),
    )


async def load_activities(pool, user_id: int) -> list:
    """Seeded activities overlaid with this user's overrides, plus user-only activities appended."""
    rows = await db.fetchall(
        pool,
        "SELECT name, data FROM user_activities WHERE user_id=%s",
        (user_id,),
    )
    overrides = {name: json.loads(data) for name, data in rows}

    result, seen = [], set()
    for activity in _seed_activities():
        name = activity["name"]
        seen.add(name)
        result.append(overrides.get(name, activity))
    for name, data in overrides.items():
        if name not in seen:
            result.append(data)
    return result


async def save_activity(pool, user_id: int, name: str, data: dict) -> None:
    """Upsert an activity override for this user."""
    await db.execute(
        pool,
        "INSERT INTO user_activities (user_id, name, data) VALUES (%s, %s, %s) "
        "ON DUPLICATE KEY UPDATE data=VALUES(data)",
        (user_id, name, json.dumps(data)),
    )
