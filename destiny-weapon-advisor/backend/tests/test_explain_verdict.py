from app.models import Verdict
from app.perk_scoring import explain_verdict


def _rated(*pairs):
    # pairs: (name, rating). Returned best-first is the caller's job; tests pass sorted.
    return [{"name": n, "rating": r, "reason": "", "tags": []} for n, r in pairs]


def test_god_roll_reason_and_no_upgrade_path():
    reason, upgrade = explain_verdict(
        Verdict.GOD_ROLL, _rated(("Frenzy", "S"), ("Killing Wind", "A")),
        is_masterworked=True, is_random_roll=True, dupe_demoted=False,
    )
    assert "Frenzy" in reason and "masterworked" in reason
    assert upgrade is None


def test_upgrade_path_is_masterwork():
    reason, upgrade = explain_verdict(
        Verdict.MASTERWORK, _rated(("Frenzy", "S"), ("Killing Wind", "A")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "not masterworked" in reason
    assert upgrade == "Masterwork it → God Roll."


def test_good_path_mentions_second_strong_perk_and_reroll_for_random():
    reason, upgrade = explain_verdict(
        Verdict.GOOD, _rated(("Outlaw", "B")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "B-tier" in reason and "Outlaw" in reason
    assert upgrade.startswith("A second A/S-tier perk")
    assert "re-roll/craft" in upgrade
    assert "→ Masterwork → God Roll" in upgrade


def test_good_path_no_reroll_suffix_for_fixed_roll():
    _, upgrade = explain_verdict(
        Verdict.GOOD, _rated(("Outlaw", "B")),
        is_masterworked=False, is_random_roll=False, dupe_demoted=False,
    )
    assert "re-roll/craft" not in upgrade


def test_no_data_empty_vs_c_tier():
    empty_reason, empty_up = explain_verdict(
        Verdict.NO_DATA, [], is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "No perk-rating data" in empty_reason
    assert empty_up == "Rate its perks on the Perks tab."

    c_reason, c_up = explain_verdict(
        Verdict.NO_DATA, _rated(("Some Perk", "C")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=False,
    )
    assert "C-tier" in c_reason
    assert c_up.startswith("Any A- or B-tier perk → Good")


def test_dismantle_dupe_vs_d_tier():
    dupe_reason, dupe_up = explain_verdict(
        Verdict.DISMANTLE, _rated(("Bad Perk", "D")),
        is_masterworked=False, is_random_roll=True, dupe_demoted=True,
    )
    assert "better-perked copy" in dupe_reason
    assert dupe_up is None

    d_reason, d_up = explain_verdict(
        Verdict.DISMANTLE, _rated(("Bad Perk", "D")),
        is_masterworked=False, is_random_roll=False, dupe_demoted=False,
    )
    assert "D-tier" in d_reason
    assert d_up == "Any A/B-tier perk → Good"


def test_unknown_verdict_is_safe():
    assert explain_verdict("weird", [], False, False, False) == ("", None)


from app.models import OwnedWeapon
from app.perk_ratings import PerkRatings
from app.perk_scoring import score_by_perks


def _ratings(mapping):
    # mapping: {perk_name: rating}. Build a PerkRatings that returns it for any type.
    class _R(PerkRatings):
        def __init__(self):
            pass
        def get(self, name, weapon_type):
            r = mapping.get(name)
            return {"rating": r, "reason": "", "tags": []} if r else None
    return _R()


def _weapon(instance_id, perks, mw=False, random=True, item_hash=1):
    return OwnedWeapon(
        instance_id=instance_id, item_hash=item_hash, name="Gun", weapon_type="Hand Cannon",
        element="Void", is_masterworked=mw, is_random_roll=random, perks=frozenset(),
        location="Vault", perk_names=perks,
    )


def test_score_by_perks_populates_explanation_fields():
    ratings = _ratings({"Frenzy": "S", "Outlaw": "B"})
    results = score_by_perks([_weapon("a", ["Frenzy"], mw=False)], ratings)
    r = results[0]
    assert r["verdictReason"]
    assert r["upgradePath"] == "Masterwork it → God Roll."  # S perk, not masterworked → Upgrade
