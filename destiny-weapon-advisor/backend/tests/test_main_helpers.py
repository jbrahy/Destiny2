from app.main import _find_item_location, weapon_to_dict
from app.models import OwnedWeapon, Verdict


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


def test_weapon_to_dict_exposes_is_exotic():
    """The outfit builder needs this to enforce one exotic weapon per loadout."""
    weapon = OwnedWeapon(
        instance_id="w1", item_hash=1, name="Gjallarhorn",
        weapon_type="Rocket Launcher", element="Solar", is_masterworked=False,
        is_random_roll=False, perks=frozenset(), location="Vault", is_exotic=True,
    )
    info = {"verdict": Verdict.GOOD, "rated": [], "note": "", "tags": [],
            "is_duplicate": False}
    assert weapon_to_dict(weapon, info)["isExotic"] is True
