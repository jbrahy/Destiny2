from app.loadout_builder import build_loadout


def _w(**p):
    base = {
        "name": "Gun", "verdict": "good", "ammoType": "Primary", "element": "Void",
        "matchedPerks": [], "isMasterworked": False, "power": 1800, "instanceId": "i",
        "itemHash": 1,
    }
    base.update(p)
    return base


def _activity(**p):
    base = {
        "name": "Crota's End (Raid)", "recommendedClass": "Titan",
        "recommendedSubclass": "Strand", "weapons": "Sword for Crota; add-clear primary",
        "notes": "n",
    }
    base.update(p)
    return base


BUILD = {"super": "Bladefury", "weapons": "melee-lean"}


def test_picks_top_weapon_per_slot():
    weapons = [
        _w(name="P-good", ammoType="Primary", verdict="good"),
        _w(name="P-god", ammoType="Primary", verdict="god_roll"),
        _w(name="S1", ammoType="Special"),
        _w(name="H1", ammoType="Heavy"),
    ]
    out = build_loadout(weapons, _activity(), BUILD)
    assert out["weapons"]["Primary"]["name"] == "P-god"
    assert out["weapons"]["Special"]["name"] == "S1"
    assert out["weapons"]["Heavy"]["name"] == "H1"


def test_empty_slot_is_null():
    weapons = [_w(name="P1", ammoType="Primary")]
    out = build_loadout(weapons, _activity(), BUILD)
    assert out["weapons"]["Primary"]["name"] == "P1"
    assert out["weapons"]["Special"] is None
    assert out["weapons"]["Heavy"] is None


def test_attaches_subclass_build():
    out = build_loadout([], _activity(recommendedClass="Titan", recommendedSubclass="Strand"), BUILD)
    assert out["subclass"]["class"] == "Titan"
    assert out["subclass"]["subclass"] == "Strand"
    assert out["subclass"]["build"] == BUILD


def test_no_build_when_none_provided():
    out = build_loadout([], _activity(recommendedClass="Any"), None)
    assert out["subclass"]["build"] is None


def test_element_coverage_reports_distinct_elements_and_activity_match():
    weapons = [
        _w(name="P", ammoType="Primary", element="Strand"),
        _w(name="S", ammoType="Special", element="Void"),
        _w(name="H", ammoType="Heavy", element="Strand"),
    ]
    # activity Strand -> Strand element
    out = build_loadout(weapons, _activity(recommendedSubclass="Strand"), BUILD)
    assert sorted(out["elementCoverage"]["elements"]) == ["Strand", "Void"]
    assert out["elementCoverage"]["activityElement"] == "Strand"
    assert out["elementCoverage"]["matchesActivity"] is True


def test_activity_element_none_for_prismatic():
    out = build_loadout([], _activity(recommendedSubclass="Prismatic"), BUILD)
    assert out["elementCoverage"]["activityElement"] is None
    assert out["elementCoverage"]["matchesActivity"] is False


def test_carries_activity_name_and_guidance():
    out = build_loadout([], _activity(name="Last Wish (Raid)", weapons="Tractor Cannon"), BUILD)
    assert out["activity"] == "Last Wish (Raid)"
    assert out["guidance"] == "Tractor Cannon"
