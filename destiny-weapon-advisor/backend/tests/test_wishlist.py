from pathlib import Path

from app.wishlist import parse_wishlist

SAMPLE = (Path(__file__).parent / "fixtures" / "wishlist_sample.txt").read_text()


def test_parses_god_rolls_grouped_by_item():
    wl = parse_wishlist(SAMPLE)
    assert set(wl.rolls_by_item.keys()) == {100, 200}
    rolls = wl.rolls_by_item[100]
    assert frozenset({2, 3}) in {r.perks for r in rolls}


def test_extracts_notes_and_tags():
    wl = parse_wishlist(SAMPLE)
    pve = next(r for r in wl.rolls_by_item[100] if r.perks == frozenset({2, 3}))
    assert pve.notes == "great pve roll"
    assert "pve" in pve.tags
    pvp = next(r for r in wl.rolls_by_item[100] if r.perks == frozenset({2}))
    assert "pvp" in pvp.tags


def test_negative_item_is_trash_keyed_by_absolute_hash():
    wl = parse_wishlist(SAMPLE)
    assert 100 in wl.trash_by_item
    assert wl.trash_by_item[100][0].is_trash is True


def test_roll_without_notes_has_empty_note():
    wl = parse_wishlist(SAMPLE)
    assert wl.rolls_by_item[200][0].notes == ""


def test_ignores_non_wishlist_lines():
    wl = parse_wishlist(SAMPLE)
    total = sum(len(v) for v in wl.rolls_by_item.values())
    total += sum(len(v) for v in wl.trash_by_item.values())
    assert total == 4
