from app.models import OwnedWeapon, Recommendation, Verdict, Wishlist, WishlistRoll


def _best_god_match(
    weapon: OwnedWeapon, rolls: list[WishlistRoll]
) -> tuple[WishlistRoll | None, list[int], bool]:
    """Return (roll, matched_perks) for the strongest match, or (None, [])."""
    best_roll = None
    best_matched: list[int] = []
    best_full = False
    for roll in rolls:
        matched = weapon.perks & roll.perks
        if not matched:
            continue
        is_full = roll.perks <= weapon.perks
        if is_full and not best_full:
            best_roll, best_matched, best_full = roll, sorted(matched), True
        elif is_full and best_full and len(matched) > len(best_matched):
            best_roll, best_matched = roll, sorted(matched)
        elif not best_full and len(matched) > len(best_matched):
            best_roll, best_matched = roll, sorted(matched)
    return best_roll, best_matched, best_full


def _trash_match(weapon: OwnedWeapon, rolls: list[WishlistRoll]) -> WishlistRoll | None:
    for roll in rolls:
        if roll.perks and roll.perks <= weapon.perks:
            return roll
    return None


def score_inventory(weapons: list[OwnedWeapon], wishlist: Wishlist) -> list[Recommendation]:
    counts: dict[int, int] = {}
    for w in weapons:
        counts[w.item_hash] = counts.get(w.item_hash, 0) + 1

    # Pass 1: base verdicts.
    base: list[Recommendation] = []
    for w in weapons:
        is_dupe = counts[w.item_hash] > 1
        roll, matched, full = _best_god_match(w, wishlist.rolls_by_item.get(w.item_hash, []))
        # Trash demotion never overrides a FULL god-roll match: a god roll that
        # happens to contain a trash-flagged perk as a subset must not be dismantled.
        trash = _trash_match(w, wishlist.trash_by_item.get(w.item_hash, []))
        if trash is not None and not full:
            base.append(Recommendation(w, Verdict.DISMANTLE, sorted(trash.perks),
                                       trash.notes, sorted(trash.tags), is_dupe))
            continue
        if roll is None:
            base.append(Recommendation(w, Verdict.NO_DATA, [], "", [], is_dupe))
        elif full:
            verdict = Verdict.GOD_ROLL if w.is_masterworked else Verdict.UPGRADE
            base.append(Recommendation(w, verdict, matched, roll.notes, sorted(roll.tags), is_dupe))
        else:
            base.append(Recommendation(w, Verdict.GOOD, matched, roll.notes, sorted(roll.tags), is_dupe))

    # Pass 2: demote random-roll NO_DATA weapons to DISMANTLE when a better
    # sibling of the same item exists.
    keepers = {Verdict.GOD_ROLL, Verdict.UPGRADE, Verdict.GOOD}
    has_keeper = {r.weapon.item_hash for r in base if r.verdict in keepers}
    for rec in base:
        if (
            rec.verdict == Verdict.NO_DATA
            and rec.weapon.is_random_roll
            and rec.weapon.item_hash in has_keeper
        ):
            rec.verdict = Verdict.DISMANTLE
            rec.note = "A better copy of this weapon exists in your inventory."
    return base
