from app.models import OwnedWeapon, Verdict
from app.perk_ratings import PerkRatings
from app.perk_scoring import score_by_perks


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


def test_s_tier_not_masterworked_is_upgrade():
    r = score_by_perks([weapon(["Incandescent"], mw=False)], ratings(SEED))[0]
    assert r["verdict"] == Verdict.UPGRADE


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
