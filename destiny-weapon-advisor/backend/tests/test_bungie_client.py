import json
from pathlib import Path

import pytest

from app.bungie_client import BungieApiError, assemble_weapons, extract_response
from app.manifest import Manifest

PROFILE = json.loads((Path(__file__).parent / "fixtures" / "profile_sample.json").read_text())
MANIFEST = Manifest(items={
    100: {"displayProperties": {"name": "Fatebringer"}, "itemType": 3,
          "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 5}},
    999: {"displayProperties": {"name": "Hawkmoon"}, "itemType": 3,
          "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 6}},
})


def test_assembles_only_weapons_with_instances():
    weapons = assemble_weapons(PROFILE, MANIFEST)
    assert {w.instance_id for w in weapons} == {"i1", "i2", "i3"}


def test_reads_perks_from_sockets():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].perks == frozenset({2, 3, 50})


def test_masterwork_flag_from_state_bitmask():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].is_masterworked is True
    assert weapons["i2"].is_masterworked is False


def test_random_roll_true_for_legendary_false_for_exotic():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].is_random_roll is True
    assert weapons["i3"].is_random_roll is False


def test_element_mapped_from_damage_type():
    weapons = {w.instance_id: w for w in assemble_weapons(PROFILE, MANIFEST)}
    assert weapons["i1"].element == "Solar"
    assert weapons["i3"].element == "Kinetic"


def test_extract_response_returns_payload_on_success():
    assert extract_response({"ErrorCode": 1, "Response": {"x": 1}}) == {"x": 1}


def test_extract_response_raises_on_error_code():
    with pytest.raises(BungieApiError, match="bad token"):
        extract_response({"ErrorCode": 99, "Message": "bad token"})
