import json
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.bungie_client import (
    CLASS_TYPES, assemble_armor, assemble_weapons, equip_item,
    get_profile, pull_from_postmaster, transfer_item,
)
from app.bungie_client import BungieApiError
from app.bungie_oauth import refresh_tokens
from app.config import get_settings
from app import db
from app.deps import get_pool
from app.manifest import Manifest, load_cached_manifest, load_manifest
from app.perk_ratings import TIER_SCORE
from app.perk_scoring import score_by_perks
from app.recommend import element_for_subclass, recommend_weapons
from app.loadout_builder import build_loadout
from app.storage import get_conn, kv_get, kv_set
from scripts.migrate import apply_migrations
from app.auth import router as auth_router, get_current_user
from app.bungie_session import valid_access_token
from app.bungie_throttle import Throttle
from app.repositories import cache, perk_ratings as perk_ratings_repo, builds as builds_repo, user_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await db.create_pool(get_settings())
    await apply_migrations(pool)
    app.state.pool = pool
    app.state.throttle = Throttle(get_settings().bungie_throttle_concurrency)
    yield
    pool.close()
    await pool.wait_closed()


app = FastAPI(title="Destiny 2 Weapon Advisor", lifespan=lifespan)
app.include_router(auth_router)

# Every cache key derived from a single account's profile. Cleared together on
# account switch so no cross-account data can survive (keep this list complete).
_ACCOUNT_CACHE_KEYS = (
    "weapons_cache", "armor_cache", "profile_cache", "perk_desc_map", "perk_icon_map",
    "profile_membership_id",
)


class TransferBody(BaseModel):
    instanceId: str
    itemHash: int
    targetCharacterId: str
    equip: bool = False


class MembershipSelectBody(BaseModel):
    membershipType: int
    membershipId: str


class PerkRatingBody(BaseModel):
    name: str
    weaponType: str = ""
    rating: str
    reason: str = ""
    tags: list[str] = []
    notes: str = ""


class BuildBody(BaseModel):
    key: str
    data: dict


class ActivityBody(BaseModel):
    name: str
    data: dict


class TagBody(BaseModel):
    instanceId: str
    tag: str  # keep | junk | infuse | favorite | "" (clears)


class BulkTransferBody(BaseModel):
    items: list[dict]  # [{instanceId, itemHash}]
    targetCharacterId: str  # a character id, or "vault"
    equip: bool = False


class LoadoutBody(BaseModel):
    name: str
    characterId: str
    items: list[dict]  # [{instanceId, itemHash}]


class ApplyLoadoutBody(BaseModel):
    name: str


class ArmorSetBody(BaseModel):
    name: str
    className: str
    characterId: str
    tier: int
    items: list[dict]  # [{instanceId, itemHash, slot, name}]


class PullPostmasterBody(BaseModel):
    itemHash: int
    instanceId: str
    characterId: str
    stackSize: int = 1


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}



# _valid_access_token (SQLite single-user) retired; per-user callers use valid_access_token from bungie_session.


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
        "verdictReason": info.get("verdictReason", ""),
        "upgradePath": info.get("upgradePath"),
        "tags": info["tags"],
        "isDuplicate": info["is_duplicate"],
        "power": weapon.power,
        "ammoType": weapon.ammo_type,
        "frame": weapon.frame,
        "perkNames": weapon.perk_names,
        "stats": weapon.stats,
        "ratedPerks": info["rated"],
        "icon": weapon.icon,
        "equipped": weapon.equipped,
    }


async def _compute_weapons(pool, uid: int, manifest: Manifest, profile: dict) -> dict:
    settings = get_settings()
    owned = assemble_weapons(profile, manifest)
    desc_map: dict[str, str] = {}
    icon_map: dict[str, str] = {}
    for w in owned:
        for plug_hash in w.perks:
            name = manifest.name(plug_hash)
            if not name or name.startswith("Unknown ("):
                continue
            description = manifest.description(plug_hash)
            if description:
                desc_map[name] = description
            icon = manifest.icon(plug_hash)
            if icon:
                icon_map[name] = icon
    await cache.set(pool, uid, "perk_desc_map", json.dumps(desc_map), settings.user_cache_ttl_seconds)
    await cache.set(pool, uid, "perk_icon_map", json.dumps(icon_map), settings.user_cache_ttl_seconds)
    ratings = await perk_ratings_repo.load(pool, uid)
    scored = score_by_perks(owned, ratings)
    result = {
        "weapons": [weapon_to_dict(s["weapon"], s) for s in scored],
        "cachedAt": time.time(),
    }
    await cache.set(pool, uid, "weapons_cache", json.dumps(result), settings.user_cache_ttl_seconds)
    armor = assemble_armor(profile, manifest)
    await cache.set(pool, uid, "armor_cache", json.dumps([_armor_to_dict(a) for a in armor]), settings.user_cache_ttl_seconds)
    return result


def _armor_to_dict(a) -> dict:
    return {
        "instanceId": a.instance_id,
        "itemHash": a.item_hash,
        "name": a.name,
        "slot": a.slot,
        "className": a.class_name,
        "power": a.power,
        "isExotic": a.is_exotic,
        "isMasterworked": a.is_masterworked,
        "stats": a.stats,
        "location": a.location,
        "icon": a.icon,
        "equipped": a.equipped,
    }


async def _recompute_from_cache(pool, uid: int) -> bool:
    """Re-score the cached inventory with current ratings — no Bungie call."""
    profile_raw = await cache.get(pool, uid, "profile_cache")
    manifest = await load_cached_manifest(pool)
    if not profile_raw or manifest is None:
        return False
    await _compute_weapons(pool, uid, manifest, json.loads(profile_raw))
    return True


@app.get("/api/weapons")
async def weapons(
    request: Request,
    refresh: bool = False,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    if not refresh:
        cached = await cache.get(pool, uid, "weapons_cache")
        if cached:
            return json.loads(cached)
    throttle = request.app.state.throttle
    async with httpx.AsyncClient(
        timeout=120.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        manifest = await load_manifest(client, pool, throttle)
        profile = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
    await cache.set(pool, uid, "profile_cache", json.dumps(profile), settings.user_cache_ttl_seconds)
    await cache.set(pool, uid, "profile_membership_id", mid, settings.user_cache_ttl_seconds)
    return await _compute_weapons(pool, uid, manifest, profile)


def _resolve_rec_context(activities: list, context: str) -> dict:
    if context == "general-pve":
        return {"label": "General (PvE)", "element": None}
    if context == "general-pvp":
        return {"label": "General (PvP)", "element": None}
    for activity in activities:
        if activity.get("name") == context:
            return {
                "label": activity["name"],
                "element": element_for_subclass(activity.get("recommendedSubclass", "")),
            }
    return {"label": context, "element": None}


@app.get("/api/recommendations")
async def recommendations(
    context: str = "general-pve",
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    cached = await cache.get(pool, uid, "weapons_cache")
    if not cached and await _recompute_from_cache(pool, uid):
        cached = await cache.get(pool, uid, "weapons_cache")
    weapons_list = json.loads(cached).get("weapons", []) if cached else []
    activities = await builds_repo.load_activities(pool, uid)
    ctx = _resolve_rec_context(activities, context)
    return recommend_weapons(weapons_list, ctx)


@app.get("/api/loadout-suggestion")
async def loadout_suggestion(
    activity: str,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    activities = await builds_repo.load_activities(pool, uid)
    match = next((a for a in activities if a.get("name") == activity), None)
    if match is None:
        raise HTTPException(status_code=404, detail=f"Unknown activity: {activity}")
    cached = await cache.get(pool, uid, "weapons_cache")
    if not cached and await _recompute_from_cache(pool, uid):
        cached = await cache.get(pool, uid, "weapons_cache")
    weapons_list = json.loads(cached).get("weapons", []) if cached else []
    key = f"{match.get('recommendedClass', '')}|{match.get('recommendedSubclass', '')}"
    builds = await builds_repo.load_builds(pool, uid)
    build = builds.get(key)
    return build_loadout(weapons_list, match, build)


@app.get("/api/perks")
async def get_perks(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    ratings = await perk_ratings_repo.load(pool, uid)
    desc_raw = await cache.get(pool, uid, "perk_desc_map")
    descriptions = json.loads(desc_raw) if desc_raw else {}
    icon_raw = await cache.get(pool, uid, "perk_icon_map")
    icons = json.loads(icon_raw) if icon_raw else {}
    cached = await cache.get(pool, uid, "weapons_cache")
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
                "notes": ratings.notes(name, wtype),
                "description": descriptions.get(name, ""),
                "icon": icons.get(name, ""),
                "tags": info.get("tags", []) if info else [],
                "isOverride": ratings.is_override(name, wtype),
            })
        perks.sort(key=lambda p: (-TIER_SCORE.get(p["rating"], 0), p["name"]))
        weapon_types.append({"weaponType": wtype, "perks": perks})
    return {"weaponTypes": weapon_types}


@app.put("/api/perks")
async def put_perk(
    body: PerkRatingBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    await perk_ratings_repo.save(
        pool, uid, body.name, body.weaponType, body.rating, body.reason, body.tags, body.notes
    )
    await _recompute_from_cache(pool, uid)
    return {"ok": True}


@app.get("/api/builds")
async def get_builds(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    return {"builds": await builds_repo.load_builds(pool, uid)}


@app.put("/api/builds")
async def put_build(
    body: BuildBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    await builds_repo.save_build(pool, uid, body.key, body.data)
    return {"ok": True}


@app.get("/api/tags")
async def get_tags(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    return {"tags": await user_tables.get_tags(pool, uid)}


@app.put("/api/tags")
async def put_tag(
    body: TagBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    await user_tables.set_tag(pool, uid, body.instanceId, body.tag)
    return {"ok": True}


@app.get("/api/activities")
async def get_activities(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    return {"activities": await builds_repo.load_activities(pool, uid)}


@app.put("/api/activities")
async def put_activity(
    body: ActivityBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    await builds_repo.save_activity(pool, uid, body.name, body.data)
    return {"ok": True}


# Activity types worth surfacing for build/loadout planning.
_ACTIVITY_TYPE_KEEP = {"raid", "dungeon", "nightfall", "exotic mission", "story"}


@app.get("/api/activities/catalog")
async def activities_catalog(
    request: Request,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    """Distinct build-relevant activity names pulled from the Destiny manifest
    (raids/dungeons/nightfalls/etc.), cached globally after the first fetch.
    This data is account-independent so it uses the manifest cache, not per-user cache."""
    settings = get_settings()
    cached = await cache.manifest_get(pool, "activity_catalog")
    if cached:
        return {"catalog": json.loads(cached)}
    throttle = request.app.state.throttle
    async with httpx.AsyncClient(
        timeout=120.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        meta = await throttle.run(lambda: client.get("https://www.bungie.net/Platform/Destiny2/Manifest/"))
        meta.raise_for_status()
        paths = meta.json()["Response"]["jsonWorldComponentContentPaths"]["en"]
        adefs = (await throttle.run(lambda: client.get(
            "https://www.bungie.net" + paths["DestinyActivityDefinition"], timeout=120.0))).json()
        atypes = (await throttle.run(lambda: client.get(
            "https://www.bungie.net" + paths["DestinyActivityTypeDefinition"], timeout=60.0))).json()
    type_name = {int(k): v.get("displayProperties", {}).get("name", "") for k, v in atypes.items()}
    seen: dict[str, str] = {}
    for a in adefs.values():
        name = a.get("displayProperties", {}).get("name", "")
        tname = type_name.get(a.get("activityTypeHash"), "")
        if name and tname.lower() in _ACTIVITY_TYPE_KEEP and name not in seen:
            seen[name] = tname
    catalog = sorted(
        ({"name": n, "type": t} for n, t in seen.items()),
        key=lambda x: (x["type"], x["name"]),
    )
    await cache.manifest_set(pool, "activity_catalog", json.dumps(catalog), "v1")
    return {"catalog": catalog}


@app.get("/api/armor")
async def get_armor(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    cached = await cache.get(pool, uid, "armor_cache")
    armor = json.loads(cached) if cached else []
    stat_names: set[str] = set()
    for piece in armor:
        stat_names.update(piece["stats"].keys())
    return {"armor": armor, "statNames": sorted(stat_names)}


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


@app.get("/api/memberships")
async def list_memberships() -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    row = conn.execute("SELECT membership_type, membership_id FROM tokens WHERE id = 1").fetchone()
    active = {"type": row[0], "id": row[1]} if row else None
    async with httpx.AsyncClient(
        timeout=30.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, _mt, _mid = await _valid_access_token(settings, conn, client)
        memberships = await get_memberships(access, settings, client)
    out = [
        {"type": m["membershipType"], "id": m["membershipId"], "displayName": m.get("displayName", "")}
        for m in memberships["destinyMemberships"]
    ]
    return {"memberships": out, "active": active}


@app.post("/api/memberships/select")
def select_membership(body: MembershipSelectBody) -> dict:
    conn = get_conn(get_settings().db_path)
    conn.execute(
        "UPDATE tokens SET membership_type = ?, membership_id = ? WHERE id = 1",
        (body.membershipType, body.membershipId),
    )
    for key in _ACCOUNT_CACHE_KEYS:
        conn.execute("DELETE FROM kv WHERE key = ?", (key,))
    conn.commit()
    return {"ok": True}


@app.get("/api/counts")
async def get_counts(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    weapons_raw = await cache.get(pool, uid, "weapons_cache")
    armor_raw = await cache.get(pool, uid, "armor_cache")
    weapons = json.loads(weapons_raw)["weapons"] if weapons_raw else []
    armor = json.loads(armor_raw) if armor_raw else []
    return {
        "weapons": len(weapons),
        "armor": len(armor),
        "vaultWeapons": sum(1 for w in weapons if w.get("location") == "Vault"),
        "vaultArmor": sum(1 for a in armor if a.get("location") == "Vault"),
    }


@app.get("/api/characters")
async def get_characters(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    profile_raw = await cache.get(pool, uid, "profile_cache")
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


async def _move_one(client, settings, access, mtype, profile, instance_id, item_hash, target, equip):
    """Move one item to `target` ('vault' or a character id), optionally equip.
    Raises BungieApiError on a problem (e.g. equipped on another character)."""
    source = _find_item_location(profile, instance_id)
    if source is None:
        raise BungieApiError("Item not found in your cached inventory.")
    if source.startswith("equipped:"):
        if source.split(":", 1)[1] == target:
            return  # already equipped on the target — nothing to do
        raise BungieApiError("Item is equipped on another character — unequip it first.")
    if target == "vault":
        if source != "vault":
            await transfer_item(mtype, item_hash, instance_id, source, True, access, settings, client)
        return
    if source != target:
        if source != "vault":
            await transfer_item(mtype, item_hash, instance_id, source, True, access, settings, client)
        await transfer_item(mtype, item_hash, instance_id, target, False, access, settings, client)
    if equip:
        await equip_item(mtype, instance_id, target, access, settings, client)


async def _save_profile(pool, uid: int, fresh: dict, mid: str) -> None:
    settings = get_settings()
    await cache.set(pool, uid, "profile_cache", json.dumps(fresh), settings.user_cache_ttl_seconds)
    await cache.set(pool, uid, "profile_membership_id", mid, settings.user_cache_ttl_seconds)
    manifest = await load_cached_manifest(pool)
    if manifest is not None:
        await _compute_weapons(pool, uid, manifest, fresh)


async def _load_profile_or_400(pool, uid: int) -> dict:
    raw = await cache.get(pool, uid, "profile_cache")
    if not raw:
        raise HTTPException(status_code=400, detail="Load your inventory first.")
    return json.loads(raw)


@app.post("/api/transfer")
async def transfer(body: TransferBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    profile = _load_profile_or_400(conn)
    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        if kv_get(conn, "profile_membership_id") != mid:
            raise HTTPException(status_code=400, detail="Your cached inventory is for a different "
                                "account — open Weapons and Refresh, then try the move again.")
        try:
            await _move_one(client, settings, access, mtype, profile, body.instanceId,
                            body.itemHash, body.targetCharacterId, body.equip)
        except BungieApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=400, detail=f"Bungie rejected the move (HTTP "
                                f"{exc.response.status_code}). If you haven't re-logged-in since "
                                "adding the move permission, click Re-login and try again.")
        fresh = await get_profile(mtype, mid, access, settings, client)
    _save_profile(conn, fresh, mid)
    return {"ok": True}


@app.post("/api/transfer/bulk")
async def transfer_bulk(body: BulkTransferBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    profile = _load_profile_or_400(conn)
    results = []
    async with httpx.AsyncClient(
        timeout=180.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        if kv_get(conn, "profile_membership_id") != mid:
            raise HTTPException(status_code=400, detail="Cached inventory is for a different "
                                "account — Refresh first.")
        for it in body.items:
            try:
                await _move_one(client, settings, access, mtype, profile, it["instanceId"],
                                it["itemHash"], body.targetCharacterId, body.equip)
                results.append({"instanceId": it["instanceId"], "ok": True})
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                results.append({"instanceId": it["instanceId"], "ok": False, "error": str(exc)})
        fresh = await get_profile(mtype, mid, access, settings, client)
    _save_profile(conn, fresh, mid)
    return {"results": results}


_POSTMASTER_BUCKET = 215593132


@app.get("/api/postmaster")
def get_postmaster() -> dict:
    conn = get_conn(get_settings().db_path)
    profile_raw = kv_get(conn, "profile_cache")
    manifest = load_cached_manifest(conn)
    if not profile_raw or manifest is None:
        return {"items": []}
    profile = json.loads(profile_raw)
    chars = profile.get("characters", {}).get("data", {})
    items = []
    for cid, bucket in profile.get("characterInventories", {}).get("data", {}).items():
        for it in bucket.get("items", []):
            if it.get("bucketHash") == _POSTMASTER_BUCKET:
                ih = it.get("itemHash")
                items.append({
                    "instanceId": it.get("itemInstanceId", ""),
                    "itemHash": ih,
                    "name": manifest.name(ih),
                    "icon": manifest.icon(ih),
                    "characterId": cid,
                    "className": CLASS_TYPES.get(chars.get(cid, {}).get("classType"), "Character"),
                    "quantity": it.get("quantity", 1),
                })
    return {"items": items}


@app.post("/api/postmaster/pull")
async def pull_postmaster(body: PullPostmasterBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        try:
            await pull_from_postmaster(mtype, body.itemHash, body.instanceId, body.characterId,
                                       body.stackSize, access, settings, client)
        except (BungieApiError, httpx.HTTPStatusError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        fresh = await get_profile(mtype, mid, access, settings, client)
    _save_profile(conn, fresh, mid)
    return {"ok": True}


def _ensure_loadouts(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS loadouts (name TEXT PRIMARY KEY, data TEXT)")
    conn.commit()


@app.get("/api/loadouts")
def get_loadouts() -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_loadouts(conn)
    out = []
    for name, data in conn.execute("SELECT name, data FROM loadouts"):
        d = json.loads(data)
        d["name"] = name
        out.append(d)
    return {"loadouts": out}


@app.put("/api/loadouts")
def put_loadout(body: LoadoutBody) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_loadouts(conn)
    data = json.dumps({"characterId": body.characterId, "items": body.items})
    conn.execute(
        "INSERT INTO loadouts (name, data) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
        (body.name, data),
    )
    conn.commit()
    return {"ok": True}


@app.delete("/api/loadouts/{name}")
def delete_loadout(name: str) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_loadouts(conn)
    conn.execute("DELETE FROM loadouts WHERE name = ?", (name,))
    conn.commit()
    return {"ok": True}


def _ensure_armor_sets(conn) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS armor_sets (name TEXT PRIMARY KEY, data TEXT)")
    conn.commit()


@app.get("/api/armor-sets")
def get_armor_sets() -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    out = []
    for name, data in conn.execute("SELECT name, data FROM armor_sets"):
        out.append({"name": name, **json.loads(data)})
    return {"armorSets": out}


@app.put("/api/armor-sets")
def put_armor_set(body: ArmorSetBody) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    data = json.dumps({
        "className": body.className,
        "characterId": body.characterId,
        "tier": body.tier,
        "items": body.items,
    })
    conn.execute(
        "INSERT INTO armor_sets (name, data) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
        (body.name, data),
    )
    conn.commit()
    return {"ok": True}


@app.delete("/api/armor-sets/{name}")
def delete_armor_set(name: str) -> dict:
    conn = get_conn(get_settings().db_path)
    _ensure_armor_sets(conn)
    conn.execute("DELETE FROM armor_sets WHERE name = ?", (name,))
    conn.commit()
    return {"ok": True}


@app.post("/api/armor-sets/apply")
async def apply_armor_set(body: ApplyLoadoutBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    _ensure_armor_sets(conn)
    row = conn.execute("SELECT data FROM armor_sets WHERE name = ?", (body.name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Armor set not found.")
    armor_set = json.loads(row[0])
    results = await _apply_item_set(conn, settings, armor_set["items"], armor_set["characterId"])
    return {"results": results}


async def _apply_item_set(conn, settings, items: list[dict], target: str) -> list[dict]:
    """Move+equip each {instanceId, itemHash} item to the target character.
    Returns per-item results. Shared by loadout-apply and armor-set-apply."""
    profile = _load_profile_or_400(conn)
    results = []
    async with httpx.AsyncClient(
        timeout=180.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await _valid_access_token(settings, conn, client)
        for it in items:
            try:
                await _move_one(client, settings, access, mtype, profile, it["instanceId"],
                                it["itemHash"], target, True)
                results.append({"instanceId": it["instanceId"], "ok": True})
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                results.append({"instanceId": it["instanceId"], "ok": False, "error": str(exc)})
        fresh = await get_profile(mtype, mid, access, settings, client)
    _save_profile(conn, fresh, mid)
    return results


@app.post("/api/loadouts/apply")
async def apply_loadout(body: ApplyLoadoutBody) -> dict:
    settings = get_settings()
    conn = get_conn(settings.db_path)
    _ensure_loadouts(conn)
    row = conn.execute("SELECT data FROM loadouts WHERE name = ?", (body.name,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Loadout not found.")
    loadout = json.loads(row[0])
    results = await _apply_item_set(conn, settings, loadout["items"], loadout["characterId"])
    return {"results": results}


# Serve the built frontend (production single-server mode). Declared after all
# /api and /callback routes so those take priority; "/" falls through to the SPA.
_FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")


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
