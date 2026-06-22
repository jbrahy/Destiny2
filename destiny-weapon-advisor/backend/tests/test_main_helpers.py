from app.main import _find_item_location


def test_find_item_location():
    profile = {
        "characterEquipment": {"data": {"c1": {"items": [{"itemInstanceId": "eq"}]}}},
        "characterInventories": {"data": {"c1": {"items": [{"itemInstanceId": "inv"}]}}},
        "profileInventory": {"data": {"items": [{"itemInstanceId": "vault"}]}},
    }
    assert _find_item_location(profile, "eq") == "equipped:c1"
    assert _find_item_location(profile, "inv") == "c1"
    assert _find_item_location(profile, "vault") == "vault"
    assert _find_item_location(profile, "missing") is None
