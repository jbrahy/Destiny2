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
