"""Per-user perk rating repository backed by MySQL user_perk_ratings table."""
import json
from pathlib import Path

from app import db
from app.perk_ratings import PerkRatings, load_seed

_DEFAULTS_PATH = Path(__file__).parent.parent / "data" / "perk_ratings_default.json"


async def load(pool, user_id: int) -> PerkRatings:
    """Load a PerkRatings instance seeded from the JSON seed, overridden by this user's DB rows."""
    rows = await db.fetchall(
        pool,
        "SELECT perk_name, weapon_type, rating, reason, tags, notes "
        "FROM user_perk_ratings WHERE user_id=%s",
        (user_id,),
    )
    overrides: dict = {}
    for perk_name, weapon_type, rating, reason, tags, notes in rows:
        overrides[(perk_name, weapon_type)] = {
            "rating": rating,
            "reason": reason or "",
            "tags": tags.split(",") if tags else [],
            "notes": notes or "",
        }
    return PerkRatings(load_seed(), overrides)


async def seed_defaults(pool, user_id: int) -> None:
    """Seed the default perk rating overrides for a brand-new user.

    Loads entries from perk_ratings_default.json and upserts each one.
    Idempotent: the underlying save() uses INSERT ... ON DUPLICATE KEY UPDATE,
    so calling this multiple times will not duplicate rows.
    """
    defaults = json.loads(_DEFAULTS_PATH.read_text())
    for entry in defaults:
        await save(
            pool,
            user_id,
            entry["perk_name"],
            entry.get("weapon_type", ""),
            entry["rating"],
            entry.get("reason", ""),
            entry.get("tags", []),
            entry.get("notes", ""),
        )


async def save(
    pool,
    user_id: int,
    perk_name: str,
    weapon_type: str,
    rating: str,
    reason: str,
    tags: list,
    notes: str,
) -> None:
    """Upsert a single perk rating override for this user."""
    tags_str = ",".join(tags) if tags else ""
    await db.execute(
        pool,
        "INSERT INTO user_perk_ratings "
        "(user_id, perk_name, weapon_type, rating, reason, tags, notes) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE "
        "rating=VALUES(rating), reason=VALUES(reason), "
        "tags=VALUES(tags), notes=VALUES(notes)",
        (user_id, perk_name, weapon_type, rating, reason or "", tags_str, notes or ""),
    )
