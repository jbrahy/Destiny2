from fastapi.testclient import TestClient

from app.main import app, recommendation_to_dict
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


def test_transfer_missing_fields_returns_422():
    client = TestClient(app)
    resp = client.post("/api/transfer", json={"instanceId": "x"})
    assert resp.status_code == 422


def test_perk_put_missing_rating_returns_422():
    client = TestClient(app)
    resp = client.put("/api/perks", json={"name": "Frenzy"})
    assert resp.status_code == 422


def test_membership_select_missing_fields_returns_422():
    client = TestClient(app)
    resp = client.post("/api/memberships/select", json={"membershipType": 2})
    assert resp.status_code == 422
