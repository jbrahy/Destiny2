import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import db
from app.bungie_client import get_memberships, get_profile
from app.bungie_oauth import build_authorize_url, exchange_code
from app.config import get_settings
from app.deps import get_pool
from app.repositories import perk_ratings as perk_ratings_repo
from app.repositories import sessions, tokens, users

router = APIRouter()


def require_csrf(request: Request) -> None:
    """FastAPI dependency: enforce CSRF double-submit cookie check.

    Reads X-CSRF-Token header and csrftoken cookie; raises 403 if either is
    absent or they do not match.  No server-side state required.
    """
    header_token = request.headers.get("X-CSRF-Token")
    cookie_token = request.cookies.get("csrftoken")
    if not header_token or not cookie_token or header_token != cookie_token:
        raise HTTPException(status_code=403, detail="CSRF check failed")


async def _pick_membership(memberships: dict, access: str, settings, client) -> dict:
    """Choose which Destiny account to use: the cross-save primary if set,
    otherwise the account whose most-recently-played character is the newest."""
    destiny_memberships = memberships["destinyMemberships"]
    if not destiny_memberships:
        raise HTTPException(status_code=400, detail="No Destiny memberships found for this Bungie account.")
    primary_id = memberships.get("primaryMembershipId")
    primary = next((m for m in destiny_memberships if m.get("membershipId") == primary_id), None)
    if primary is not None:
        return primary
    best, best_date, validated = destiny_memberships[0], "", False
    for m in destiny_memberships:
        try:
            prof = await get_profile(m["membershipType"], m["membershipId"], access, settings, client)
        except Exception:
            continue
        dates = [
            c.get("dateLastPlayed", "")
            for c in prof.get("characters", {}).get("data", {}).values()
        ]
        latest = max(dates) if dates else ""
        if not validated or latest > best_date:
            best, best_date, validated = m, latest, True
    return best


@router.get("/api/login")
async def login(pool=Depends(get_pool)) -> RedirectResponse:
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    await db.execute(
        pool,
        "INSERT INTO oauth_states (state, expires_at) VALUES (%s, NOW() + INTERVAL 10 MINUTE)",
        (state,),
    )
    url = build_authorize_url(settings.bungie_client_id, settings.redirect_uri, state)
    return RedirectResponse(url, status_code=307)


@router.get("/callback")
async def callback(code: str, state: str, pool=Depends(get_pool)) -> RedirectResponse:
    # Validate state exists and is not expired
    row = await db.fetchone(
        pool,
        "SELECT state FROM oauth_states WHERE state=%s AND expires_at > NOW()",
        (state,),
    )
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")
    # Delete the state (one-time use)
    await db.execute(pool, "DELETE FROM oauth_states WHERE state=%s", (state,))

    settings = get_settings()
    async with httpx.AsyncClient(
        timeout=30.0, headers={"X-API-Key": settings.bungie_api_key}
    ) as client:
        tokens_resp = await exchange_code(code, settings, client)
        access = tokens_resp["access_token"]
        memberships = await get_memberships(access, settings, client)
        primary = await _pick_membership(memberships, access, settings, client)

    # Upsert user — use the stable Bungie.net account id (bungieNetUser.membershipId)
    # as the primary key, not the Destiny platform membershipId which can change.
    bungie_net_id = memberships["bungieNetUser"]["membershipId"]
    display_name = primary.get("displayName", "")
    existing = await users.get_by_bungie_id(pool, bungie_net_id)
    user_id = await users.upsert(
        pool, bungie_net_id, display_name,
        primary["membershipType"], primary["membershipId"],
    )
    if existing is None:
        await perk_ratings_repo.seed_defaults(pool, user_id)

    # Store encrypted tokens
    expires_in = tokens_resp.get("expires_in", 3600)
    await tokens.set_tokens(
        pool, user_id,
        access, tokens_resp["refresh_token"],
        time.time() + expires_in,
        time.time() + 7776000,  # ~90 days
        primary["membershipType"], primary["membershipId"],
        settings.token_enc_key,
    )

    # Create session
    raw = await sessions.create(pool, user_id, settings.session_ttl_days)

    # Generate CSRF token for double-submit cookie pattern
    csrf = secrets.token_urlsafe(32)

    # Build redirect response with session + CSRF cookies
    response = RedirectResponse(settings.frontend_url, status_code=307)
    response.set_cookie(
        key="sid",
        value=raw,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_ttl_days * 86400,
    )
    response.set_cookie(
        key="csrftoken",
        value=csrf,
        httponly=False,   # JS must read this to send it as a header
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
        max_age=settings.session_ttl_days * 86400,
    )
    return response


@router.post("/api/auth/logout")
async def logout(request: Request, pool=Depends(get_pool)) -> dict:
    sid = request.cookies.get("sid")
    if sid:
        await sessions.delete(pool, sid)
    response = JSONResponse({"ok": True})
    response.delete_cookie(key="sid", path="/")
    response.delete_cookie(key="csrftoken", path="/")
    return response


@router.get("/api/status")
async def status(request: Request, pool=Depends(get_pool)) -> dict:
    sid = request.cookies.get("sid")
    if not sid:
        return {"authenticated": False}
    uid = await sessions.lookup(pool, sid)
    return {"authenticated": uid is not None}


async def get_current_user(request: Request, pool=Depends(get_pool)) -> dict:
    """Dependency: return the current user dict, or raise 401."""
    sid = request.cookies.get("sid")
    if not sid:
        raise HTTPException(status_code=401, detail="Not authenticated")
    uid = await sessions.lookup(pool, sid)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await users.get(pool, uid)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user
