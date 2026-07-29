"""A weapon's trait roll pool, resolved from the manifest's plug sets.

The pool is what a weapon CAN roll, per trait column. Everything here is pure —
no I/O — so the rules that decide "is this weapon worth chasing / shaping" are
cheap to test exhaustively.

THE RULE THAT MATTERS: perks in one column are mutually exclusive. Any scorer
built on this must take one per column, never a union, or two A-tier perks in
the same column read as `strong >= 2` and promote a weapon to a god roll the
player could never actually hold.
"""
from app.manifest import Manifest
from app.roll_pool import trait_columns

_ITEMS = {
    100: {"displayProperties": {"name": "Fatebringer"}, "itemType": 3,
          "sockets": {"socketEntries": [
              {"singleInitialItemHash": 900},                                 # intrinsic
              {"singleInitialItemHash": 700, "randomizedPlugSetHash": 5001},  # barrel
              {"singleInitialItemHash": 800, "randomizedPlugSetHash": 5004},  # magazine
              {"singleInitialItemHash": 10, "randomizedPlugSetHash": 5002},   # trait col 1
              {"singleInitialItemHash": 12, "randomizedPlugSetHash": 5003},   # trait col 2
              {"singleInitialItemHash": 600, "randomizedPlugSetHash": 5005},  # origin trait
          ]}},
    # A weapon whose trait options are only inline on the socket entry.
    200: {"displayProperties": {"name": "Inline Gun"}, "itemType": 3,
          "sockets": {"socketEntries": [
              {"singleInitialItemHash": 14, "reusablePlugItems": [
                  {"plugItemHash": 14}, {"plugItemHash": 15}]},
          ]}},
    # Both hashes present: randomized must win (it is the real roll pool).
    300: {"displayProperties": {"name": "Both Gun"}, "itemType": 3,
          "sockets": {"socketEntries": [
              {"singleInitialItemHash": 10,
               "randomizedPlugSetHash": 5002, "reusablePlugSetHash": 5003},
          ]}},
    400: {"displayProperties": {"name": "No Sockets"}, "itemType": 3},
    500: {"displayProperties": {"name": "Dangling Ref"}, "itemType": 3,
          "sockets": {"socketEntries": [
              {"singleInitialItemHash": 10, "randomizedPlugSetHash": 999999},
          ]}},

    10: {"displayProperties": {"name": "Explosive Payload"}, "itemTypeDisplayName": "Trait"},
    11: {"displayProperties": {"name": "Frenzy"}, "itemTypeDisplayName": "Trait"},
    12: {"displayProperties": {"name": "Incandescent"}, "itemTypeDisplayName": "Trait"},
    13: {"displayProperties": {"name": "Rampage"}, "itemTypeDisplayName": "Trait"},
    14: {"displayProperties": {"name": "Chain Reaction"}, "itemTypeDisplayName": "Trait"},
    15: {"displayProperties": {"name": "Eager Edge"}, "itemTypeDisplayName": "Trait"},
    600: {"displayProperties": {"name": "Nadir Focus"}, "itemTypeDisplayName": "Origin Trait"},
    601: {"displayProperties": {"name": "Suros Synergy"}, "itemTypeDisplayName": "Origin Trait"},
    700: {"displayProperties": {"name": "Fluted Barrel"}, "itemTypeDisplayName": "Barrel"},
    701: {"displayProperties": {"name": "Corkscrew Rifling"}, "itemTypeDisplayName": "Barrel"},
    800: {"displayProperties": {"name": "Appended Mag"}, "itemTypeDisplayName": "Magazine"},
    801: {"displayProperties": {"name": "Ricochet Rounds"}, "itemTypeDisplayName": "Magazine"},
    900: {"displayProperties": {"name": "Adaptive Frame"}, "itemTypeDisplayName": "Intrinsic"},
}

_PLUG_SETS = {
    5001: {"reusablePlugItems": [{"plugItemHash": 700, "currentlyCanRoll": True},
                                 {"plugItemHash": 701, "currentlyCanRoll": True}]},
    5002: {"reusablePlugItems": [{"plugItemHash": 10, "currentlyCanRoll": True},
                                 {"plugItemHash": 11, "currentlyCanRoll": True},
                                 {"plugItemHash": 13, "currentlyCanRoll": False}]},
    5003: {"reusablePlugItems": [{"plugItemHash": 12, "currentlyCanRoll": True},
                                 {"plugItemHash": 14, "currentlyCanRoll": True}]},
    5004: {"reusablePlugItems": [{"plugItemHash": 800, "currentlyCanRoll": True},
                                 {"plugItemHash": 801, "currentlyCanRoll": True}]},
    5005: {"reusablePlugItems": [{"plugItemHash": 600, "currentlyCanRoll": True},
                                 {"plugItemHash": 601, "currentlyCanRoll": True}]},
}


def _manifest() -> Manifest:
    return Manifest(items=_ITEMS, plug_sets=_PLUG_SETS)


def test_returns_one_group_per_trait_column():
    """Grouping IS the mutual-exclusion rule — flatten it and scoring breaks."""
    cols = trait_columns(100, _manifest())
    assert len(cols) == 2
    assert cols[0] == ["Explosive Payload", "Frenzy", "Rampage"]
    assert cols[1] == ["Incandescent", "Chain Reaction"]


def test_excludes_barrels_magazines_origin_traits_and_intrinsics():
    """Only Trait plugs decide a weapon's quality. A barrel column would add
    noise, and an origin-trait column would add a free extra 'strong' perk."""
    flat = [name for col in trait_columns(100, _manifest()) for name in col]
    for noise in ("Fluted Barrel", "Appended Mag", "Nadir Focus", "Adaptive Frame"):
        assert noise not in flat


def test_only_current_drops_perks_that_no_longer_roll():
    """Chasing a perk that has left the loot pool is a wasted grind."""
    cols = trait_columns(100, _manifest(), only_current=True)
    assert cols[0] == ["Explosive Payload", "Frenzy"]   # Rampage no longer rolls
    assert cols[1] == ["Incandescent", "Chain Reaction"]


def test_falls_back_to_inline_reusable_plug_items():
    assert trait_columns(200, _manifest()) == [["Chain Reaction", "Eager Edge"]]


def test_randomized_plug_set_wins_over_reusable():
    """randomizedPlugSetHash is the actual roll pool; reusable is the fixed set."""
    assert trait_columns(300, _manifest()) == [["Explosive Payload", "Frenzy", "Rampage"]]


def test_weapon_without_sockets_yields_no_columns():
    assert trait_columns(400, _manifest()) == []


def test_dangling_plug_set_reference_is_skipped_not_fatal():
    assert trait_columns(500, _manifest()) == []


def test_manifest_without_plug_sets_yields_no_columns():
    """Caches predating the plug-set download must degrade, not crash."""
    assert trait_columns(100, Manifest(items=_ITEMS)) == []


def test_unknown_item_yields_no_columns():
    assert trait_columns(424242, _manifest()) == []


def test_columns_are_deduped_by_name():
    """Base and enhanced variants share a display name; counting both would
    inflate a column and mislead the chase list."""
    items = dict(_ITEMS)
    items[16] = {"displayProperties": {"name": "Frenzy"}, "itemTypeDisplayName": "Trait"}
    plug_sets = dict(_PLUG_SETS)
    plug_sets[5002] = {"reusablePlugItems": [
        {"plugItemHash": 11, "currentlyCanRoll": True},
        {"plugItemHash": 16, "currentlyCanRoll": True},
    ]}
    cols = trait_columns(100, Manifest(items=items, plug_sets=plug_sets))
    assert cols[0] == ["Frenzy"]
