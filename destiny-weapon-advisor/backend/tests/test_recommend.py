from app.recommend import element_for_subclass, recommend_weapons


def _w(**p):
    base = {
        "name": "Gun", "verdict": "good", "ammoType": "Primary", "element": "Void",
        "matchedPerks": [], "isMasterworked": False, "power": 1800,
    }
    base.update(p)
    return base


GENERAL = {"label": "General (PvE)", "element": None}


def test_element_for_subclass_maps_damage_types():
    assert element_for_subclass("Solar") == "Solar"
    assert element_for_subclass("Prismatic") is None
    assert element_for_subclass("Any") is None
    assert element_for_subclass("") is None


def test_groups_by_ammo_slot():
    weapons = [_w(name="P", ammoType="Primary"), _w(name="S", ammoType="Special"),
               _w(name="H", ammoType="Heavy")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["P"]
    assert [w["name"] for w in out["slots"]["Special"]] == ["S"]
    assert [w["name"] for w in out["slots"]["Heavy"]] == ["H"]


def test_orders_by_verdict_tier():
    weapons = [_w(name="good", verdict="good"), _w(name="god", verdict="god_roll"),
               _w(name="upg", verdict="masterwork")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["god", "upg", "good"]


def test_excludes_dismantle():
    weapons = [_w(name="keep", verdict="good"), _w(name="trash", verdict="dismantle")]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["keep"]


def test_excludes_unknown_verdict():
    weapons = [_w(name="keep", verdict="good"), _w(name="unknown", verdict="mythic")]
    out = recommend_weapons(weapons, GENERAL)
    # unknown verdict "mythic" should be excluded from all slots
    assert [w["name"] for w in out["slots"]["Primary"]] == ["keep"]
    assert [w["name"] for w in out["slots"]["Special"]] == []
    assert [w["name"] for w in out["slots"]["Heavy"]] == []


def test_activity_element_bonus_promotes_matching_weapon():
    activity = {"label": "Raid", "element": "Solar"}
    weapons = [_w(name="solar", verdict="good", element="Solar"),
               _w(name="void", verdict="good", element="Void")]
    out = recommend_weapons(weapons, activity)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["solar", "void"]
    assert "element-matched for Solar" in out["slots"]["Primary"][0]["recommendReason"]


def test_element_bonus_ties_one_tier_up_then_tiebreakers():
    activity = {"label": "Raid", "element": "Solar"}
    # Element bonus is +1, exactly one verdict tier.
    # matched "good" (3+1=4) ties unmatched "masterwork" (4).
    # Tiebreaker: masterwork.
    weapons = [_w(name="matched_good_mw", verdict="good", element="Solar", isMasterworked=True),
               _w(name="unmatched_upgrade", verdict="masterwork", element="Void", isMasterworked=False)]
    out = recommend_weapons(weapons, activity)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["matched_good_mw", "unmatched_upgrade"]

    # Reverse: unmatched masterwork with masterwork should beat matched good without.
    weapons = [_w(name="matched_good", verdict="good", element="Solar", isMasterworked=False),
               _w(name="unmatched_upgrade_mw", verdict="masterwork", element="Void", isMasterworked=True)]
    out = recommend_weapons(weapons, activity)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["unmatched_upgrade_mw", "matched_good"]


def test_general_context_no_element_bonus():
    weapons = [_w(name="void", verdict="good", element="Void"),
               _w(name="solar", verdict="good", element="Solar")]
    out = recommend_weapons(weapons, GENERAL)
    # tie on verdict; name tiebreaker -> alphabetical
    assert [w["name"] for w in out["slots"]["Primary"]] == ["solar", "void"]
    assert out["slots"]["Primary"][0]["recommendReason"] == "Good roll"


def test_masterwork_and_power_tiebreakers():
    weapons = [_w(name="plain", isMasterworked=False, power=1800),
               _w(name="mw", isMasterworked=True, power=1800)]
    out = recommend_weapons(weapons, GENERAL)
    assert [w["name"] for w in out["slots"]["Primary"]] == ["mw", "plain"]


def test_empty_input_returns_empty_slots():
    out = recommend_weapons([], GENERAL)
    assert out["slots"] == {"Primary": [], "Special": [], "Heavy": []}


def test_top_n_truncates():
    weapons = [_w(name=f"g{i}", verdict="good") for i in range(7)]
    out = recommend_weapons(weapons, GENERAL, top_n=3)
    assert len(out["slots"]["Primary"]) == 3


def test_no_internal_rank_key_leaks():
    out = recommend_weapons([_w()], GENERAL)
    assert "_rank" not in out["slots"]["Primary"][0]
