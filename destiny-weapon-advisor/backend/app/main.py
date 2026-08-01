import json
import os
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.bungie_client import (
    CLASS_TYPES, assemble_armor, assemble_weapons, equip_item,
    get_memberships, get_profile, pull_from_postmaster, transfer_item,
)
from app.bungie_client import BungieApiError
from app.bungie_client import set_item_lock_state
from app.bungie_client import _LOCKED_STATE
from app.bungie_oauth import refresh_tokens
from app.armor_scoring import focus as armor_focus, load_bands, score_armor, waste as armor_waste
from app.armor_set_bonuses import set_bonuses
from app.config import get_settings
from app import db
from app import dismantle as dismantle_logic
from app.chase import chase_candidates
from app.deps import get_pool
from app.manifest import Manifest, load_cached_manifest, load_manifest
from app.perk_ratings import TIER_SCORE
from app.perk_scoring import score_by_perks
from app.recommend import element_for_subclass, recommend_weapons
from app.loadout_builder import build_loadout
from app.outfits import build_all_outfits, plan_apply
from scripts.migrate import apply_migrations
from app.auth import router as auth_router, get_current_user, require_csrf
from app.ads import router as ads_router
from app.bungie_session import valid_access_token
from app.bungie_throttle import Throttle
from app.repositories import cache, perk_ratings as perk_ratings_repo, builds as builds_repo, tokens, user_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.cookie_secure:
        if not settings.token_enc_key:
            raise RuntimeError("token_enc_key must be set in production (cookie_secure=true)")
        if not settings.session_secret:
            raise RuntimeError("session_secret must be set in production (cookie_secure=true)")
    pool = await db.create_pool(settings)
    await apply_migrations(pool)
    app.state.pool = pool
    app.state.throttle = Throttle(settings.bungie_throttle_concurrency)
    yield
    pool.close()
    await pool.wait_closed()


app = FastAPI(title="Destiny 2 Weapon Advisor", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(ads_router)

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


_ALLOWED_TAGS = {"keep", "junk", "infuse", "favorite", ""}
_MAX_BULK_TAGS = 1000


class BulkTagBody(BaseModel):
    instanceIds: list[str] = Field(max_length=_MAX_BULK_TAGS)
    tag: str  # keep | junk | infuse | favorite | "" (clears)

    @field_validator("tag")
    @classmethod
    def _known_tag(cls, value: str) -> str:
        """Reject typos rather than persisting an unusable tag."""
        if value not in _ALLOWED_TAGS:
            raise ValueError(f"unknown tag {value!r}")
        return value


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


class ApplyOutfitBody(BaseModel):
    className: str
    subclass: str
    characterId: str
    dryRun: bool = True


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


class DismantlePreviewBody(BaseModel):
    characterId: str


class DismantleSweepBody(BaseModel):
    characterId: str
    instanceIds: list[str]
    overrides: list[str] = []


class DismantleUndoBody(BaseModel):
    characterId: str


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
        "isExotic": weapon.is_exotic,
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
        "isCrafted": weapon.is_crafted,
        # "shapeable" means the verdict describes what this weapon COULD be
        # shaped into, not what it currently holds -- label it as such in the UI.
        "scoredFrom": info.get("scored_from", "current"),
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
    scored = score_by_perks(owned, ratings, use_potential=settings.score_crafted_potential)
    result = {
        "weapons": [weapon_to_dict(s["weapon"], s) for s in scored],
        "cachedAt": time.time(),
    }
    await cache.set(pool, uid, "weapons_cache", json.dumps(result), settings.user_cache_ttl_seconds)
    armor = assemble_armor(profile, manifest)
    bands = load_bands()
    await cache.set(pool, uid, "armor_cache",
                    json.dumps([_armor_to_dict(a, manifest, bands) for a in armor]),
                    settings.user_cache_ttl_seconds)
    return result


def _armor_to_dict(a, manifest: Manifest, bands: dict[str, int]) -> dict:
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
        "setName": a.set_name,
        "setHash": a.set_hash,
        "setBonuses": set_bonuses(a.set_hash, manifest) if a.set_hash else [],
        "verdict": score_armor(a, bands).value,
        "focus": armor_focus(a.stats),
        "waste": armor_waste(a.stats),
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


@app.get("/api/chase")
async def get_chase(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    """Weapons you own whose roll pool allows a better roll than your best copy.

    Read-only, and derived from the cached profile — the trait pool comes from
    the manifest, so no Bungie call is needed.
    """
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    manifest = await load_cached_manifest(pool)
    if manifest is None:
        raise HTTPException(status_code=400, detail="Load your inventory first.")
    weapons = assemble_weapons(profile, manifest)
    ratings = await perk_ratings_repo.load(pool, uid)
    return {"chase": chase_candidates(weapons, manifest, ratings)}


async def _outfits_or_400(pool, uid: int) -> list[dict]:
    """Rebuild every outfit from the cached inventory, or 400 if there is none."""
    weapons_raw = await cache.get(pool, uid, "weapons_cache")
    armor_raw = await cache.get(pool, uid, "armor_cache")
    if not weapons_raw or not armor_raw:
        raise HTTPException(status_code=400, detail="Load your inventory first.")
    weapons = json.loads(weapons_raw).get("weapons", [])
    armor = json.loads(armor_raw)
    builds = await builds_repo.load_builds(pool, uid)
    return build_all_outfits(builds, weapons, armor)


@app.get("/api/outfits")
async def get_outfits(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    """One complete outfit per class/subclass, from cached inventory.

    Read-only: no Bungie calls, nothing is equipped or modified.
    """
    return {"outfits": await _outfits_or_400(pool, current_user["user_id"])}


@app.post("/api/outfits/apply")
async def apply_outfit(
    request: Request,
    body: ApplyOutfitBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Transfer and equip a whole outfit onto one of your characters.

    The outfit is rebuilt server-side from the caller's own cached inventory —
    the client sends only which outfit it wants. Accepting a caller-supplied
    list of instance ids would make this a general "equip anything" primitive,
    which is a much larger thing to secure than "equip the outfit you already
    computed".

    dryRun (the default) classifies every item without touching Bungie, and is
    what fills the confirm dialog.
    """
    uid = current_user["user_id"]
    outfits = await _outfits_or_400(pool, uid)
    outfit = next(
        (o for o in outfits
         if o["className"] == body.className and o["subclass"] == body.subclass),
        None,
    )
    if outfit is None:
        raise HTTPException(status_code=404, detail="No outfit for that class and subclass.")

    profile = await _load_profile_or_400(pool, uid)
    chars = profile.get("characters", {}).get("data", {})
    char = chars.get(body.characterId)
    if char is None:
        raise HTTPException(status_code=400, detail="That character is not on your account.")
    char_class = CLASS_TYPES.get(char.get("classType"), "Character")
    if char_class != body.className:
        raise HTTPException(
            status_code=400,
            detail=f"That is a {char_class}; this outfit is for a {body.className}.",
        )

    plan = plan_apply(outfit, body.characterId,
                      lambda iid: _find_item_location(profile, iid))
    if body.dryRun:
        return {"plan": plan, "results": []}

    movable = [p for p in plan if p["action"] == "move"]
    results = await _apply_item_set(
        pool, uid, get_settings(), request, movable, body.characterId,
    )
    return {"plan": plan, "results": results}


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


@app.post("/api/tags/bulk")
async def put_tags_bulk(
    body: BulkTagBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Apply one tag to many instances — e.g. tag every dismantle suggestion junk."""
    uid = current_user["user_id"]
    count = await user_tables.set_tags_bulk(pool, uid, body.instanceIds, body.tag)
    return {"ok": True, "count": count}


def _candidate_to_dict(c) -> dict:
    return {
        "instanceId": c.instance_id,
        "itemHash": c.item_hash,
        "name": c.name,
        "icon": c.icon,
        "power": c.power,
        # Serialised as a string so it keys directly into plan.perBucket, whose
        # keys are stringified bucket hashes. Without this the UI cannot tell
        # which bucket a candidate consumes and can only sum free space across
        # all three, overstating what fits for a bucket-concentrated selection.
        "bucketHash": str(c.bucket_hash),
        "verdict": c.verdict,
        "source": c.source,
        "reason": c.reason,
        "blocked": c.blocked,
        "overridable": c.overridable,
    }


def _postmaster_instance_ids(profile: dict) -> set[str]:
    """Instance ids currently sitting in a character's postmaster.

    Postmaster items live in characterInventories like any other held item, but
    only the raw profile shows it — a Candidate's bucket_hash comes from the
    manifest definition, so a postmaster hand cannon reports Kinetic and looks
    ordinary to the (pure) planner. Worse, when it is already on the sweep's
    target character _move_one sees source == target and transfers nothing, so
    the item would simply be unlocked in place, in the postmaster."""
    out: set[str] = set()
    for bucket in profile.get("characterInventories", {}).get("data", {}).values():
        for item in bucket.get("items", []):
            instance_id = item.get("itemInstanceId")
            if instance_id and item.get("bucketHash") == _POSTMASTER_BUCKET:
                out.add(instance_id)
    return out


async def _sweep_candidates(pool, uid: int, profile: dict) -> list:
    """Score the inventory and classify it into sweep candidates."""
    manifest = await load_cached_manifest(pool)
    if manifest is None:
        raise HTTPException(status_code=400, detail="Manifest not loaded yet — open Weapons and Refresh.")
    weapons = assemble_weapons(profile, manifest)
    ratings = await perk_ratings_repo.load(pool, uid)
    scored = score_by_perks(weapons, ratings)
    tags = await user_tables.get_tags(pool, uid)
    candidates = dismantle_logic.classify(scored, tags)
    # Weapons only, never postmaster. Dropped here rather than in dismantle.py,
    # which is pure and only ever sees manifest-derived bucket hashes.
    in_postmaster = _postmaster_instance_ids(profile)
    return [c for c in candidates if c.instance_id not in in_postmaster]


@app.post("/api/dismantle/preview")
async def dismantle_preview(
    body: DismantlePreviewBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    """What a sweep would stage. Reports blocked items rather than hiding them."""
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    candidates = await _sweep_candidates(pool, uid, profile)
    occupancy = dismantle_logic.bucket_occupancy(profile, body.characterId)
    # Plan over the non-blocked candidates so the UI can show what would fit.
    plan = dismantle_logic.plan_batch(
        candidates, [c.instance_id for c in candidates if not c.blocked], occupancy
    )
    # Staged sweeps are scoped per Destiny membership (see user_sweep_items),
    # so read from the same membership id the cached profile was built from.
    mid = await cache.get(pool, uid, "profile_membership_id")
    return {
        "candidates": [_candidate_to_dict(c) for c in candidates],
        "plan": {"staged": plan.staged, "deferred": plan.deferred,
                 "perBucket": {str(k): v for k, v in plan.per_bucket.items()}},
        "staged": await user_tables.get_staged_sweep(pool, uid, mid or ""),
    }


def _locked_instance_ids(profile: dict) -> set[str]:
    """Instance ids currently locked, read from the item state bitmask."""
    locked = set()
    buckets = [profile.get("profileInventory", {}).get("data", {})]
    buckets += list(profile.get("characterInventories", {}).get("data", {}).values())
    buckets += list(profile.get("characterEquipment", {}).get("data", {}).values())
    for entry in buckets:
        for item in entry.get("items", []):
            instance_id = item.get("itemInstanceId")
            if instance_id and item.get("state", 0) & _LOCKED_STATE:
                locked.add(instance_id)
    return locked


@app.post("/api/dismantle/sweep")
async def dismantle_sweep(
    request: Request,
    body: DismantleSweepBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Stage a batch: move each approved weapon to the character, then unlock it.

    Transfer precedes unlock so an interrupted sweep leaves weapons locked on a
    character rather than unlocked in the vault. The pre-sweep lock state for
    each item is persisted right after its transfer succeeds but before its
    unlock call — not batched up and flushed after the whole loop — because no
    except clause catches a process kill or client disconnect: writing early
    means a kill before the record leaves the item transferred-but-still-locked
    (inert, no undo record needed), while a kill during or after unlock still
    leaves a correct record behind.
    """
    settings = get_settings()
    uid = current_user["user_id"]
    throttle = request.app.state.throttle
    staged: list[str] = []
    failed: list[dict] = []

    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(
            pool, uid, settings, client, settings.token_enc_key
        )
        cached_mid = await cache.get(pool, uid, "profile_membership_id")
        if cached_mid != mid:
            raise HTTPException(status_code=400, detail="Your cached inventory is for a "
                                "different account — open Weapons and Refresh, then retry.")
        # Re-fetch rather than trust the cache (up to user_cache_ttl_seconds
        # stale): both the locked blocklist and the was_locked recorded for undo
        # are read off this profile, so a lock the user set in-game minutes ago
        # must be visible here or the weapon is both swept and unrestorable.
        # One extra Bungie call on a rare, irreversible operation.
        profile = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
        await _save_profile(pool, uid, profile, mid)

        candidates = await _sweep_candidates(pool, uid, profile)
        allowed, rejected = dismantle_logic.enforce_blocklist(
            candidates, body.instanceIds, body.overrides
        )
        occupancy = dismantle_logic.bucket_occupancy(profile, body.characterId)
        plan = dismantle_logic.plan_batch(candidates, allowed, occupancy)

        by_id = {c.instance_id: c for c in candidates}
        locked_now = _locked_instance_ids(profile)
        for instance_id in plan.staged:
            candidate = by_id[instance_id]
            try:
                await _move_one(client, settings, access, mtype, profile, instance_id,
                                candidate.item_hash, body.characterId, False, throttle)
                # Written now — after transfer succeeds, before unlock — so a
                # network error on the unlock call below can never lose the
                # undo record for an item that ends up unlocked. The write is
                # insert-only, so re-staging an already-staged instance (a
                # retry, a second tab) cannot overwrite the true original lock
                # state with the False it now reads.
                await user_tables.stage_sweep_items(
                    pool, uid, mid, [(instance_id, instance_id in locked_now)]
                )
                await throttle.run(lambda iid=instance_id: set_item_lock_state(
                    # iid=instance_id binds the loop variable's *current* value at
                    # lambda-creation time. Without it every deferred closure would
                    # share the loop's final instance_id by the time throttle.run
                    # actually invokes it, unlocking the wrong item.
                    mtype, iid, body.characterId, False, access, settings, client
                ))
            except (BungieApiError, httpx.RequestError, httpx.HTTPStatusError) as exc:
                failed.append({"instanceId": instance_id, "error": str(exc)})
                continue
            staged.append(instance_id)
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))

    await _save_profile(pool, uid, fresh, mid)
    return {"staged": staged, "deferred": plan.deferred,
            "rejected": rejected, "failed": failed}


def _instance_item_hashes(profile: dict) -> dict[str, int]:
    """Map instance id -> item hash across every inventory bucket."""
    out: dict[str, int] = {}
    buckets = [profile.get("profileInventory", {}).get("data", {})]
    buckets += list(profile.get("characterInventories", {}).get("data", {}).values())
    buckets += list(profile.get("characterEquipment", {}).get("data", {}).values())
    for entry in buckets:
        for item in entry.get("items", []):
            instance_id = item.get("itemInstanceId")
            if instance_id:
                out[instance_id] = item.get("itemHash", 0)
    return out


def _profile_has_inventory_data(profile: dict) -> bool:
    """True when the profile demonstrably carries its inventory components.

    Bungie answers HTTP 200 with ErrorCode 1 but the component's `data` key
    ABSENT when a component is unavailable (reduced OAuth scope, privacy
    settings, partial outage), and that reply is cached like any other. Walking
    such a profile yields nothing, which is indistinguishable from "the item is
    gone" unless the envelopes themselves are checked. A reply carrying no
    character inventories at all counts as degraded too: every account has at
    least one character, so an empty map is Bungie withholding, not an empty
    inventory."""
    if not all(
        "data" in profile.get(key, {})
        for key in ("profileInventory", "characterInventories", "characterEquipment")
    ):
        return False
    return bool(profile["characterInventories"]["data"])


def _lock_character_id(profile: dict, instance_id: str, fallback: str) -> str:
    """Character id to send with the re-lock call. Nothing records which
    character a sweep staged an item to, and the item may currently sit on a
    different character than whichever one is selected in the undo request —
    so prefer the character that actually owns the item right now (resolved
    the same way _move_one finds its transfer source), falling back to the
    request's characterId only when the item isn't tied to a specific
    character (already in the vault, or not found)."""
    location = _find_item_location(profile, instance_id)
    if location is None or location == "vault":
        return fallback
    if location.startswith("equipped:"):
        return location.split(":", 1)[1]
    return location


@app.post("/api/dismantle/undo")
async def dismantle_undo(
    request: Request,
    body: DismantleUndoBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    """Reverse a staged sweep: restore each item's prior lock state, then send
    it back to the vault. Re-locking first mirrors the sweep's safety ordering:
    an interrupted undo must leave a weapon locked on a character rather than
    unlocked and sitting in the vault where it can be dismantled by accident.

    An item whose unlock failed during the sweep was left transferred but
    still locked — re-locking it here is a harmless no-op, not an error. An
    instance missing from the profile entirely was already dismantled
    in-game, which is the feature working as intended, so it counts as
    restored rather than failed.
    """
    settings = get_settings()
    uid = current_user["user_id"]
    throttle = request.app.state.throttle
    restored: list[str] = []
    failed: list[dict] = []

    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(
            pool, uid, settings, client, settings.token_enc_key
        )
        # Staged sweeps are scoped per Destiny membership: an account switch
        # must never let undo see (and wipe) another membership's records.
        staged = await user_tables.get_staged_sweep(pool, uid, mid)
        if not staged:
            return {"restored": [], "failed": []}

        profile = await _load_profile_or_400(pool, uid)
        cached_mid = await cache.get(pool, uid, "profile_membership_id")
        if cached_mid != mid:
            raise HTTPException(status_code=400, detail="Your cached inventory is for a "
                                "different account — open Weapons and Refresh, then retry.")
        # "Absent from the profile" only means "already dismantled in-game" if
        # the profile actually carries inventory. Without this an inventory-less
        # reply would classify every staged item as restored and delete every
        # row — and a row is the only record of a weapon's pre-sweep lock state.
        if not _profile_has_inventory_data(profile):
            raise HTTPException(status_code=400, detail="Inventory data unavailable — open "
                                "Weapons and Refresh, then try Undo again.")
        item_hashes = _instance_item_hashes(profile)
        for instance_id, was_locked in staged.items():
            item_hash = item_hashes.get(instance_id)
            if item_hash is None:
                # Already dismantled in-game — nothing to restore.
                restored.append(instance_id)
                continue
            try:
                if was_locked:
                    lock_char = _lock_character_id(profile, instance_id, body.characterId)
                    await throttle.run(lambda iid=instance_id, cid=lock_char: set_item_lock_state(
                        mtype, iid, cid, True, access, settings, client
                    ))
                await _move_one(client, settings, access, mtype, profile, instance_id,
                                item_hash, "vault", False, throttle)
            except (BungieApiError, httpx.RequestError, httpx.HTTPStatusError) as exc:
                failed.append({"instanceId": instance_id, "error": str(exc)})
                continue
            restored.append(instance_id)
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))

    await user_tables.clear_sweep_items(pool, uid, mid, restored)
    await _save_profile(pool, uid, fresh, mid)
    return {"restored": restored, "failed": failed}


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
async def list_memberships(
    request: Request,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    tok = await tokens.get_tokens(pool, uid, settings.token_enc_key)
    active = {"type": tok["membership_type"], "id": tok["membership_id"]} if tok else None
    async with httpx.AsyncClient(
        timeout=30.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, _mt, _mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        memberships = await request.app.state.throttle.run(
            lambda: get_memberships(access, settings, client)
        )
    out = [
        {"type": m["membershipType"], "id": m["membershipId"], "displayName": m.get("displayName", "")}
        for m in memberships["destinyMemberships"]
    ]
    return {"memberships": out, "active": active}


@app.post("/api/memberships/select")
async def select_membership(
    body: MembershipSelectBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    await tokens.update_membership(pool, uid, body.membershipType, body.membershipId)
    for key in _ACCOUNT_CACHE_KEYS:
        await cache.delete(pool, uid, key)
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


async def _move_one(client, settings, access, mtype, profile, instance_id, item_hash, target, equip, throttle=None):
    """Move one item to `target` ('vault' or a character id), optionally equip.
    Raises BungieApiError on a problem (e.g. equipped on another character).
    When throttle is provided, all Bungie calls are routed through it."""
    _run = throttle.run if throttle is not None else (lambda f: f())

    source = _find_item_location(profile, instance_id)
    if source is None:
        raise BungieApiError("Item not found in your cached inventory.")
    if source.startswith("equipped:"):
        if source.split(":", 1)[1] == target:
            return  # already equipped on the target — nothing to do
        raise BungieApiError("Item is equipped on another character — unequip it first.")
    if target == "vault":
        if source != "vault":
            await _run(lambda: transfer_item(mtype, item_hash, instance_id, source, True, access, settings, client))
        return
    if source != target:
        if source != "vault":
            await _run(lambda: transfer_item(mtype, item_hash, instance_id, source, True, access, settings, client))
        await _run(lambda: transfer_item(mtype, item_hash, instance_id, target, False, access, settings, client))
    if equip:
        await _run(lambda: equip_item(mtype, instance_id, target, access, settings, client))


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
async def transfer(
    request: Request,
    body: TransferBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    throttle = request.app.state.throttle
    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        cached_mid = await cache.get(pool, uid, "profile_membership_id")
        if cached_mid != mid:
            raise HTTPException(status_code=400, detail="Your cached inventory is for a different "
                                "account — open Weapons and Refresh, then try the move again.")
        try:
            await _move_one(client, settings, access, mtype, profile, body.instanceId,
                            body.itemHash, body.targetCharacterId, body.equip, throttle)
        except BungieApiError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=400, detail=f"Bungie rejected the move (HTTP "
                                f"{exc.response.status_code}). If you haven't re-logged-in since "
                                "adding the move permission, click Re-login and try again.")
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
    await _save_profile(pool, uid, fresh, mid)
    return {"ok": True}


@app.post("/api/transfer/bulk")
async def transfer_bulk(
    request: Request,
    body: BulkTransferBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    profile = await _load_profile_or_400(pool, uid)
    throttle = request.app.state.throttle
    results = []
    async with httpx.AsyncClient(
        timeout=180.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        cached_mid = await cache.get(pool, uid, "profile_membership_id")
        if cached_mid != mid:
            raise HTTPException(status_code=400, detail="Cached inventory is for a different "
                                "account — Refresh first.")
        for it in body.items:
            try:
                await _move_one(client, settings, access, mtype, profile, it["instanceId"],
                                it["itemHash"], body.targetCharacterId, body.equip, throttle)
                results.append({"instanceId": it["instanceId"], "ok": True})
            except (BungieApiError, httpx.HTTPStatusError) as exc:
                results.append({"instanceId": it["instanceId"], "ok": False, "error": str(exc)})
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
    await _save_profile(pool, uid, fresh, mid)
    return {"results": results}


_POSTMASTER_BUCKET = 215593132


@app.get("/api/postmaster")
async def get_postmaster(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    profile_raw = await cache.get(pool, uid, "profile_cache")
    manifest = await load_cached_manifest(pool)
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
async def pull_postmaster(
    request: Request,
    body: PullPostmasterBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    throttle = request.app.state.throttle
    async with httpx.AsyncClient(
        timeout=60.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        try:
            await throttle.run(lambda: pull_from_postmaster(mtype, body.itemHash, body.instanceId,
                                                             body.characterId, body.stackSize,
                                                             access, settings, client))
        except (BungieApiError, httpx.HTTPStatusError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
    await _save_profile(pool, uid, fresh, mid)
    return {"ok": True}


@app.get("/api/loadouts")
async def get_loadouts(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    return {"loadouts": await user_tables.get_loadouts(pool, uid)}


@app.put("/api/loadouts")
async def put_loadout(
    body: LoadoutBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    uid = current_user["user_id"]
    await user_tables.save_loadout(pool, uid, body.name, {"characterId": body.characterId, "items": body.items})
    return {"ok": True}


@app.delete("/api/loadouts/{name}")
async def delete_loadout(
    name: str,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    uid = current_user["user_id"]
    await user_tables.delete_loadout(pool, uid, name)
    return {"ok": True}


@app.get("/api/armor-sets")
async def get_armor_sets(
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
) -> dict:
    uid = current_user["user_id"]
    return {"armorSets": await user_tables.get_armor_sets(pool, uid)}


@app.put("/api/armor-sets")
async def put_armor_set(
    body: ArmorSetBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    uid = current_user["user_id"]
    await user_tables.save_armor_set(pool, uid, body.name, {
        "className": body.className,
        "characterId": body.characterId,
        "tier": body.tier,
        "items": body.items,
    })
    return {"ok": True}


@app.delete("/api/armor-sets/{name}")
async def delete_armor_set(
    name: str,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    uid = current_user["user_id"]
    await user_tables.delete_armor_set(pool, uid, name)
    return {"ok": True}


async def _apply_item_set(pool, uid: int, settings, request: Request, items: list[dict], target: str) -> list[dict]:
    """Move+equip each {instanceId, itemHash} item to the target character.
    Returns per-item results. Shared by loadout-apply and armor-set-apply."""
    profile = await _load_profile_or_400(pool, uid)
    results = []
    throttle = request.app.state.throttle
    async with httpx.AsyncClient(
        timeout=180.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        access, mtype, mid = await valid_access_token(pool, uid, settings, client, settings.token_enc_key)
        for it in items:
            try:
                await _move_one(client, settings, access, mtype, profile, it["instanceId"],
                                it["itemHash"], target, True, throttle=throttle)
                results.append({"instanceId": it["instanceId"], "ok": True})
            # RequestError is a SIBLING of HTTPStatusError, not a subclass — a
            # network blip used to escape as a 500, discarding the per-item
            # results for everything after it.
            except (BungieApiError, httpx.HTTPStatusError, httpx.RequestError) as exc:
                results.append({"instanceId": it["instanceId"], "ok": False, "error": str(exc)})
        fresh = await throttle.run(lambda: get_profile(mtype, mid, access, settings, client))
    await _save_profile(pool, uid, fresh, mid)
    return results


@app.post("/api/armor-sets/apply")
async def apply_armor_set(
    request: Request,
    body: ApplyLoadoutBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    sets = await user_tables.get_armor_sets(pool, uid)
    armor_set = next((s for s in sets if s["name"] == body.name), None)
    if armor_set is None:
        raise HTTPException(status_code=404, detail="Armor set not found.")
    results = await _apply_item_set(pool, uid, settings, request, armor_set["items"], armor_set["characterId"])
    return {"results": results}


@app.post("/api/loadouts/apply")
async def apply_loadout(
    request: Request,
    body: ApplyLoadoutBody,
    current_user: dict = Depends(get_current_user),
    pool=Depends(get_pool),
    _csrf=Depends(require_csrf),
) -> dict:
    settings = get_settings()
    uid = current_user["user_id"]
    loadouts = await user_tables.get_loadouts(pool, uid)
    loadout = next((lo for lo in loadouts if lo["name"] == body.name), None)
    if loadout is None:
        raise HTTPException(status_code=404, detail="Loadout not found.")
    results = await _apply_item_set(pool, uid, settings, request, loadout["items"], loadout["characterId"])
    return {"results": results}


# Serve the built frontend (production single-server mode). Declared after all
# /api and /callback routes so those take priority; "/" falls through to the SPA.
_FRONTEND_DIST = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if os.path.isdir(_FRONTEND_DIST):
    # routes.tsx declares "/app/*", a wildcard the SSG build cannot prerender, so
    # no /app/index.html exists on disk. StaticFiles has no SPA fallback, so without
    # these routes /app 404s — and /app is the landing page's primary CTA and where
    # login lands. Declared before the mount so they take priority over it.
    @app.get("/app")
    @app.get("/app/{spa_path:path}")
    async def spa_shell(spa_path: str = "") -> FileResponse:
        """Serve the SPA shell so the client router can handle /app routes."""
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))

    # The SSG build emits flat prerendered pages (dist/weapons/<slug>.html).
    # StaticFiles will not append ".html" the way the nginx design's
    # `try_files $uri $uri.html` did, so these 404 — while sitemap.xml
    # advertises them to search engines.
    @app.get("/weapons/{slug}")
    async def prerendered_weapon(slug: str) -> FileResponse:
        """Serve a flat prerendered weapon page by slug."""
        weapons_dir = os.path.join(_FRONTEND_DIST, "weapons")
        candidate = os.path.normpath(os.path.join(weapons_dir, f"{slug}.html"))
        # Guard against traversal: the resolved path must stay inside weapons/.
        if not candidate.startswith(weapons_dir + os.sep) or not os.path.isfile(candidate):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(candidate)

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
