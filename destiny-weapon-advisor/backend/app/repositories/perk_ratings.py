"""Per-user perk rating repository backed by MySQL user_perk_ratings table."""
from app import db
from app.perk_ratings import PerkRatings, load_seed


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
