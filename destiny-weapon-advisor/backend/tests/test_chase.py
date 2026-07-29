"""Weapons worth farming: the roll pool says a god roll is possible, your vault
says you don't have one yet.

Pure — no I/O. The ceiling is computed from the trait pool one perk per column
(never a union, or two A-tier perks in the same column would fake a god roll the
player can never hold), and fed through the SAME score_weapon thresholds the rest
of the app uses so the two can never disagree.
"""
from app.chase import chase_candidates
from app.manifest import Manifest
from app.models import OwnedWeapon, Verdict
from app.perk_ratings import PerkRatings

_ITEMS = {
    100: {"displayProperties": {"name": "Fatebringer", "icon": "/fb.jpg"},
          "itemType": 3, "itemTypeDisplayName": "Hand Cannon",
          "sockets": {"socketEntries": [
              {"randomizedPlugSetHash": 5002},   # trait col 1
              {"randomizedPlugSetHash": 5003},   # trait col 2
          ]}},
    200: {"displayProperties": {"name": "Mediocre Gun", "icon": "/mg.jpg"},
          "itemType": 3, "itemTypeDisplayName": "Auto Rifle",
          "sockets": {"socketEntries": [{"randomizedPlugSetHash": 5004}]}},
    300: {"displayProperties": {"name": "One Column Wonder", "icon": "/ocw.jpg"},
          "itemType": 3, "itemTypeDisplayName": "Shotgun",
          "sockets": {"socketEntries": [{"randomizedPlugSetHash": 5005}]}},

    10: {"displayProperties": {"name": "Explosive Payload"}, "itemTypeDisplayName": "Trait"},
    11: {"displayProperties": {"name": "Frenzy"}, "itemTypeDisplayName": "Trait"},
    12: {"displayProperties": {"name": "Incandescent"}, "itemTypeDisplayName": "Trait"},
    13: {"displayProperties": {"name": "Meh Perk"}, "itemTypeDisplayName": "Trait"},
    14: {"displayProperties": {"name": "Also Meh"}, "itemTypeDisplayName": "Trait"},
}

_PLUG_SETS = {
    # Two A-tier perks, but in SEPARATE columns -> a real god roll is possible.
    5002: {"reusablePlugItems": [{"plugItemHash": 10, "currentlyCanRoll": True},
                                 {"plugItemHash": 13, "currentlyCanRoll": True}]},
    5003: {"reusablePlugItems": [{"plugItemHash": 11, "currentlyCanRoll": True}]},
    # Only weak perks -> ceiling is low, never worth chasing.
    5004: {"reusablePlugItems": [{"plugItemHash": 13, "currentlyCanRoll": True},
                                 {"plugItemHash": 14, "currentlyCanRoll": True}]},
    # TWO A-tier perks in ONE column -> mutually exclusive, NOT a god roll.
    5005: {"reusablePlugItems": [{"plugItemHash": 10, "currentlyCanRoll": True},
                                 {"plugItemHash": 11, "currentlyCanRoll": True}]},
}

_SEED = {
    "Explosive Payload": {"rating": "A", "reason": "", "tags": []},
    "Frenzy": {"rating": "A", "reason": "", "tags": []},
    "Incandescent": {"rating": "S", "reason": "", "tags": []},
    "Meh Perk": {"rating": "C", "reason": "", "tags": []},
    "Also Meh": {"rating": "C", "reason": "", "tags": []},
}


def _manifest() -> Manifest:
    return Manifest(items=_ITEMS, plug_sets=_PLUG_SETS)


def _ratings() -> PerkRatings:
    return PerkRatings(_SEED, {})


def _owned(item_hash: int, perks: list[str], masterworked: bool = False) -> OwnedWeapon:
    return OwnedWeapon(
        instance_id=f"i{item_hash}-{'-'.join(perks) or 'none'}", item_hash=item_hash,
        name=_ITEMS[item_hash]["displayProperties"]["name"],
        weapon_type=_ITEMS[item_hash]["itemTypeDisplayName"],
        element="Solar", is_masterworked=masterworked, is_random_roll=True,
        perks=frozenset(), location="Vault", perk_names=perks,
    )


def test_weapon_whose_ceiling_beats_what_you_own_is_a_chase():
    rows = chase_candidates([_owned(100, ["Meh Perk"])], _manifest(), _ratings())
    assert len(rows) == 1
    assert rows[0]["itemHash"] == 100
    assert rows[0]["ceiling"] == Verdict.GOD_ROLL.value


def test_chase_names_the_perks_to_farm_for_grouped_by_column():
    rows = chase_candidates([_owned(100, ["Meh Perk"])], _manifest(), _ratings())
    assert rows[0]["chasePerks"] == ["Explosive Payload", "Frenzy"]


def test_weapon_you_already_have_at_its_ceiling_is_not_a_chase():
    """You own the god roll already — nothing left to farm."""
    owned = _owned(100, ["Explosive Payload", "Frenzy"], masterworked=True)
    assert chase_candidates([owned], _manifest(), _ratings()) == []


def test_two_a_tier_perks_in_ONE_column_is_not_a_god_roll_ceiling():
    """The central trap. They are mutually exclusive, so the ceiling is GOOD."""
    rows = chase_candidates([_owned(300, ["Meh Perk"])], _manifest(), _ratings())
    assert rows == []


def test_weapon_with_only_weak_perks_in_its_pool_is_never_a_chase():
    assert chase_candidates([_owned(200, ["Meh Perk"])], _manifest(), _ratings()) == []


def test_best_owned_copy_across_duplicates_decides():
    """Two copies: the good one means there is nothing to chase."""
    weapons = [
        _owned(100, ["Meh Perk"]),
        _owned(100, ["Explosive Payload", "Frenzy"], masterworked=True),
    ]
    assert chase_candidates(weapons, _manifest(), _ratings()) == []


def test_reports_how_many_copies_you_hold():
    weapons = [_owned(100, ["Meh Perk"]), _owned(100, ["Also Meh"])]
    rows = chase_candidates(weapons, _manifest(), _ratings())
    assert rows[0]["haveCount"] == 2


def test_manifest_without_plug_sets_yields_no_chases():
    """Old caches degrade to an empty list, never a crash or a false chase."""
    bare = Manifest(items=_ITEMS)
    assert chase_candidates([_owned(100, ["Meh Perk"])], bare, _ratings()) == []


def test_result_carries_display_fields_for_the_ui():
    rows = chase_candidates([_owned(100, ["Meh Perk"])], _manifest(), _ratings())
    assert rows[0]["name"] == "Fatebringer"
    assert rows[0]["icon"] == "/fb.jpg"
    assert rows[0]["weaponType"] == "Hand Cannon"
    assert rows[0]["ownedBest"] == Verdict.NO_DATA.value


def test_rows_are_sorted_by_ceiling_then_name():
    """Deterministic order so the UI does not reshuffle between refreshes."""
    rows = chase_candidates(
        [_owned(100, ["Meh Perk"]), _owned(200, ["Meh Perk"]), _owned(300, ["Meh Perk"])],
        _manifest(), _ratings(),
    )
    assert [r["name"] for r in rows] == ["Fatebringer"]
