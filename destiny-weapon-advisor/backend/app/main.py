import json
import secrets
import time

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from app.bungie_client import assemble_weapons, get_memberships, get_profile
from app.bungie_oauth import build_authorize_url, exchange_code, refresh_tokens
from app.config import get_settings
from app.manifest import Manifest, load_manifest
from app.scoring import score_inventory
from app.storage import get_conn, kv_get, kv_set
from app.wishlist import fetch_wishlist

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
        wishlist = await fetch_wishlist(settings.wishlist_url, client)
        profile = await get_profile(mtype, mid, access, settings, client)
    owned = assemble_weapons(profile, manifest)
    recs = score_inventory(owned, wishlist)
    result = {
        "weapons": [recommendation_to_dict(r, manifest) for r in recs],
        "cachedAt": time.time(),
    }
    kv_set(conn, "weapons_cache", json.dumps(result))
    return result


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
