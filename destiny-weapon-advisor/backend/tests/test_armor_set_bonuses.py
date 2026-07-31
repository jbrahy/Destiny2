"""Armour set membership and bonuses.

NOTE: distinct from the "/api/armor-sets" endpoints, which are user-saved
armour loadouts. This module is about Destiny's own armour sets and their
2-piece / 4-piece bonuses.

Verified against the live manifest: 56 sets, each with setItems[] and setPerks
of the shape [{requiredSetCount: 2|4, sandboxPerkHash}].

Everything here is pure — no I/O — so membership is cheap to test exhaustively.
"""
from app.armor_set_bonuses import build_index, equipped_set_counts, set_bonuses, set_for
from app.manifest import Manifest

_ITEM_SETS = {
    900: {
        "displayProperties": {"name": "Techsec"},
        "setItems": [10, 11, 12],
        "setPerks": [
            {"requiredSetCount": 2, "sandboxPerkHash": 7001},
            {"requiredSetCount": 4, "sandboxPerkHash": 7002},
        ],
    },
    901: {
        "displayProperties": {"name": "AION Renewal"},
        "setItems": [20, 21],
        "setPerks": [{"requiredSetCount": 2, "sandboxPerkHash": 7003}],
    },
}
_PERKS = {
    7001: {"displayProperties": {"name": "Wrecker", "description": "Bonus Kinetic damage."}},
    7002: {"displayProperties": {"name": "Concussive Rounds", "description": "Disorienting burst."}},
    7003: {"displayProperties": {"name": "Force Converter", "description": "Sprint after RL kills."}},
}


def _manifest() -> Manifest:
    return Manifest(item_sets=_ITEM_SETS, sandbox_perks=_PERKS)


def test_index_maps_every_member_item_to_its_set():
    index = build_index(_manifest())
    assert index[10] == 900
    assert index[12] == 900
    assert index[20] == 901


def test_set_for_returns_name_and_hash():
    m = _manifest()
    assert set_for(11, build_index(m), m) == ("Techsec", 900)


def test_set_for_an_item_in_no_set_is_none():
    m = _manifest()
    assert set_for(999, build_index(m), m) is None


def test_set_bonuses_resolve_count_name_and_description():
    assert set_bonuses(900, _manifest()) == [
        {"count": 2, "name": "Wrecker", "description": "Bonus Kinetic damage."},
        {"count": 4, "name": "Concussive Rounds", "description": "Disorienting burst."},
    ]


def test_set_bonuses_are_sorted_by_required_count():
    """4pc must never be listed before 2pc, whatever order the manifest uses."""
    m = Manifest(item_sets={900: {**_ITEM_SETS[900], "setPerks": [
        {"requiredSetCount": 4, "sandboxPerkHash": 7002},
        {"requiredSetCount": 2, "sandboxPerkHash": 7001},
    ]}}, sandbox_perks=_PERKS)
    assert [b["count"] for b in set_bonuses(900, m)] == [2, 4]


def test_set_bonuses_with_an_unresolvable_perk_still_reports_the_count():
    m = Manifest(item_sets=_ITEM_SETS, sandbox_perks={})
    assert set_bonuses(901, m) == [{"count": 2, "name": "", "description": ""}]


def test_set_bonuses_of_unknown_set_is_empty():
    assert set_bonuses(4242, _manifest()) == []


def test_equipped_set_counts_tallies_by_set():
    assert equipped_set_counts([900, 900, 901, None, 900]) == {900: 3, 901: 1}


def test_equipped_set_counts_ignores_pieces_with_no_set():
    assert equipped_set_counts([None, None]) == {}


def test_manifest_without_set_tables_yields_an_empty_index():
    """Old caches degrade to 'no sets', never a crash."""
    assert build_index(Manifest()) == {}
