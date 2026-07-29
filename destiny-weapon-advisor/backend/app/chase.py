"""Weapons worth farming: the roll pool allows a better roll than you own.

The manifest's trait pool is identical for every copy of a weapon, so it cannot
say whether YOUR copy is worth keeping — that is what the verdict engine does.
What it can say is what a weapon is capable of, which is the question a chase
list answers: "can this roll better than the one in my vault?"

Pure: stdlib + app modules, no I/O.
"""
from app.models import OwnedWeapon, Verdict
from app.perk_ratings import TIER_SCORE
from app.perk_scoring import score_weapon
from app.roll_pool import trait_columns

# Ranked worst to best so "is this ceiling better than what I own" is a compare.
_VERDICT_ORDER = [
    Verdict.DISMANTLE, Verdict.NO_DATA, Verdict.GOOD,
    Verdict.MASTERWORK, Verdict.GOD_ROLL,
]
_RANK = {v: i for i, v in enumerate(_VERDICT_ORDER)}


def best_possible(item_hash: int, weapon_type: str, manifest, ratings):
    """The best verdict this weapon could ever reach, and the perks that get there.

    One perk per column — perks in a column are mutually exclusive, so a union
    would let two A-tier perks in the same column satisfy `strong >= 2` and fake
    a god roll nobody can actually hold.

    Masterwork is assumed: it is always attainable, so it belongs in a ceiling.
    Scoring goes through the real `score_weapon`, so the ceiling can never drift
    from the verdicts shown everywhere else.
    """
    columns = trait_columns(item_hash, manifest, only_current=True)
    best_names: list[str] = []
    for names in columns:
        rated = [(TIER_SCORE.get(info["rating"], 0), n)
                 for n in names
                 for info in [ratings.get(n, weapon_type)] if info]
        if rated:
            best_names.append(max(rated)[1])
    if not best_names:
        return None, []

    ceiling_weapon = OwnedWeapon(
        instance_id="", item_hash=item_hash, name="", weapon_type=weapon_type,
        element="", is_masterworked=True, is_random_roll=True,
        perks=frozenset(), location="", perk_names=best_names,
    )
    verdict, _, _, _ = score_weapon(ceiling_weapon, ratings)
    return verdict, best_names


def chase_candidates(weapons: list[OwnedWeapon], manifest, ratings) -> list[dict]:
    """Weapons you own whose ceiling beats the best copy in your vault.

    Only weapons already in the vault are considered: those are the ones you can
    actually farm more of, and it bounds the work to your inventory rather than
    every weapon in the manifest.
    """
    by_hash: dict[int, list[OwnedWeapon]] = {}
    for weapon in weapons:
        by_hash.setdefault(weapon.item_hash, []).append(weapon)

    rows = []
    for item_hash, copies in by_hash.items():
        weapon_type = copies[0].weapon_type
        ceiling, chase_perks = best_possible(item_hash, weapon_type, manifest, ratings)
        if ceiling is None:
            continue

        owned_best = max(
            (score_weapon(c, ratings)[0] for c in copies),
            key=lambda v: _RANK.get(v, 0),
        )
        if _RANK.get(ceiling, 0) <= _RANK.get(owned_best, 0):
            continue
        # Only surface a genuinely top-tier ceiling; "you could roll a GOOD one"
        # is not worth a farming session.
        if _RANK.get(ceiling, 0) < _RANK[Verdict.MASTERWORK]:
            continue

        rows.append({
            "itemHash": item_hash,
            # Display fields from the manifest: it is their authority, and it
            # does not depend on which copy happens to be first.
            "name": manifest.name(item_hash),
            "icon": manifest.icon(item_hash),
            "weaponType": weapon_type,
            "ceiling": ceiling.value,
            "ownedBest": owned_best.value,
            "chasePerks": chase_perks,
            "haveCount": len(copies),
        })

    rows.sort(key=lambda r: (-_RANK.get(Verdict(r["ceiling"]), 0), r["name"]))
    return rows
