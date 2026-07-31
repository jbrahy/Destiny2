import json
from pathlib import Path

import pytest

from app.bungie_client import (
    BungieApiError,
    assemble_armor,
    assemble_weapons,
    extract_response,
    set_item_lock_state,
)
from app.config import get_settings
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


def test_locked_flag_from_state_bitmask():
    """state bit 1 is locked; bit 2 (4) is masterwork — verify they're read
    independently, including when both are set on the same item."""
    manifest = Manifest(items={
        100: {"displayProperties": {"name": "Fatebringer"}, "itemType": 3,
              "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 5}},
    })
    profile = {
        "characters": {"data": {}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "locked-only", "itemHash": 100, "state": 1},
            {"itemInstanceId": "unlocked", "itemHash": 100, "state": 0},
            {"itemInstanceId": "locked-and-masterworked", "itemHash": 100, "state": 5},
        ]}},
        "itemComponents": {},
    }
    weapons = {w.instance_id: w for w in assemble_weapons(profile, manifest)}
    assert weapons["locked-only"].is_locked is True
    assert weapons["locked-only"].is_masterworked is False
    assert weapons["unlocked"].is_locked is False
    assert weapons["locked-and-masterworked"].is_locked is True
    assert weapons["locked-and-masterworked"].is_masterworked is True


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


def test_manifest_bucket_hash_reads_inventory_bucket_type_hash():
    m = Manifest(items={555: {"inventory": {"bucketTypeHash": 1498876634}}})
    assert m.bucket_hash(555) == 1498876634


def test_manifest_bucket_hash_defaults_to_zero_when_missing():
    assert Manifest(items={}).bucket_hash(999) == 0


def test_assemble_weapons_sets_is_exotic_and_bucket_hash():
    """tierType 6 is Exotic; tierType 5 is Legendary (already used for is_random_roll)."""
    manifest = Manifest(items={
        777: {
            "displayProperties": {"name": "Gjallarhorn", "icon": "/gjally.jpg"},
            "itemType": 3,
            "itemTypeDisplayName": "Rocket Launcher",
            "inventory": {"tierType": 6, "bucketTypeHash": 953998645},
            "equippingBlock": {"ammoType": 3},
        },
    })
    profile = {
        "characters": {"data": {}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "inst-777", "itemHash": 777, "state": 0},
        ]}},
        "itemComponents": {},
    }
    weapons = assemble_weapons(profile, manifest)
    assert len(weapons) == 1
    assert weapons[0].is_exotic is True
    assert weapons[0].bucket_hash == 953998645


def test_assemble_armor_tags_pieces_with_their_set():
    manifest = Manifest(
        items={
            500: {
                "displayProperties": {"name": "Techsec Helm", "icon": "/t.jpg"},
                "itemType": 2, "itemTypeDisplayName": "Helmet",
                "inventory": {"tierType": 5}, "classType": 2,
            },
        },
        item_sets={900: {"displayProperties": {"name": "Techsec"},
                         "setItems": [500], "setPerks": []}},
    )
    profile = {
        "characters": {"data": {}},
        "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "a1", "itemHash": 500, "state": 0},
        ]}},
        "itemComponents": {},
    }
    pieces = assemble_armor(profile, manifest)
    assert len(pieces) == 1
    assert pieces[0].set_name == "Techsec"
    assert pieces[0].set_hash == 900


def test_assemble_armor_leaves_setless_pieces_blank():
    manifest = Manifest(items={
        501: {"displayProperties": {"name": "Random Helm"}, "itemType": 2,
              "itemTypeDisplayName": "Helmet", "inventory": {"tierType": 5}, "classType": 2},
    })
    profile = {
        "characters": {"data": {}}, "characterEquipment": {"data": {}},
        "characterInventories": {"data": {}},
        "profileInventory": {"data": {"items": [
            {"itemInstanceId": "a2", "itemHash": 501, "state": 0}]}},
        "itemComponents": {},
    }
    pieces = assemble_armor(profile, manifest)
    assert pieces[0].set_name == ""
    assert pieces[0].set_hash is None


@pytest.mark.asyncio
async def test_set_item_lock_state_posts_expected_payload():
    calls = []

    class FakeResponse:
        def json(self):
            return {"ErrorCode": 1, "Response": 0}

    class FakeClient:
        async def post(self, url, json=None, headers=None):
            calls.append((url, json))
            return FakeResponse()

    settings = get_settings()
    await set_item_lock_state(
        3, "inst-1", "char-1", False, "token", settings, FakeClient()
    )

    url, payload = calls[0]
    assert url.endswith("/Destiny2/Actions/Items/SetItemLockState/")
    assert payload == {
        "state": False,
        "itemId": "inst-1",
        "characterId": "char-1",
        "membershipType": 3,
    }


@pytest.mark.asyncio
async def test_set_item_lock_state_raises_on_bungie_error():
    class FakeResponse:
        def json(self):
            return {"ErrorCode": 1618, "ErrorStatus": "DestinyItemNotFound",
                    "Message": "Item not found."}

    class FakeClient:
        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    with pytest.raises(BungieApiError):
        await set_item_lock_state(
            3, "inst-1", "char-1", False, "token", get_settings(), FakeClient()
        )
