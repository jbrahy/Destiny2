import json
import secrets
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from app.bungie_client import (
    CLASS_TYPES, assemble_weapons, equip_item, get_memberships, get_profile, transfer_item,
)
from app.bungie_client import BungieApiError
from app.bungie_oauth import build_authorize_url, exchange_code, refresh_tokens
from app.config import get_settings
from app.manifest import Manifest, load_cached_manifest, load_manifest
from app.perk_ratings import TIER_SCORE, load_ratings, save_rating
from app.perk_scoring import score_by_perks
from app.storage import get_conn, kv_get, kv_set

app = FastAPI(title="Destiny 2 Weapon Advisor")
_states: set[str] = set()


def recommendation_to_dict(rec, manifest: Manifest) -> dict:
    return {
        "instanceId": rec.weapon.instance_id,
        "name": rec.weapon.name,
        "weaponType": rec.weapon.weapon_type,
        "element": rec.weapon.element,
        "location": rec.weapon.location,
        "isMasterworked": rec.weapon.is_masterworked,
        "verdict": rec.verdict.value,
        "matchedPerks": [manifest.name(p) for p in rec.matched_perks],
        "note": rec.note,
        "tags": rec.tags,
        "isDuplicate": rec.is_duplicate,
        "power": rec.weapon.power,
        "ammoType": rec.weapon.ammo_type,
        "frame": rec.weapon.frame,
        "perkNames": rec.weapon.perk_names,
        "stats": rec.weapon.stats,
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, bool]:
    conn = get_conn(get_settings().db_path)
    row = conn.execute("SELECT access_token FROM tokens WHERE id = 1").fetchone()
    return {"authenticated": bool(row and row[0])}


@app.get("/api/login")
def login() -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(16)
    _states.add(state)
    url = build_authorize_url(settings.bungie_client_id, settings.redirect_uri, state)
    return RedirectResponse(url, status_code=307)


@app.get("/callback")
async def callback(code: str, state: str) -> RedirectResponse:
    if state not in _states:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _states.discard(state)
    settings = get_settings()
    conn = get_conn(settings.db_path)
    async with httpx.AsyncClient(
        timeout=30.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        tokens = await exchange_code(code, settings, client)
        access = tokens["access_token"]
        memberships = await get_memberships(access, settings, client)
        primary = memberships["destinyMemberships"][0]
    conn.execute("DELETE FROM tokens")
    conn.execute(
        "INSERT INTO tokens (id, access_token, refresh_token, expires_at, "
        "membership_type, membership_id) VALUES (1, ?, ?, ?, ?, ?)",
        (
            access,
            tokens["refresh_token"],
            time.time() + tokens["expires_in"],
            primary["membershipType"],
            primary["membershipId"],
        ),
    )
    conn.commit()
    return RedirectResponse(settings.frontend_url, status_code=307)


async def _valid_access_token(settings, conn, client) -> tuple[str, int, str]:
    row = conn.execute(
        "SELECT access_token, refresh_token, expires_at, membership_type, membership_id "
        "FROM tokens WHERE id = 1"
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    access, refresh, expires_at, mtype, mid = row
    if time.time() > expires_at - 60:
        try:
            tokens = await refresh_tokens(refresh, settings, client)
        except Exception:
            conn.execute("DELETE FROM tokens")
            conn.commit()
            raise HTTPException(status_code=401, detail="Session expired; please log in again.")
        access = tokens["access_token"]
        conn.execute(
            "UPDATE tokens SET access_token = ?, refresh_token = ?, expires_at = ? WHERE id = 1",
            (access, tokens["refresh_token"], time.time() + tokens["expires_in"]),
        )
        conn.commit()
    return access, mtype, mid


def weapon_to_dict(weapon, info: dict) -> dict:
    return {
        "instanceId": weapon.instance_id,
        "itemHash": weapon.item_hash,
        "name": weapon.name,
        "weaponType": weapon.weapon_type,
        "element": weapon.element,
        "location": weapon.location,
        "isMasterworked": weapon.is_masterworked,
        "verdict": info["verdict"].value,
        "matchedPerks": [r["name"] for r in info["rated"] if TIER_SCORE.get(r["rating"], 0) >= 4],
        "note": info["note"],
        "tags": info["tags"],
        "isDuplicate": info["is_duplicate"],
        "power": weapon.power,
        "ammoType": weapon.ammo_type,
        "frame": weapon.frame,
        "perkNames": weapon.perk_names,
        "stats": weapon.stats,
        "ratedPerks": info["rated"],
    }


def _compute_weapons(conn, manifest: Manifest, profile: dict) -> dict:
    owned = assemble_weapons(profile, manifest)
    ratings = load_ratings(conn)
    scored = score_by_perks(owned, ratings)
    result = {
        "weapons": [weapon_to_dict(s["weapon"], s) for s in scored],
        "cachedAt": time.time(),
    }
    kv_set(conn, "weapons_cache", json.dumps(result))
    return result


def _recompute_from_cache(conn) -> bool:
    """Re-score the cached inventory with current ratings — no Bungie call."""
    profile_raw = kv_get(conn, "profile_cache")
    manifest = load_cached_manifest(conn)
    if not profile_raw or manifest is None:
        return False
    _compute_weapons(conn, manifest, json.loads(profile_raw))
    return True


@app.get("/api/weapons")
async def weapons(refresh: bool = False) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    if not refresh:
        cached = kv_get(conn, "weapons_cache")
        if cached:
            return json.loads(cached)
    async with httpx.AsyncClient(
        timeout=120.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        manifest = await load_manifest(client, conn)
        profile = await get_profile(mtype, mid, access, settings, client)
    kv_set(conn, "profile_cache", json.dumps(profile))
    return _compute_weapons(conn, manifest, profile)


@app.get("/api/perks")
def get_perks() -> dict:
    conn = get_conn(get_settings().db_path)
    ratings = load_ratings(conn)
    cached = kv_get(conn, "weapons_cache")
    by_type: dict[str, set] = {}
    if cached:
        for w in json.loads(cached)["weapons"]:
            wtype = w["weaponType"] or "Other"
            by_type.setdefault(wtype, set()).update(w["perkNames"])

    weapon_types = []
    for wtype in sorted(by_type):
        perks = []
        for name in by_type[wtype]:
            info = ratings.get(name, wtype)
            perks.append({
                "name": name,
                "rating": info["rating"] if info else "",
                "reason": info.get("reason", "") if info else "",
                "tags": info.get("tags", []) if info else [],
                "isOverride": ratings.is_override(name, wtype),
            })
        perks.sort(key=lambda p: (-TIER_SCORE.get(p["rating"], 0), p["name"]))
        weapon_types.append({"weaponType": wtype, "perks": perks})
    return {"weaponTypes": weapon_types}


@app.put("/api/perks")
def put_perk(payload: dict) -> dict:
    conn = get_conn(get_settings().db_path)
    save_rating(
        conn,
        payload["name"],
        payload.get("weaponType", ""),
        payload["rating"],
        payload.get("reason", ""),
        payload.get("tags", []),
    )
    _recompute_from_cache(conn)
    return {"ok": True}


def _find_item_location(profile: dict, instance_id: str) -> str | None:
    """Return the character id holding the item, 'vault', or None if not found.
    Returns 'equipped:<charId>' when the item is currently equipped."""
    for cid, bucket in profile.get("characterEquipment", {}).get("data", {}).items():
        for it in bucket.get("items", []):
            if it.get("itemInstanceId") == instance_id:
                return f"equipped:{cid}"
    for cid, bucket in profile.get("characterInventories", {}).get("data", {}).items():
        for it in bucket.get("items", []):
            if it.get("itemInstanceId") == instance_id:
                return cid
    for it in profile.get("profileInventory", {}).get("data", {}).get("items", []):
        if it.get("itemInstanceId") == instance_id:
            return "vault"
    return None


@app.get("/api/characters")
def get_characters() -> dict:
    conn = get_conn(get_settings().db_path)
    profile_raw = kv_get(conn, "profile_cache")
    if not profile_raw:
        return {"characters": []}
    chars = json.loads(profile_raw).get("characters", {}).get("data", {})
    out = [
        {
            "id": cid,
            "className": CLASS_TYPES.get(c.get("classType"), "Character"),
            "light": c.get("light", 0),
            "lastPlayed": c.get("dateLastPlayed", ""),
        }
        for cid, c in chars.items()
    ]
    out.sort(key=lambda x: x["lastPlayed"], reverse=True)
    for i, o in enumerate(out):
        o["current"] = i == 0
    return {"characters": out}


@app.post("/api/transfer")
async def transfer(payload: dict) -> dict:
    instance_id = payload["instanceId"]
    item_hash = payload["itemHash"]
    target = payload["targetCharacterId"]
    do_equip = payload.get("equip", False)
    settings = get_settings()
    conn = get_conn(settings.db_path)
    profile_raw = kv_get(conn, "profile_cache")
    if not profile_raw:
        raise HTTPException(status_code=400, detail="Load your inventory first.")
    profile = json.loads(profile_raw)
    source = _find_item_location(profile, instance_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Item not found in your cached inventory.")
    if source.startswith("equipped:"):
        raise HTTPException(
            status_code=400,
            detail="That weapon is currently equipped — equip something else first, then move it.",
        )

    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        try:
            if source != target:
                if source != "vault":
                    await transfer_item(
                        mtype, item_hash, instance_id, source, True, access, settings, client
                    )
                await transfer_item(
                    mtype, item_hash, instance_id, target, False, access, settings, client
                )
            if do_equip:
                await equip_item(mtype, instance_id, target, access, settings, client)
        except BungieApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        fresh = await get_profile(mtype, mid, access, settings, client)
    kv_set(conn, "profile_cache", json.dumps(fresh))
    manifest = load_cached_manifest(conn)
    if manifest is not None:
        _compute_weapons(conn, manifest, fresh)
    return {"ok": True}


def run() -> None:
    import uvicorn

    from app.certs import ensure_self_signed_cert

    cert_path, key_path = ensure_self_signed_cert(".certs")
    uvicorn.run(
        "app.main:app", host="localhost", port=8443,
        ssl_certfile=cert_path, ssl_keyfile=key_path,
    )


if __name__ == "__main__":
    run()
