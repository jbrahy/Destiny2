from app.models import OwnedWeapon, Verdict
from app.perk_ratings import PerkRatings, TIER_SCORE


def score_weapon(weapon: OwnedWeapon, ratings: PerkRatings):
    """Return (verdict, rated_perks, note, tags) for a single weapon, judging it
    by the ratings of the perks it actually rolled (for its weapon type)."""
    rated = []
    for name in weapon.perk_names:
        info = ratings.get(name, weapon.weapon_type)
        if info:
            rated.append(
                {"name": name, "rating": info["rating"],
                 "reason": info.get("reason", ""), "tags": info.get("tags", [])}
            )
    if not rated:
        return Verdict.NO_DATA, [], "", []

    rated.sort(key=lambda r: TIER_SCORE.get(r["rating"], 0), reverse=True)
    scores = [TIER_SCORE.get(r["rating"], 0) for r in rated]
    best = scores[0]
    strong = sum(1 for s in scores if s >= 4)  # A or S

    if best >= 5 or strong >= 2:
        verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.UPGRADE
    elif best >= 3:  # at least one A or B perk
        verdict = Verdict.GOOD
    elif best == 2:  # only C-tier perks
        verdict = Verdict.NO_DATA
    else:  # only D-tier (avoid) perks
        verdict = Verdict.DISMANTLE

    note = "; ".join(
        f'{r["name"]} ({r["rating"]}): {r["reason"]}' for r in rated[:2] if r["reason"]
    )
    tags = sorted({t for r in rated for t in r["tags"]})
    return verdict, rated, note, tags


def score_by_perks(weapons: list[OwnedWeapon], ratings: PerkRatings) -> list[dict]:
    counts: dict[int, int] = {}
    for w in weapons:
        counts[w.item_hash] = counts.get(w.item_hash, 0) + 1

    results = []
    for w in weapons:
        verdict, rated, note, tags = score_weapon(w, ratings)
        results.append(
            {"weapon": w, "verdict": verdict, "rated": rated, "note": note,
             "tags": tags, "is_duplicate": counts[w.item_hash] > 1}
        )

    # Demote unremarkable random-roll dupes to DISMANTLE when a better copy exists.
    keepers = {Verdict.GOD_ROLL, Verdict.UPGRADE, Verdict.GOOD}
    has_keeper = {r["weapon"].item_hash for r in results if r["verdict"] in keepers}
    for r in results:
        if (
            r["verdict"] == Verdict.NO_DATA
            and r["weapon"].is_random_roll
            and r["weapon"].item_hash in has_keeper
        ):
            r["verdict"] = Verdict.DISMANTLE
            r["note"] = "A better-perked copy of this weapon exists in your inventory."
    return results
