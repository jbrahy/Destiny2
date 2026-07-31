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

    Fewer than three stats simply sums what exists; negative values (Health
    really can be -2) sort to the bottom and are excluded by the slice.
    """
    return sum(sorted(stats.values(), reverse=True)[:3])


def waste(stats: dict[str, int]) -> int:
    """Everything outside the top 3 — stat points the archetype threw away."""
    return sum(stats.values()) - focus(stats)


def load_bands() -> dict[str, int]:
    """Focus thresholds, editable in app/data/armor_scoring_seed.json."""
    return json.loads(_SEED_PATH.read_text())["bands"]


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
