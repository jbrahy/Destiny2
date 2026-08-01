"""GET /api/outfits — one outfit per seeded class/subclass, read-only.

POST /api/outfits/apply — equip one of them onto a character. The dry run is
the load-bearing test here: it fills the confirm dialog, and if it ever reaches
Bungie the "preview" would be silently mutating the player's gear.
"""
import json

import pytest

from app.repositories import cache as cache_repo
from tests.conftest import login_user

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHAR = "char-warlock-1"
_TITAN = "char-titan-1"

_PROFILE = {
    "characters": {"data": {
        _CHAR: {"classType": 2, "light": 2000, "dateLastPlayed": "2026-07-31T00:00:00Z"},
        _TITAN: {"classType": 0, "light": 1990, "dateLastPlayed": "2026-07-30T00:00:00Z"},
    }},
    "characterEquipment": {"data": {}},
    "characterInventories": {"data": {}},
    "profileInventory": {"data": {"items": [
        {"itemInstanceId": "helm-1", "itemHash": 500, "state": 0},
    ]}},
}

_ARMOR = [{
    "instanceId": "helm-1", "itemHash": 500, "name": "Techsec Helm", "slot": "Helmet",
    "className": "Warlock", "power": 2000, "isExotic": False, "isMasterworked": False,
    "stats": {"Health": 10, "Melee": 10, "Grenade": 30, "Super": 5, "Class": 5, "Weapons": 5},
    "location": "Vault", "icon": "/t.jpg", "equipped": False,
    "setName": "", "setHash": None, "setBonuses": [],
    "verdict": "good", "focus": 50, "waste": 15,
}]


def _csrf(client) -> dict:
    token = client.cookies.get("csrftoken")
    assert token, "csrftoken cookie not set after login"
    return {"X-CSRF-Token": token}


async def _seed(pool, uid):
    await cache_repo.set(pool, uid, "profile_cache", json.dumps(_PROFILE), 3600)
    await cache_repo.set(pool, uid, "weapons_cache", json.dumps({"weapons": []}), 3600)
    await cache_repo.set(pool, uid, "armor_cache", json.dumps(_ARMOR), 3600)


# ---------------------------------------------------------------------------
# GET /api/outfits
# ---------------------------------------------------------------------------

async def test_outfits_requires_authentication(app_client):
    assert (await app_client.get("/api/outfits")).status_code == 401


async def test_outfits_needs_a_cached_inventory(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch)
    resp = await app_client.get("/api/outfits")
    assert resp.status_code == 400
    assert "Load your inventory first" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/outfits/apply
# ---------------------------------------------------------------------------

async def test_apply_requires_authentication(app_client):
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/api/outfits/apply", json={
            "className": "Warlock", "subclass": "Solar",
            "characterId": _CHAR, "dryRun": True,
        })
    assert r.status_code == 401


async def test_apply_403_without_csrf(app_client, clean_db, monkeypatch):
    await login_user(app_client, monkeypatch, bungie_id="bm-outfit-nocsrf")
    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _CHAR, "dryRun": True,
    })
    assert r.status_code == 403


async def test_apply_404_for_an_unknown_subclass(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-outfit-404")
    await _seed(clean_db, uid)
    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Nonsense", "characterId": _CHAR, "dryRun": True,
    }, headers=_csrf(app_client))
    assert r.status_code == 404


async def test_apply_400_when_the_character_is_not_yours(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-outfit-nochar")
    await _seed(clean_db, uid)
    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": "someone-elses", "dryRun": True,
    }, headers=_csrf(app_client))
    assert r.status_code == 400
    assert "character" in r.json()["detail"].lower()


async def test_apply_400_when_the_character_class_does_not_match(app_client, clean_db, monkeypatch):
    """Warlock armour on a Titan is not a Bungie error to discover eight times."""
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-outfit-wrongclass")
    await _seed(clean_db, uid)
    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _TITAN, "dryRun": True,
    }, headers=_csrf(app_client))
    assert r.status_code == 400
    assert "Titan" in r.json()["detail"]


async def test_dry_run_returns_a_plan_and_never_calls_bungie(app_client, clean_db, monkeypatch):
    """The load-bearing one: a preview that reached Bungie would be moving the
    player's gear while claiming to be a preview."""
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-outfit-dry")
    await _seed(clean_db, uid)

    called = []
    monkeypatch.setattr("app.main.transfer_item",
                        lambda *a, **k: called.append("transfer"))
    monkeypatch.setattr("app.main.equip_item", lambda *a, **k: called.append("equip"))
    monkeypatch.setattr("app.main.get_profile", lambda *a, **k: called.append("profile"))

    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _CHAR, "dryRun": True,
    }, headers=_csrf(app_client))

    assert r.status_code == 200
    assert called == [], f"dry run reached Bungie: {called}"
    plan = r.json()["plan"]
    assert [p["instanceId"] for p in plan] == ["helm-1"]
    assert plan[0]["action"] == "move"


async def test_dry_run_reports_a_piece_worn_by_another_character_as_blocked(
    app_client, clean_db, monkeypatch,
):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-outfit-blocked")
    profile = json.loads(json.dumps(_PROFILE))
    profile["profileInventory"]["data"]["items"] = []
    profile["characterEquipment"]["data"] = {
        _TITAN: {"items": [{"itemInstanceId": "helm-1", "itemHash": 500}]},
    }
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "weapons_cache", json.dumps({"weapons": []}), 3600)
    await cache_repo.set(clean_db, uid, "armor_cache", json.dumps(_ARMOR), 3600)

    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _CHAR, "dryRun": True,
    }, headers=_csrf(app_client))

    assert r.status_code == 200
    assert r.json()["plan"][0]["action"] == "blocked"


# ---------------------------------------------------------------------------
# Stat focus
# ---------------------------------------------------------------------------

async def test_outfits_rejects_an_unknown_focus_stat(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-focus-bad")
    await _seed(clean_db, uid)
    r = await app_client.get("/api/outfits?focus=Grenade,Nonsense")
    assert r.status_code == 400
    assert "Nonsense" in r.json()["detail"]


async def test_outfits_rejects_more_than_three_focus_stats(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-focus-many")
    await _seed(clean_db, uid)
    r = await app_client.get("/api/outfits?focus=Health,Melee,Grenade,Super")
    assert r.status_code == 400


async def test_focus_replaces_the_seeded_priority_on_every_outfit(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-focus-ok")
    await _seed(clean_db, uid)
    r = await app_client.get("/api/outfits?focus=Super,Health")
    assert r.status_code == 200
    body = r.json()
    assert body["focus"] == ["Super", "Health"]
    assert all(o["statPriority"] == ["Super", "Health"] for o in body["outfits"])


async def test_apply_rebuilds_with_the_focus_it_was_given(app_client, clean_db, monkeypatch):
    """The preview must describe the outfit the page is showing.

    Two Helmets: one wins on Grenade (the seeded priority), the other on Super.
    Applying with focus=Super must plan the Super piece, not the seeded one.
    """
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-focus-apply")
    seeded = dict(_ARMOR[0], instanceId="helm-grenade",
                  stats={"Health": 0, "Melee": 0, "Grenade": 40,
                         "Super": 0, "Class": 0, "Weapons": 0})
    focused = dict(_ARMOR[0], instanceId="helm-super",
                   stats={"Health": 0, "Melee": 0, "Grenade": 0,
                          "Super": 40, "Class": 0, "Weapons": 0})
    profile = json.loads(json.dumps(_PROFILE))
    profile["profileInventory"]["data"]["items"] = [
        {"itemInstanceId": "helm-grenade", "itemHash": 500, "state": 0},
        {"itemInstanceId": "helm-super", "itemHash": 500, "state": 0},
    ]
    await cache_repo.set(clean_db, uid, "profile_cache", json.dumps(profile), 3600)
    await cache_repo.set(clean_db, uid, "weapons_cache", json.dumps({"weapons": []}), 3600)
    await cache_repo.set(clean_db, uid, "armor_cache", json.dumps([seeded, focused]), 3600)

    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _CHAR,
        "dryRun": True, "focus": ["Super"],
    }, headers=_csrf(app_client))

    assert r.status_code == 200
    assert [p["instanceId"] for p in r.json()["plan"]] == ["helm-super"]


async def test_apply_rejects_an_unknown_focus_stat(app_client, clean_db, monkeypatch):
    uid = await login_user(app_client, monkeypatch, bungie_id="bm-focus-apply-bad")
    await _seed(clean_db, uid)
    r = await app_client.post("/api/outfits/apply", json={
        "className": "Warlock", "subclass": "Solar", "characterId": _CHAR,
        "dryRun": True, "focus": ["Nonsense"],
    }, headers=_csrf(app_client))
    assert r.status_code == 400
