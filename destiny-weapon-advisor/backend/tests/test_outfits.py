"""Outfit assembly.

THE RULE THAT MATTERS: Destiny allows exactly ONE exotic armour piece and ONE
exotic weapon equipped. Greedy per-slot picking violates it whenever the best
piece in two slots is exotic, producing an outfit the player cannot equip.

Pure — no I/O.
"""
from app.outfits import ARMOR_SLOTS, build_all_outfits, build_outfit, pick_with_one_exotic


def armor(slot, cls="Warlock", exotic=False, **stats):
    full = {"Health": 0, "Melee": 0, "Grenade": 0, "Super": 0, "Class": 0, "Weapons": 0}
    full.update(stats)
    return {
        "instanceId": f"{slot}-{'exo' if exotic else 'leg'}-{sum(full.values())}",
        "itemHash": 1, "name": f"{slot} piece", "slot": slot, "className": cls,
        "power": 2000, "isExotic": exotic, "isMasterworked": False, "stats": full,
        "location": "Vault", "icon": "", "equipped": False,
        "setName": "", "setHash": None, "setBonuses": [],
        "verdict": "good", "focus": sum(sorted(full.values(), reverse=True)[:3]), "waste": 0,
    }


def weapon(ammo, name="Gun", exotic=False, element="Solar", verdict="good"):
    return {
        "instanceId": f"{name}-{ammo}", "itemHash": 2, "name": name,
        "weaponType": "Auto Rifle", "element": element, "ammoType": ammo,
        "isExotic": exotic, "isMasterworked": False, "verdict": verdict,
        "matchedPerks": [], "power": 2000, "location": "Vault", "icon": "",
        "equipped": False, "tags": [], "isDuplicate": False, "frame": "",
        "perkNames": [], "stats": {}, "ratedPerks": [], "note": "",
        "verdictReason": "", "upgradePath": None,
    }


BUILD = {"statPriority": ["Grenade", "Health"], "super": "x", "playstyle": "y"}


# ---------------------------------------------------------------------------
# The exotic constraint
# ---------------------------------------------------------------------------

def test_only_one_exotic_survives_when_two_slots_prefer_one():
    """The whole reason this is not a greedy per-slot pick."""
    by_slot = {
        "Helmet": [armor("Helmet", exotic=True, Grenade=40), armor("Helmet", Grenade=10)],
        "Gauntlets": [armor("Gauntlets", exotic=True, Grenade=30), armor("Gauntlets", Grenade=20)],
    }
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    exotics = [c for c in chosen.values() if c and c["isExotic"]]
    assert len(exotics) == 1


def test_the_exotic_kept_is_the_one_with_the_biggest_gain():
    """Helmet gains 40-10=30; Gauntlets gains 30-20=10. Helmet must win."""
    by_slot = {
        "Helmet": [armor("Helmet", exotic=True, Grenade=40), armor("Helmet", Grenade=10)],
        "Gauntlets": [armor("Gauntlets", exotic=True, Grenade=30), armor("Gauntlets", Grenade=20)],
    }
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    assert chosen["Helmet"]["isExotic"] is True
    assert chosen["Gauntlets"]["isExotic"] is False


def test_an_all_legendary_pool_is_untouched_by_the_constraint():
    by_slot = {
        "Helmet": [armor("Helmet", Grenade=30), armor("Helmet", Grenade=10)],
        "Gauntlets": [armor("Gauntlets", Grenade=20)],
    }
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    assert chosen["Helmet"]["stats"]["Grenade"] == 30
    assert chosen["Gauntlets"]["stats"]["Grenade"] == 20


def test_a_slot_whose_only_option_is_exotic_can_still_be_filled():
    by_slot = {"Helmet": [armor("Helmet", exotic=True, Grenade=30)]}
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    assert chosen["Helmet"]["isExotic"] is True


def test_two_exotic_only_slots_leave_the_lesser_one_empty():
    """Both slots can ONLY be exotic, but only one exotic may be worn."""
    by_slot = {
        "Helmet": [armor("Helmet", exotic=True, Grenade=40)],
        "Gauntlets": [armor("Gauntlets", exotic=True, Grenade=10)],
    }
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    assert chosen["Helmet"]["isExotic"] is True
    assert chosen["Gauntlets"] is None


def test_an_empty_slot_yields_none_not_a_fabricated_pick():
    chosen = pick_with_one_exotic({"Helmet": []}, lambda a: 0)
    assert chosen["Helmet"] is None


def test_an_exotic_worse_than_the_best_legendary_is_never_worn():
    """No forced exotic swap when every exotic loses to the best legendary —
    the single allowance is spent only when it is a genuine upgrade."""
    by_slot = {
        "Helmet": [armor("Helmet", exotic=True, Grenade=5), armor("Helmet", Grenade=30)],
        "Gauntlets": [armor("Gauntlets", Grenade=20)],
    }
    chosen = pick_with_one_exotic(by_slot, lambda a: a["stats"]["Grenade"])
    assert chosen["Helmet"]["isExotic"] is False
    assert chosen["Gauntlets"]["isExotic"] is False


# ---------------------------------------------------------------------------
# Outfit assembly
# ---------------------------------------------------------------------------

def test_armor_is_class_locked():
    pool = [armor("Helmet", cls="Titan", Grenade=40), armor("Helmet", cls="Warlock", Grenade=10)]
    out = build_outfit("Warlock", "Solar", [], pool, BUILD)
    assert out["armor"]["Helmet"]["className"] == "Warlock"


def test_stat_priority_beats_raw_focus():
    """A piece stacked into the build's priority stats wins over a higher-focus
    piece that dumps its points elsewhere."""
    on_priority = armor("Helmet", Grenade=30, Health=25)          # focus 55
    off_priority = armor("Helmet", Super=35, Weapons=35, Class=5)  # focus 75
    out = build_outfit("Warlock", "Solar", [], [on_priority, off_priority], BUILD)
    assert out["armor"]["Helmet"]["instanceId"] == on_priority["instanceId"]


def test_only_one_exotic_weapon():
    pool = [
        weapon("Primary", "ExoPrimary", exotic=True),
        weapon("Special", "ExoSpecial", exotic=True),
        weapon("Primary", "LegPrimary"),
        weapon("Special", "LegSpecial"),
    ]
    out = build_outfit("Warlock", "Solar", pool, [], BUILD)
    exotics = [w for w in out["weapons"].values() if w and w["isExotic"]]
    assert len(exotics) <= 1


def test_every_armor_slot_key_is_present_even_when_unfilled():
    out = build_outfit("Warlock", "Solar", [], [], BUILD)
    assert set(out["armor"]) == set(ARMOR_SLOTS)
    assert all(v is None for v in out["armor"].values())


def test_build_all_outfits_produces_one_per_seeded_combo():
    builds = {
        "_meta": "ignored",
        "Warlock|Solar": BUILD,
        "Titan|Arc": BUILD,
    }
    outfits = build_all_outfits(builds, [], [])
    assert len(outfits) == 2
    assert {(o["className"], o["subclass"]) for o in outfits} == {
        ("Warlock", "Solar"), ("Titan", "Arc")}


def test_outfit_carries_the_build_for_display():
    out = build_outfit("Warlock", "Solar", [], [], BUILD)
    assert out["build"] == BUILD
    assert out["statPriority"] == ["Grenade", "Health"]
