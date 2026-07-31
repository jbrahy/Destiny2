"""Complete, equippable outfits — one per class/subclass combination.

Destiny allows exactly ONE exotic armour piece and ONE exotic weapon equipped.
A greedy per-slot pick ignores that and produces outfits the player cannot
equip, so the exotic allowance is solved exactly: 5 armour and 3 weapon slots
is a small enough space that there is no reason to approximate.

Pure: stdlib + app modules only. Read-only — nothing here writes to Bungie.
"""
from app.recommend import _VERDICT_TIER, element_for_subclass, recommend_weapons

ARMOR_SLOTS = ("Helmet", "Gauntlets", "Chest Armor", "Leg Armor", "Class Item")
AMMO_SLOTS = ("Primary", "Special", "Heavy")


def pick_with_one_exotic(by_slot: dict[str, list[dict]], score) -> dict[str, dict | None]:
    """Best item per slot, spending the single exotic allowance where it gains most.

    Starts from the best legendary in every slot, then swaps in exactly one
    exotic — whichever swap improves the score by the largest margin. A slot
    whose only options are exotic is filled only if it wins that contest;
    otherwise it is left empty, because two exotics cannot both be worn.

    `score` MUST return a single number (int or float), not a tuple: the
    exotic allowance is decided by subtracting scores across slots, and
    tuples cannot be subtracted or compared with `>`.
    """
    chosen: dict[str, dict | None] = {}
    gains: list[tuple[float, str, dict]] = []

    for slot, items in by_slot.items():
        legendary = [i for i in items if not i.get("isExotic")]
        exotic = [i for i in items if i.get("isExotic")]
        best_legendary = max(legendary, key=score) if legendary else None
        chosen[slot] = best_legendary
        if exotic:
            best_exotic = max(exotic, key=score)
            baseline = score(best_legendary) if best_legendary else 0
            gains.append((score(best_exotic) - baseline, slot, best_exotic))

    if gains:
        gain, slot, item = max(gains, key=lambda g: g[0])
        if gain > 0 or chosen[slot] is None:
            chosen[slot] = item
    return chosen


def _armor_score(priority: list[str]):
    """Score armour by the build's priority stats, tie-broken on overall focus.

    A single number, not a tuple: the exotic solver subtracts scores to find
    which slot the one exotic allowance gains most in, and tuples cannot be
    subtracted. The multiplier is safe because focus is the sum of the three
    highest armour stats, each capped around 40 — it cannot reach 1000.
    """
    def score(piece: dict) -> int:
        stats = piece.get("stats", {})
        on_priority = sum(stats.get(s, 0) for s in priority)
        return on_priority * 1000 + piece.get("focus", 0)
    return score


def _weapon_score(element: str | None):
    """Score a weapon on the same signals recommend_weapons ranks by.

    The solver compares gains across ammo slots, so the score has to be
    commensurable between them — a per-slot ordinal position is not, and
    made every slot's exotic look equally worth its allowance.
    """
    def score(w: dict) -> int:
        tier = _VERDICT_TIER.get(w.get("verdict"), 0)
        if element and w.get("element") == element:
            tier += 1                      # the same synergy bonus recommend_weapons grants
        return (
            tier * 1_000_000
            + min(len(w.get("matchedPerks", [])), 9) * 100_000
            + (50_000 if w.get("isMasterworked") else 0)
            + int(w.get("power", 0))
        )
    return score


def build_outfit(
    class_name: str, subclass: str, weapons: list[dict], armor: list[dict], build: dict,
) -> dict:
    """One complete outfit: 5 armour slots + 3 ammo slots, each obeying the
    one-exotic rule. Slots with nothing owned are None rather than invented."""
    priority = build.get("statPriority", [])

    # Armour is class-locked: Warlock gear never appears in a Titan outfit.
    mine = [a for a in armor if a.get("className") == class_name]
    armor_by_slot = {slot: [a for a in mine if a.get("slot") == slot] for slot in ARMOR_SLOTS}
    chosen_armor = pick_with_one_exotic(armor_by_slot, _armor_score(priority))

    element = element_for_subclass(subclass)
    ranked = recommend_weapons(weapons, {"label": subclass, "element": element}, top_n=5)
    weapons_by_slot = {slot: ranked["slots"].get(slot, []) for slot in AMMO_SLOTS}
    chosen_weapons = pick_with_one_exotic(weapons_by_slot, _weapon_score(element))

    return {
        "className": class_name,
        "subclass": subclass,
        "statPriority": priority,
        "build": build,
        "armor": chosen_armor,
        "weapons": chosen_weapons,
    }


def build_all_outfits(builds: dict, weapons: list[dict], armor: list[dict]) -> list[dict]:
    """One outfit per seeded "Class|Subclass" build, in sorted key order."""
    outfits = []
    for key in sorted(k for k in builds if not k.startswith("_")):
        class_name, _, subclass = key.partition("|")
        outfits.append(build_outfit(class_name, subclass, weapons, armor, builds[key]))
    return outfits
