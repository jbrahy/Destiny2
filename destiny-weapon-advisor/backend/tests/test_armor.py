from app.bungie_client import assemble_armor
from app.manifest import Manifest


def _manifest():
    return Manifest(
        items={
            100: {"displayProperties": {"name": "Cool Helm"}, "itemType": 2,
                  "itemTypeDisplayName": "Helmet", "inventory": {"tierType": 5}, "classType": 1},
            200: {"displayProperties": {"name": "Stompees"}, "itemType": 2,
                  "itemTypeDisplayName": "Hunter Cloak", "inventory": {"tierType": 6}, "classType": 1},
            300: {"displayProperties": {"name": "Gun"}, "itemType": 3,
                  "itemTypeDisplayName": "Hand Cannon", "inventory": {"tierType": 5}},
        },
        stats={2996146975: {"displayProperties": {"name": "Mobility"}}},
    )


PROFILE = {
    "characters": {"data": {"c1": {"classType": 1}}},
    "profileInventory": {"data": {"items": [
        {"itemHash": 100, "itemInstanceId": "a", "state": 0},
        {"itemHash": 200, "itemInstanceId": "b", "state": 4},
        {"itemHash": 300, "itemInstanceId": "c"},
    ]}},
    "characterInventories": {"data": {}},
    "characterEquipment": {"data": {}},
    "itemComponents": {
        "instances": {"data": {"a": {"primaryStat": {"value": 1800}}}},
        "stats": {"data": {"a": {"stats": {"2996146975": {"value": 20}}}}},
    },
}


def test_armor_excludes_weapons_and_reads_fields():
    pieces = {p.instance_id: p for p in assemble_armor(PROFILE, _manifest())}
    assert set(pieces) == {"a", "b"}  # weapon "c" excluded
    assert pieces["a"].slot == "Helmet"
    assert pieces["a"].class_name == "Hunter"
    assert pieces["a"].power == 1800
    assert pieces["a"].stats == {"Mobility": 20}
    assert pieces["a"].is_exotic is False


def test_class_item_normalized_and_exotic_masterwork_flags():
    pieces = {p.instance_id: p for p in assemble_armor(PROFILE, _manifest())}
    assert pieces["b"].slot == "Class Item"  # "Hunter Cloak" normalized
    assert pieces["b"].is_exotic is True
    assert pieces["b"].is_masterworked is True
