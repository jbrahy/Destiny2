from app.models import OwnedWeapon, Verdict
from app.perk_ratings import PerkRatings, TIER_SCORE


def explain_verdict(
    verdict, rated: list[dict], is_masterworked: bool,
    is_random_roll: bool, dupe_demoted: bool,
) -> tuple[str, str | None]:
    """Explain why `verdict` was chosen and what reaching the next tier takes.
    Derived from the same thresholds score_weapon uses, so it cannot drift."""
    reroll = " (re-roll/craft for a better roll)" if is_random_roll else ""
    strong = [r["name"] for r in rated if TIER_SCORE.get(r["rating"], 0) >= 4]

    if verdict == Verdict.GOD_ROLL:
        names = ", ".join(strong) or "strong perks"
        return f"Top-tier perks ({names}) and masterworked.", None
    if verdict == Verdict.MASTERWORK:
        names = ", ".join(strong) or "strong perks"
        return (f"{len(strong)} A/S-tier perk(s) ({names}) but not masterworked.",
                "Masterwork it → God Roll.")
    if verdict == Verdict.GOOD:
        best = max(rated, key=lambda r: TIER_SCORE.get(r["rating"], 0)) if rated else None
        reason = (
            f"Best perk is {best['rating']}-tier ({best['name']}); "
            "no S-tier and fewer than two A/S perks."
            if best else "No S-tier and fewer than two A/S perks."
        )
        return reason, f"A second A/S-tier perk (or one S-tier perk) → Upgrade{reroll}"
    if verdict == Verdict.NO_DATA:
        if not rated:
            return ("No perk-rating data for this weapon's perks.",
                    "Rate its perks on the Perks tab.")
        return "Only C-tier perks for this weapon type.", f"Any A- or B-tier perk → Good{reroll}"
    if verdict == Verdict.DISMANTLE:
        if dupe_demoted:
            return "A better-perked copy of this weapon exists in your inventory.", None
        return "Only low-value (D-tier) perks.", f"Any A/B-tier perk → Good{reroll}"
    return "", None


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
        verdict = Verdict.GOD_ROLL if weapon.is_masterworked else Verdict.MASTERWORK
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
    keepers = {Verdict.GOD_ROLL, Verdict.MASTERWORK, Verdict.GOOD}
    has_keeper = {r["weapon"].item_hash for r in results if r["verdict"] in keepers}
    for r in results:
        if (
            r["verdict"] == Verdict.NO_DATA
            and r["weapon"].is_random_roll
            and r["weapon"].item_hash in has_keeper
        ):
            r["verdict"] = Verdict.DISMANTLE
            r["note"] = "A better-perked copy of this weapon exists in your inventory."
            r["dupe_demoted"] = True

    for r in results:
        reason, upgrade = explain_verdict(
            r["verdict"], r["rated"], r["weapon"].is_masterworked,
            r["weapon"].is_random_roll, r.get("dupe_demoted", False),
        )
        r["verdictReason"] = reason
        r["upgradePath"] = upgrade
    return results
