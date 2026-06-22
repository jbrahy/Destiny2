import json
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

    def notes(self, perk_name: str, weapon_type: str) -> str:
        for key in ((perk_name, weapon_type), (perk_name, "")):
            if key in self._overrides:
                return self._overrides[key].get("notes", "")
        return ""

    def is_override(self, perk_name: str, weapon_type: str) -> bool:
        return (perk_name, weapon_type) in self._overrides
