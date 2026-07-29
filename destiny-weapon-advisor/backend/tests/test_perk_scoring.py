from app.models import OwnedWeapon, Verdict
from app.perk_ratings import PerkRatings
from app.perk_scoring import score_by_perks, score_weapon


def weapon(perk_names, *, item_hash=100, instance="i1", mw=False, random=True, wtype="Hand Cannon"):
    return OwnedWeapon(
        instance_id=instance, item_hash=item_hash, name="Gun", weapon_type=wtype,
        element="Solar", is_masterworked=mw, is_random_roll=random,
        perks=frozenset(), location="Vault", perk_names=list(perk_names),
    )


def ratings(seed=None, overrides=None):
    return PerkRatings(seed or {}, overrides or {})


SEED = {
    "Incandescent": {"rating": "S", "reason": "ad clear", "tags": ["pve"]},
    "Frenzy": {"rating": "A", "reason": "always on", "tags": ["pve"]},
    "Firefly": {"rating": "B", "reason": "ok", "tags": ["pve"]},
    "Thresh": {"rating": "C", "reason": "minor", "tags": ["pve"]},
    "BadPerk": {"rating": "D", "reason": "avoid", "tags": []},
}


def only(recs, iid):
    return next(r for r in recs if r["weapon"].instance_id == iid)


def test_s_tier_masterworked_is_god_roll():
    r = score_by_perks([weapon(["Incandescent", "Frenzy"], mw=True)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.GOD_ROLL


def test_s_tier_not_masterworked_is_masterwork():
    r = score_by_perks([weapon(["Incandescent"], mw=False)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.MASTERWORK


def test_two_a_perks_is_god_roll_when_masterworked():
    r = score_by_perks([weapon(["Frenzy", "Frenzy"], mw=True)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.GOD_ROLL


def test_single_b_perk_is_good():
    r = score_by_perks([weapon(["Firefly"])], ratings(SEED))[0]
    assert r["verdict"] == Verdict.GOOD


def test_only_c_perk_is_no_data():
    r = score_by_perks([weapon(["Thresh"])], ratings(SEED))[0]
    assert r["verdict"] == Verdict.NO_DATA


def test_d_perk_is_dismantle():
    r = score_by_perks([weapon(["BadPerk"])], ratings(SEED))[0]
    assert r["verdict"] == Verdict.DISMANTLE


def test_unrated_perks_are_no_data():
    r = score_by_perks([weapon(["Arrowhead Brake", "Ricochet Rounds"])], ratings(SEED))[0]
    assert r["verdict"] == Verdict.NO_DATA


def test_weapon_type_override_changes_rating():
    # Frenzy is A by default, but overridden to D specifically on Sniper Rifle.
    over = {("Frenzy", "Sniper Rifle"): {"rating": "D", "reason": "bad here", "tags": []}}
    recs = score_by_perks(
        [weapon(["Frenzy"], instance="hc", wtype="Hand Cannon"),
         weapon(["Frenzy"], instance="sniper", wtype="Sniper Rifle")],
        ratings(SEED, over),
    )
    assert only(recs, "hc")["verdict"] == Verdict.GOOD
    assert only(recs, "sniper")["verdict"] == Verdict.DISMANTLE


def test_note_and_tags_surface_from_rated_perks():
    r = score_by_perks([weapon(["Incandescent"], mw=True)], ratings(SEED))[0]
    assert "Incandescent (S)" in r["note"]
    assert r["tags"] == ["pve"]


# ---------------------------------------------------------------------------
# Crafted potential: score what a shapeable weapon COULD hold, not just what
# is socketed. Gated off by default — turning it on changes verdicts.
# ---------------------------------------------------------------------------

def _crafted(perk_names, trait_pool, masterworked=False):
    return OwnedWeapon(
        instance_id="c1", item_hash=1, name="Crafted Gun", weapon_type="Hand Cannon",
        element="Solar", is_masterworked=masterworked, is_random_roll=True,
        perks=frozenset(), location="Vault", perk_names=perk_names,
        is_crafted=True, trait_pool=trait_pool,
    )


def test_potential_ignored_unless_explicitly_enabled():
    """Default behaviour must be byte-identical to before this feature."""
    w = _crafted(["Meh"], [["Frenzy"], ["Incandescent"]])
    ratings = PerkRatings({
        "Meh": {"rating": "C", "reason": "", "tags": []},
        "Frenzy": {"rating": "A", "reason": "", "tags": []},
        "Incandescent": {"rating": "S", "reason": "", "tags": []},
    }, {})
    verdict, _, _, _ = score_weapon(w, ratings)
    assert verdict == Verdict.NO_DATA          # scored on the socketed C perk


def test_potential_scores_the_best_shapeable_combination():
    w = _crafted(["Meh"], [["Frenzy"], ["Incandescent"]], masterworked=True)
    ratings = PerkRatings({
        "Meh": {"rating": "C", "reason": "", "tags": []},
        "Frenzy": {"rating": "A", "reason": "", "tags": []},
        "Incandescent": {"rating": "S", "reason": "", "tags": []},
    }, {})
    verdict, rated, _, _ = score_weapon(w, ratings, use_potential=True)
    assert verdict == Verdict.GOD_ROLL
    assert {r["name"] for r in rated} == {"Frenzy", "Incandescent"}


def test_potential_two_strong_perks_in_ONE_column_is_not_promoted():
    """The central trap: mutually exclusive perks must count once."""
    w = _crafted(["Meh"], [["Frenzy", "Rampage"]], masterworked=True)
    ratings = PerkRatings({
        "Meh": {"rating": "C", "reason": "", "tags": []},
        "Frenzy": {"rating": "A", "reason": "", "tags": []},
        "Rampage": {"rating": "A", "reason": "", "tags": []},
    }, {})
    verdict, rated, _, _ = score_weapon(w, ratings, use_potential=True)
    assert len(rated) == 1
    assert verdict == Verdict.GOOD             # one A perk, not two


def test_potential_ignored_for_a_weapon_with_no_pool():
    """Non-crafted weapons carry no pool, so the flag changes nothing for them."""
    w = OwnedWeapon(
        instance_id="n1", item_hash=2, name="Normal", weapon_type="Hand Cannon",
        element="Solar", is_masterworked=True, is_random_roll=True,
        perks=frozenset(), location="Vault", perk_names=["Frenzy"],
    )
    ratings = PerkRatings({"Frenzy": {"rating": "A", "reason": "", "tags": []}}, {})
    a, _, _, _ = score_weapon(w, ratings)
    b, _, _, _ = score_weapon(w, ratings, use_potential=True)
    assert a == b == Verdict.GOOD


def test_score_by_perks_forwards_the_potential_flag():
    w = _crafted(["Meh"], [["Frenzy"], ["Incandescent"]], masterworked=True)
    ratings = PerkRatings({
        "Meh": {"rating": "C", "reason": "", "tags": []},
        "Frenzy": {"rating": "A", "reason": "", "tags": []},
        "Incandescent": {"rating": "S", "reason": "", "tags": []},
    }, {})
    off = score_by_perks([w], ratings)[0]
    on = score_by_perks([w], ratings, use_potential=True)[0]
    assert off["verdict"] == Verdict.NO_DATA
    assert on["verdict"] == Verdict.GOD_ROLL
    assert on["scored_from"] == "shapeable"
    assert off["scored_from"] == "current"
