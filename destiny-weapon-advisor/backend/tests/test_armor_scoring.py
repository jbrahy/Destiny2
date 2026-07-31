"""Objective armour scoring.

THE TEST THAT MATTERS: a spread-thin 103 must rank BELOW a focused 95. Armour
rolls archetype-spiky -- two or three stats at 25-35 and the rest pinned at 5-6
-- so total stats cannot distinguish a great piece from a useless one. That is
the entire reason this module exists.

Pure -- no I/O.
"""
import json

import pytest

from app.armor_scoring import focus, load_bands, score_armor, waste
from app.models import ArmorPiece, ArmorVerdict

BANDS = {"top_roll": 80, "good": 65, "ok": 50}


def piece(stats: dict, exotic: bool = False) -> ArmorPiece:
    return ArmorPiece(
        instance_id="i1", item_hash=1, name="Piece", slot="Helmet",
        class_name="Warlock", power=2000, is_exotic=exotic,
        is_masterworked=False, stats=stats, location="Vault",
    )


SPREAD_103 = {"Health": 17, "Melee": 17, "Grenade": 17, "Super": 17, "Class": 17, "Weapons": 18}
FOCUSED_95 = {"Health": 6, "Melee": 30, "Grenade": 6, "Super": 6, "Class": 12, "Weapons": 35}


def test_focus_sums_only_the_top_three_stats():
    assert focus(FOCUSED_95) == 30 + 35 + 12


def test_waste_is_everything_outside_the_top_three():
    assert waste(FOCUSED_95) == sum(FOCUSED_95.values()) - focus(FOCUSED_95)
    assert waste(FOCUSED_95) == 18  # literal pin: catches a [:3]-removal regression


def test_a_spread_thin_103_ranks_BELOW_a_focused_95():
    """The whole point. Total says the 103 is better; focus says otherwise."""
    assert sum(SPREAD_103.values()) > sum(FOCUSED_95.values())
    assert focus(SPREAD_103) < focus(FOCUSED_95)


def test_exotics_are_always_a_keep_regardless_of_stats():
    junk = {"Health": 1, "Melee": 1, "Grenade": 1, "Super": 1, "Class": 1, "Weapons": 1}
    assert score_armor(piece(junk, exotic=True), BANDS) == ArmorVerdict.EXOTIC


def test_bands_map_focus_to_verdicts():
    assert score_armor(piece({"a": 40, "b": 40, "c": 10}), BANDS) == ArmorVerdict.TOP_ROLL
    assert score_armor(piece({"a": 30, "b": 30, "c": 10}), BANDS) == ArmorVerdict.GOOD
    assert score_armor(piece({"a": 20, "b": 20, "c": 15}), BANDS) == ArmorVerdict.OK
    assert score_armor(piece({"a": 10, "b": 10, "c": 5}), BANDS) == ArmorVerdict.DISMANTLE


def test_band_boundaries_are_inclusive():
    """A piece exactly on a threshold takes the higher band."""
    assert score_armor(piece({"a": 80, "b": 0, "c": 0}), BANDS) == ArmorVerdict.TOP_ROLL
    assert score_armor(piece({"a": 65, "b": 0, "c": 0}), BANDS) == ArmorVerdict.GOOD
    assert score_armor(piece({"a": 50, "b": 0, "c": 0}), BANDS) == ArmorVerdict.OK


def test_negative_stats_do_not_break_scoring():
    """Health really can be -2 on live armour."""
    p = piece({"Health": -2, "Melee": 30, "Grenade": 30, "Super": 5, "Class": 5, "Weapons": 5})
    assert focus(p.stats) == 30 + 30 + 5
    assert score_armor(p, BANDS) == ArmorVerdict.GOOD


def test_a_zero_total_piece_is_dismantle_not_a_crash():
    """Some live pieces carry no stats at all."""
    p = piece({"Health": 0, "Melee": 0, "Grenade": 0})
    assert focus(p.stats) == 0
    assert score_armor(p, BANDS) == ArmorVerdict.DISMANTLE


def test_a_piece_with_no_stats_at_all_is_dismantle():
    assert score_armor(piece({}), BANDS) == ArmorVerdict.DISMANTLE


def test_fewer_than_three_stats_sums_what_exists():
    assert focus({"Melee": 30, "Weapons": 20}) == 50


def test_focus_with_fewer_than_three_stats_includes_negatives():
    """Documented, not desirable: with fewer than 3 stats the slice cannot
    exclude a negative, so it drags focus down. Real armour always carries
    all 6 stats, so this regime does not occur in practice."""
    assert focus({"Health": -2, "Melee": 5}) == 3
    assert focus({"Health": -2}) == -2


def test_load_bands_happy_path(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"bands": {"top_roll": 80, "good": 65, "ok": 50}}))
    assert load_bands(seed) == {"top_roll": 80, "good": 65, "ok": 50}


def test_load_bands_rejects_missing_key(tmp_path):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"bands": {"top_roll": 80, "good": 65}}))
    with pytest.raises(ValueError, match="missing band key"):
        load_bands(seed)


def test_load_bands_rejects_non_descending_thresholds(tmp_path):
    """good above top_roll would make GOOD unreachable for every piece."""
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"bands": {"top_roll": 80, "good": 90, "ok": 50}}))
    with pytest.raises(ValueError, match="top_roll >= good >= ok"):
        load_bands(seed)
