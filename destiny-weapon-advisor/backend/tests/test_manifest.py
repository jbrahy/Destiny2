import json
from pathlib import Path

from app.manifest import Manifest

SAMPLE = json.loads((Path(__file__).parent / "fixtures" / "manifest_sample.json").read_text())


def test_name_lookup():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.name(100) == "Fatebringer"
    assert m.name(2) == "Explosive Payload"


def test_is_weapon_true_only_for_item_type_3():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.is_weapon(100) is True
    assert m.is_weapon(2) is False


def test_tier_type_distinguishes_legendary_from_exotic():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.tier_type(100) == 5
    assert m.tier_type(999) == 6


def test_item_type_display_name():
    m = Manifest(items={int(k): v for k, v in SAMPLE.items()})
    assert m.item_type(100) == "Hand Cannon"


def test_unknown_hash_name_is_safe():
    m = Manifest(items={})
    assert m.name(123) == "Unknown (123)"


# ---------------------------------------------------------------------------
# Plug sets — the source of a weapon's trait roll pool.
#
# socketEntries[] point at DestinyPlugSetDefinition via randomizedPlugSetHash
# (random rolls / craftable traits) or reusablePlugSetHash (fixed choices).
# Verified against Syncopation-53: socket 3 -> plug set 374393294 -> 13 traits.
# ---------------------------------------------------------------------------

_PLUGSET_ITEMS = {
    100: {"displayProperties": {"name": "Fatebringer"}, "itemType": 3,
          "sockets": {"socketEntries": [
              {"singleInitialItemHash": 900},                                  # 0: intrinsic
              {"singleInitialItemHash": 700, "randomizedPlugSetHash": 5001},   # 1: barrel
              {"singleInitialItemHash": 10, "randomizedPlugSetHash": 5002},    # 2: trait col
              {"singleInitialItemHash": 12, "reusablePlugSetHash": 5003},      # 3: trait col
              {"singleInitialItemHash": 14, "reusablePlugItems": [             # 4: inline only
                  {"plugItemHash": 14}, {"plugItemHash": 15}]},
          ]}},
    10: {"displayProperties": {"name": "Explosive Payload"}, "itemTypeDisplayName": "Trait"},
    11: {"displayProperties": {"name": "Frenzy"}, "itemTypeDisplayName": "Trait"},
    12: {"displayProperties": {"name": "Incandescent"}, "itemTypeDisplayName": "Trait"},
    13: {"displayProperties": {"name": "Rampage"}, "itemTypeDisplayName": "Trait"},
    14: {"displayProperties": {"name": "Chain Reaction"}, "itemTypeDisplayName": "Trait"},
    15: {"displayProperties": {"name": "Eager Edge"}, "itemTypeDisplayName": "Trait"},
    700: {"displayProperties": {"name": "Fluted Barrel"}, "itemTypeDisplayName": "Barrel"},
    701: {"displayProperties": {"name": "Corkscrew Rifling"}, "itemTypeDisplayName": "Barrel"},
    900: {"displayProperties": {"name": "Adaptive Frame"}, "itemTypeDisplayName": "Intrinsic"},
}

_PLUG_SETS = {
    5001: {"reusablePlugItems": [{"plugItemHash": 700, "currentlyCanRoll": True},
                                 {"plugItemHash": 701, "currentlyCanRoll": True}]},
    5002: {"reusablePlugItems": [{"plugItemHash": 10, "currentlyCanRoll": True},
                                 {"plugItemHash": 11, "currentlyCanRoll": True},
                                 {"plugItemHash": 13, "currentlyCanRoll": False}]},
    5003: {"reusablePlugItems": [{"plugItemHash": 12, "currentlyCanRoll": True}]},
}


def _plugset_manifest() -> Manifest:
    return Manifest(items=_PLUGSET_ITEMS, plug_sets=_PLUG_SETS)


def test_socket_entries_returns_the_definition_list():
    m = _plugset_manifest()
    assert len(m.socket_entries(100)) == 5
    assert m.socket_entries(999999) == []


def test_plug_set_hashes_resolves_a_plug_set():
    m = _plugset_manifest()
    assert m.plug_set_hashes(5001) == [700, 701]


def test_plug_set_hashes_can_filter_to_currently_rollable():
    """A chase list must not tell you to farm a perk that no longer drops."""
    m = _plugset_manifest()
    assert m.plug_set_hashes(5002) == [10, 11, 13]
    assert m.plug_set_hashes(5002, only_current=True) == [10, 11]


def test_plug_set_hashes_of_unknown_set_is_empty_not_an_error():
    assert _plugset_manifest().plug_set_hashes(424242) == []


def test_is_trait_distinguishes_traits_from_barrels_and_intrinsics():
    m = _plugset_manifest()
    assert m.is_trait(10) is True
    assert m.is_trait(700) is False   # Barrel
    assert m.is_trait(900) is False   # Intrinsic
    assert m.is_trait(999999) is False


def test_manifest_without_plug_sets_degrades_quietly():
    """Caches written before plug sets existed must not crash."""
    m = Manifest(items=_PLUGSET_ITEMS)
    assert m.plug_set_hashes(5001) == []
    assert m.socket_entries(100) != []
