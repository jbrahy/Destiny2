import httpx

from app.config import Settings
from app.manifest import Manifest
from app.models import ArmorPiece, OwnedWeapon


class BungieApiError(Exception):
    """Raised when the Bungie API returns a non-success ErrorCode."""


def extract_response(payload: dict) -> dict:
    """Return the Response envelope, or raise if Bungie signaled an error."""
    if payload.get("ErrorCode") != 1:
        raise BungieApiError(payload.get("Message") or "Bungie API error")
    return payload["Response"]


def _raise_for_bungie(resp: httpx.Response) -> None:
    """Surface Bungie's error envelope (ErrorStatus/Message) even when the call
    comes back with a non-2xx HTTP status, instead of an opaque HTTP error."""
    try:
        data = resp.json()
    except ValueError:
        resp.raise_for_status()
        return
    if isinstance(data, dict) and "ErrorCode" in data:
        if data.get("ErrorCode") != 1:
            status = data.get("ErrorStatus", "")
            message = data.get("Message") or "Bungie API error"
            raise BungieApiError(f"{message} ({status})" if status else message)
        return
    resp.raise_for_status()

_BASE = "https://www.bungie.net/Platform"
_MASTERWORK_STATE = 4
PROFILE_COMPONENTS = "102,200,201,205,300,302,304,305,310"

DAMAGE_TYPES = {1: "Kinetic", 2: "Arc", 3: "Solar", 4: "Void", 6: "Stasis", 7: "Strand"}
CLASS_TYPES = {0: "Titan", 1: "Hunter", 2: "Warlock"}

# Plug item-types that are NOT weapon perks (excluded from the displayed roll;
# the Intrinsic is shown separately as the frame).
_NON_PERK_TYPES = {
    "", "Intrinsic", "Shader", "Weapon Ornament", "Tracker", "Weapon Mod",
    "Masterwork", "Enhancement", "Memento", "Restore Defaults", "Catalyst",
}


def _headers(settings: Settings, access_token: str | None = None) -> dict:
    headers = {"X-API-Key": settings.bungie_api_key}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def assemble_weapons(profile: dict, manifest: Manifest) -> list[OwnedWeapon]:
    components = profile.get("itemComponents", {})
    instances = components.get("instances", {}).get("data", {})
    sockets = components.get("sockets", {}).get("data", {})
    item_stats = components.get("stats", {}).get("data", {})
    characters = profile.get("characters", {}).get("data", {})
    char_class = {
        cid: CLASS_TYPES.get(c.get("classType"), "Character") for cid, c in characters.items()
    }

    weapons: list[OwnedWeapon] = []
    for item, holder, equipped in _gather_items(profile):
        instance_id = item.get("itemInstanceId")
        item_hash = item.get("itemHash")
        if not instance_id or not manifest.is_weapon(item_hash):
            continue
        socket_list = sockets.get(instance_id, {}).get("sockets", [])
        plug_hashes = [s["plugHash"] for s in socket_list if s.get("plugHash") is not None]
        frame = next(
            (manifest.name(h) for h in plug_hashes if manifest.item_type(h) == "Intrinsic"), ""
        )
        perk_names = [
            manifest.name(h)
            for h in plug_hashes
            if manifest.item_type(h) not in _NON_PERK_TYPES
            and not manifest.name(h).startswith("Unknown (")
        ]
        inst = instances.get(instance_id, {})
        raw_stats = item_stats.get(instance_id, {}).get("stats", {})
        stats = {}
        for stat_hash, entry in raw_stats.items():
            stat_name = manifest.stat_name(int(stat_hash))
            if stat_name:
                stats[stat_name] = entry.get("value", 0)
        location = "Vault" if holder == "Vault" else char_class.get(holder, "Character")
        weapons.append(
            OwnedWeapon(
                instance_id=instance_id,
                item_hash=item_hash,
                name=manifest.name(item_hash),
                weapon_type=manifest.item_type(item_hash),
                element=DAMAGE_TYPES.get(inst.get("damageType", 0), "Unknown"),
                is_masterworked=bool(item.get("state", 0) & _MASTERWORK_STATE),
                is_random_roll=manifest.tier_type(item_hash) == 5,
                perks=frozenset(plug_hashes),
                location=location,
                power=inst.get("primaryStat", {}).get("value", 0),
                ammo_type=manifest.ammo_type(item_hash),
                frame=frame,
                perk_names=perk_names,
                stats=stats,
                icon=manifest.icon(item_hash),
                equipped=equipped,
            )
        )
    return weapons


_CLASS_ITEM_TYPES = {"Hunter Cloak", "Titan Mark", "Warlock Bond"}


def _gather_items(profile: dict) -> list[tuple[dict, str, bool]]:
    """Each (item, holder, equipped). holder is 'Vault' or a character id."""
    raw: list[tuple[dict, str, bool]] = []
    raw += [(it, "Vault", False)
            for it in profile.get("profileInventory", {}).get("data", {}).get("items", [])]
    for cid, bucket in profile.get("characterInventories", {}).get("data", {}).items():
        raw += [(it, cid, False) for it in bucket.get("items", [])]
    for cid, bucket in profile.get("characterEquipment", {}).get("data", {}).items():
        raw += [(it, cid, True) for it in bucket.get("items", [])]
    return raw


def assemble_armor(profile: dict, manifest: Manifest) -> list[ArmorPiece]:
    components = profile.get("itemComponents", {})
    instances = components.get("instances", {}).get("data", {})
    item_stats = components.get("stats", {}).get("data", {})
    characters = profile.get("characters", {}).get("data", {})
    char_class = {
        cid: CLASS_TYPES.get(c.get("classType"), "Character") for cid, c in characters.items()
    }

    pieces: list[ArmorPiece] = []
    for item, holder, equipped in _gather_items(profile):
        instance_id = item.get("itemInstanceId")
        item_hash = item.get("itemHash")
        if not instance_id or not manifest.is_armor(item_hash):
            continue
        slot = manifest.item_type(item_hash)
        if slot in _CLASS_ITEM_TYPES:
            slot = "Class Item"
        inst = instances.get(instance_id, {})
        raw_stats = item_stats.get(instance_id, {}).get("stats", {})
        stats = {}
        for stat_hash, entry in raw_stats.items():
            stat_name = manifest.stat_name(int(stat_hash))
            if stat_name:
                stats[stat_name] = entry.get("value", 0)
        pieces.append(
            ArmorPiece(
                instance_id=instance_id,
                item_hash=item_hash,
                name=manifest.name(item_hash),
                slot=slot,
                class_name=CLASS_TYPES.get(manifest.item_class_type(item_hash), "Any"),
                power=inst.get("primaryStat", {}).get("value", 0),
                is_exotic=manifest.tier_type(item_hash) == 6,
                is_masterworked=bool(item.get("state", 0) & _MASTERWORK_STATE),
                stats=stats,
                location="Vault" if holder == "Vault" else char_class.get(holder, "Character"),
                icon=manifest.icon(item_hash),
                equipped=equipped,
            )
        )
    return pieces


async def transfer_item(
    membership_type: int, item_hash: int, instance_id: str, character_id: str,
    to_vault: bool, access_token: str, settings: Settings, client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        f"{_BASE}/Destiny2/Actions/Items/TransferItem/",
        json={
            "itemReferenceHash": item_hash, "stackSize": 1, "transferToVault": to_vault,
            "itemId": instance_id, "characterId": character_id, "membershipType": membership_type,
        },
        headers=_headers(settings, access_token),
    )
    _raise_for_bungie(resp)


async def equip_item(
    membership_type: int, instance_id: str, character_id: str,
    access_token: str, settings: Settings, client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        f"{_BASE}/Destiny2/Actions/Items/EquipItem/",
        json={"itemId": instance_id, "characterId": character_id, "membershipType": membership_type},
        headers=_headers(settings, access_token),
    )
    _raise_for_bungie(resp)


async def pull_from_postmaster(
    membership_type: int, item_hash: int, instance_id: str, character_id: str,
    stack_size: int, access_token: str, settings: Settings, client: httpx.AsyncClient,
) -> None:
    resp = await client.post(
        f"{_BASE}/Destiny2/Actions/Items/PullFromPostmaster/",
        json={
            "itemReferenceHash": item_hash, "itemId": instance_id, "stackSize": stack_size,
            "characterId": character_id, "membershipType": membership_type,
        },
        headers=_headers(settings, access_token),
    )
    _raise_for_bungie(resp)


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
