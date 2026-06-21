import httpx

from app.config import Settings
from app.manifest import Manifest
from app.models import OwnedWeapon


class BungieApiError(Exception):
    """Raised when the Bungie API returns a non-success ErrorCode."""


def extract_response(payload: dict) -> dict:
    """Return the Response envelope, or raise if Bungie signaled an error."""
    if payload.get("ErrorCode") != 1:
        raise BungieApiError(payload.get("Message") or "Bungie API error")
    return payload["Response"]

_BASE = "https://www.bungie.net/Platform"
_MASTERWORK_STATE = 4
PROFILE_COMPONENTS = "102,201,205,300,302,305,310"

DAMAGE_TYPES = {1: "Kinetic", 2: "Arc", 3: "Solar", 4: "Void", 6: "Stasis", 7: "Strand"}


def _headers(settings: Settings, access_token: str | None = None) -> dict:
    headers = {"X-API-Key": settings.bungie_api_key}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def assemble_weapons(profile: dict, manifest: Manifest) -> list[OwnedWeapon]:
    instances = profile.get("itemComponents", {}).get("instances", {}).get("data", {})
    sockets = profile.get("itemComponents", {}).get("sockets", {}).get("data", {})

    raw: list[tuple[dict, str]] = []
    pi = profile.get("profileInventory", {}).get("data", {}).get("items", [])
    raw += [(item, "Vault") for item in pi]
    for char_id, bucket in profile.get("characterInventories", {}).get("data", {}).items():
        raw += [(item, char_id) for item in bucket.get("items", [])]
    for char_id, bucket in profile.get("characterEquipment", {}).get("data", {}).items():
        raw += [(item, char_id) for item in bucket.get("items", [])]

    weapons: list[OwnedWeapon] = []
    for item, location in raw:
        instance_id = item.get("itemInstanceId")
        item_hash = item.get("itemHash")
        if not instance_id or not manifest.is_weapon(item_hash):
            continue
        socket_list = sockets.get(instance_id, {}).get("sockets", [])
        perks = frozenset(
            s["plugHash"] for s in socket_list if s.get("plugHash") is not None
        )
        damage = instances.get(instance_id, {}).get("damageType", 0)
        weapons.append(
            OwnedWeapon(
                instance_id=instance_id,
                item_hash=item_hash,
                name=manifest.name(item_hash),
                weapon_type=manifest.item_type(item_hash),
                element=DAMAGE_TYPES.get(damage, "Unknown"),
                is_masterworked=bool(item.get("state", 0) & _MASTERWORK_STATE),
                is_random_roll=manifest.tier_type(item_hash) == 5,
                perks=perks,
                location=location,
            )
        )
    return weapons


async def get_memberships(access_token: str, settings: Settings, client: httpx.AsyncClient) -> dict:
    resp = await client.get(
        f"{_BASE}/User/GetMembershipsForCurrentUser/",
        headers=_headers(settings, access_token),
    )
    resp.raise_for_status()
    return extract_response(resp.json())


async def get_profile(
    membership_type: int,
    membership_id: str,
    access_token: str,
    settings: Settings,
    client: httpx.AsyncClient,
) -> dict:
    resp = await client.get(
        f"{_BASE}/Destiny2/{membership_type}/Profile/{membership_id}/",
        params={"components": PROFILE_COMPONENTS},
        headers=_headers(settings, access_token),
    )
    resp.raise_for_status()
    return extract_response(resp.json())
