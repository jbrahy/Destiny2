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
ARMOR_STATS = ("Health", "Melee", "Grenade", "Super", "Class", "Weapons")
MAX_FOCUS = 3


def parse_focus(raw) -> list[str]:
    """Validate a chosen stat focus: 0-3 armour stats, duplicates collapsed.

    Accepts a comma-separated string (query param) or a list (JSON body).
    Empty means "no focus" — the seeded per-build priority applies — which is a
    fallback, not an error. An unknown name raises rather than being dropped:
    a silent drop would quietly change which armour you get off a typo.
    """
    if raw is None:
        return []
    names = raw.split(",") if isinstance(raw, str) else list(raw)
    picked: list[str] = []
    for name in names:
        name = name.strip()
        if not name:
            continue
        if name not in ARMOR_STATS:
            raise ValueError(
                f"{name!r} is not an armour stat. Choose from: {', '.join(ARMOR_STATS)}."
            )
        if name not in picked:
            picked.append(name)
    if len(picked) > MAX_FOCUS:
        raise ValueError(f"Choose at most {MAX_FOCUS} stats to focus on.")
    return picked


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
    focus: list[str] | None = None,
) -> dict:
    """One complete outfit: 5 armour slots + 3 ammo slots, each obeying the
    one-exotic rule. Slots with nothing owned are None rather than invented.

    `focus` is the stats the player asked for. It replaces the build's seeded
    priority outright — which means every subclass of a class gets the same
    armour, because armour is class-locked, not subclass-locked. Weapons still
    vary by subclass, since those key off the damage element.
    """
    priority = focus or build.get("statPriority", [])

    # Armour is class-locked: Warlock gear never appears in a Titan outfit.
    mine = [a for a in armor if a.get("className") == class_name]
    armor_by_slot = {slot: [a for a in mine if a.get("slot") == slot] for slot in ARMOR_SLOTS}
    chosen_armor = pick_with_one_exotic(armor_by_slot, _armor_score(priority))

    element = element_for_subclass(subclass)
    # No truncation: a top-5 cut runs BEFORE the solver splits legendary from
    # exotic, so a slot whose five best are all exotic would lose its legendary
    # fallback and render empty even though the player owns twenty of them.
    ranked = recommend_weapons(
        weapons, {"label": subclass, "element": element}, top_n=len(weapons) or 1,
    )
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


def plan_apply(outfit: dict, target: str, locate) -> list[dict]:
    """What equipping this outfit would do to each item — without doing it.

    Mirrors `_move_one`'s rules exactly so the preview can never promise
    something the run will refuse. `locate(instance_id)` returns the same
    shape `_find_item_location` does: "vault", a character id,
    "equipped:<character id>", or None when the item is not in the cached
    profile.

    Empty slots produce no entry at all — a slot you own nothing for is not a
    failure the user can act on, and listing it as one is noise.
    """
    plan = []
    slots = [(s, outfit["armor"].get(s)) for s in ARMOR_SLOTS]
    slots += [(s, outfit["weapons"].get(s)) for s in AMMO_SLOTS]

    for slot, item in slots:
        if item is None:
            continue
        where = locate(item["instanceId"])
        if where is None:
            action, reason = "blocked", "Not in your cached inventory — refresh it."
        elif where == f"equipped:{target}":
            action, reason = "skip", "Already equipped."
        elif isinstance(where, str) and where.startswith("equipped:"):
            action, reason = "blocked", "Equipped on another character — unequip it there first."
        else:
            action, reason = "move", "Will be transferred and equipped."
        plan.append({
            "slot": slot,
            "instanceId": item["instanceId"],
            "itemHash": item["itemHash"],
            "name": item["name"],
            "isExotic": item.get("isExotic", False),
            "action": action,
            "reason": reason,
        })
    return plan


def build_all_outfits(
    builds: dict, weapons: list[dict], armor: list[dict], focus: list[str] | None = None,
) -> list[dict]:
    """One outfit per seeded "Class|Subclass" build, in sorted key order."""
    outfits = []
    for key in sorted(k for k in builds if not k.startswith("_")):
        class_name, _, subclass = key.partition("|")
        outfits.append(build_outfit(class_name, subclass, weapons, armor, builds[key], focus))
    return outfits
