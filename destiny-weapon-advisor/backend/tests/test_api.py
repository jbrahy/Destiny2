from app.main import recommendation_to_dict
from app.manifest import Manifest
from app.models import OwnedWeapon, Recommendation, Verdict


def test_recommendation_serialization_resolves_perk_names():
    manifest = Manifest(items={2: {"displayProperties": {"name": "Explosive Payload"}}})
    weapon = OwnedWeapon("i1", 100, "Fatebringer", "Hand Cannon", "Solar",
                         True, True, frozenset({2}), "Vault")
    rec = Recommendation(weapon, Verdict.GOD_ROLL, [2], "great pve", ["pve"], False)
    out = recommendation_to_dict(rec, manifest)
    assert out["name"] == "Fatebringer"
    assert out["verdict"] == "god_roll"
    assert out["matchedPerks"] == ["Explosive Payload"]
    assert out["note"] == "great pve"
    assert out["tags"] == ["pve"]
