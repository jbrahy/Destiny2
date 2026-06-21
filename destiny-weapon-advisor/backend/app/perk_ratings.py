import json
import sqlite3
from pathlib import Path

_SEED_PATH = Path(__file__).parent / "data" / "perk_ratings_seed.json"

# Higher is better. Used by the perk scorer and to sort the catalog.
TIER_SCORE = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 1}


def load_seed() -> dict:
    data = json.loads(_SEED_PATH.read_text())
    return {name: info for name, info in data.items() if not name.startswith("_")}


class PerkRatings:
    """Resolves a perk's rating, preferring a weapon-type override, then a base
    override, then the seeded base rating."""

    def __init__(self, seed: dict, overrides: dict):
        self._seed = seed
        self._overrides = overrides  # {(perk_name, weapon_type): {rating, reason, tags}}

    def get(self, perk_name: str, weapon_type: str = "") -> dict | None:
        if (perk_name, weapon_type) in self._overrides:
            return self._overrides[(perk_name, weapon_type)]
        if (perk_name, "") in self._overrides:
            return self._overrides[(perk_name, "")]
        if perk_name in self._seed:
            return self._seed[perk_name]
        return None

    def is_override(self, perk_name: str, weapon_type: str) -> bool:
        return (perk_name, weapon_type) in self._overrides


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS perk_ratings ("
        "perk_name TEXT, weapon_type TEXT, rating TEXT, reason TEXT, tags TEXT, "
        "PRIMARY KEY (perk_name, weapon_type))"
    )
    conn.commit()


def load_ratings(conn: sqlite3.Connection) -> PerkRatings:
    _ensure_table(conn)
    overrides: dict = {}
    for name, wtype, rating, reason, tags in conn.execute(
        "SELECT perk_name, weapon_type, rating, reason, tags FROM perk_ratings"
    ):
        overrides[(name, wtype)] = {
            "rating": rating,
            "reason": reason or "",
            "tags": tags.split(",") if tags else [],
        }
    return PerkRatings(load_seed(), overrides)


def save_rating(
    conn: sqlite3.Connection, perk_name: str, weapon_type: str,
    rating: str, reason: str, tags: list[str],
) -> None:
    _ensure_table(conn)
    conn.execute(
        "INSERT INTO perk_ratings (perk_name, weapon_type, rating, reason, tags) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(perk_name, weapon_type) DO UPDATE SET "
        "rating = excluded.rating, reason = excluded.reason, tags = excluded.tags",
        (perk_name, weapon_type, rating, reason or "", ",".join(tags)),
    )
    conn.commit()
