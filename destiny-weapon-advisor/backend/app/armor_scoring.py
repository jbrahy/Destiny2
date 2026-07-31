"""Objective armour scoring.

Armour rolls archetype-spiky: two or three stats at 25-35 and the rest pinned
at 5-6. Three pieces all totalling 103 can have wildly different usable output,
so total stats -- what the old frontend heuristic used -- is close to
meaningless. `focus` (the top 3 stats) is what a piece actually gives you.

Judged against fixed thresholds rather than against the player's own best
piece, so a verdict never silently changes as their collection improves.

Pure: stdlib + app.models only.
"""
import json
from pathlib import Path

from app.models import ArmorPiece, ArmorVerdict

_SEED_PATH = Path(__file__).parent / "data" / "armor_scoring_seed.json"


def focus(stats: dict[str, int]) -> int:
    """Sum of the top 3 stats — a piece's usable output.

    Fewer than three stats simply sums what exists. With 3+ stats, a negative
    value (Health really can be -2) sorts to the bottom and is excluded by
    the slice, as intended. With FEWER than 3 stats the slice cannot exclude
    anything, so a negative is included and drags focus down — e.g.
    {"Health": -2, "Melee": 5} -> focus 3, not 5. Real armour always carries
    all 6 stats, so this regime does not occur in practice.
    """
    return sum(sorted(stats.values(), reverse=True)[:3])


def waste(stats: dict[str, int]) -> int:
    """Everything outside the top 3 — stat points the archetype threw away."""
    return sum(stats.values()) - focus(stats)


def load_bands(path: Path | None = None) -> dict[str, int]:
    """Focus thresholds, editable in app/data/armor_scoring_seed.json.

    Validates the loaded bands so a malformed hand-edit fails loudly here,
    at load time, rather than silently misclassifying every piece (e.g. a
    `good` threshold above `top_roll` makes GOOD unreachable) or raising a
    bare KeyError deep inside score_armor for a missing key.
    """
    seed_path = path or _SEED_PATH
    bands = json.loads(seed_path.read_text())["bands"]
    required = {"top_roll", "good", "ok"}
    missing = required - bands.keys()
    if missing:
        raise ValueError(f"{seed_path}: missing band key(s): {sorted(missing)}")
    if not (bands["top_roll"] >= bands["good"] >= bands["ok"]):
        raise ValueError(
            f"{seed_path}: bands must satisfy top_roll >= good >= ok, got {bands}"
        )
    return bands


def score_armor(piece: ArmorPiece, bands: dict[str, int]) -> ArmorVerdict:
    """Objective verdict for one piece.

    Exotics are always a keep: they are build-defining and cannot be re-rolled,
    so scoring their stat roll would be answering the wrong question.
    """
    if piece.is_exotic:
        return ArmorVerdict.EXOTIC
    value = focus(piece.stats)
    if value >= bands["top_roll"]:
        return ArmorVerdict.TOP_ROLL
    if value >= bands["good"]:
        return ArmorVerdict.GOOD
    if value >= bands["ok"]:
        return ArmorVerdict.OK
    return ArmorVerdict.DISMANTLE
