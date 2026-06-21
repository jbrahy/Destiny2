from app.models import OwnedWeapon, Verdict, Wishlist, WishlistRoll
from app.scoring import score_inventory


def weapon(perks, *, item_hash=100, instance="i1", mw=False, random=True, name="Gun"):
    return OwnedWeapon(
        instance_id=instance,
        item_hash=item_hash,
        name=name,
        weapon_type="Hand Cannon",
        element="Solar",
        is_masterworked=mw,
        is_random_roll=random,
        perks=frozenset(perks),
        location="Vault",
    )


def wl(god=None, trash=None):
    return Wishlist(rolls_by_item=god or {}, trash_by_item=trash or {})


def test_full_match_masterworked_is_god_roll():
    w = weapon([1, 2, 3], mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "great pve", tags=frozenset({"pve"}))]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.GOD_ROLL
    assert set(rec.matched_perks) == {2, 3}
    assert rec.note == "great pve"
    assert rec.tags == ["pve"]


def test_full_match_not_masterworked_is_upgrade():
    w = weapon([1, 2, 3], mw=False)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    assert score_inventory([w], lists)[0].verdict == Verdict.UPGRADE


def test_partial_match_is_good():
    w = weapon([1, 2], mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.GOOD
    assert rec.matched_perks == [2]


def test_no_wishlist_entry_is_no_data():
    w = weapon([1, 2])
    assert score_inventory([w], wl())[0].verdict == Verdict.NO_DATA


def test_trash_roll_is_dismantle():
    w = weapon([7, 8])
    lists = wl(trash={100: [WishlistRoll(100, frozenset({7, 8}), "bad", is_trash=True)]})
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.DISMANTLE
    assert rec.note == "bad"


def test_random_dupe_with_better_sibling_is_dismantle():
    keeper = weapon([2, 3], instance="keep", mw=True)
    junk = weapon([4, 5], instance="junk")
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    recs = {r.weapon.instance_id: r for r in score_inventory([keeper, junk], lists)}
    assert recs["keep"].verdict == Verdict.GOD_ROLL
    assert recs["junk"].verdict == Verdict.DISMANTLE
    assert recs["keep"].is_duplicate is True


def test_exotic_no_match_stays_no_data_not_dismantle():
    a = weapon([4, 5], instance="a", random=False)
    b = weapon([2, 3], instance="b", random=False, mw=True)
    lists = wl(god={100: [WishlistRoll(100, frozenset({2, 3}), "")]})
    recs = {r.weapon.instance_id: r for r in score_inventory([a, b], lists)}
    assert recs["a"].verdict == Verdict.NO_DATA


def test_full_god_match_overrides_trash_subset():
    w = weapon([2, 3], mw=True)
    lists = wl(
        god={100: [WishlistRoll(100, frozenset({2, 3}), "godroll")]},
        trash={100: [WishlistRoll(100, frozenset({2}), "trashy", is_trash=True)]},
    )
    rec = score_inventory([w], lists)[0]
    assert rec.verdict == Verdict.GOD_ROLL
