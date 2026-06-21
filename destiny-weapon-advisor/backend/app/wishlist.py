import re

import httpx

from app.models import Wishlist, WishlistRoll

_LINE = re.compile(r"^dimwishlist:item=(-?\d+)&perks=([\d,]*)(.*)$")
_TAG_WORDS = ("pve", "pvp", "gambit")


def _tags_from_text(text: str) -> frozenset[str]:
    low = text.lower()
    return frozenset(t for t in _TAG_WORDS if t in low)


def parse_wishlist(text: str) -> Wishlist:
    wl = Wishlist()
    for raw in text.splitlines():
        line = raw.strip()
        m = _LINE.match(line)
        if not m:
            continue
        item_raw = int(m.group(1))
        perks = frozenset(int(p) for p in m.group(2).split(",") if p)
        remainder = m.group(3) or ""
        notes = ""
        if "#notes:" in remainder:
            notes = remainder.split("#notes:", 1)[1]
            if "|tags:" in notes:
                notes = notes.split("|tags:", 1)[0]
        notes = notes.strip()
        is_trash = item_raw < 0
        item_hash = abs(item_raw)
        roll = WishlistRoll(
            item_hash=item_hash,
            perks=perks,
            notes=notes,
            is_trash=is_trash,
            tags=_tags_from_text(remainder),
        )
        target = wl.trash_by_item if is_trash else wl.rolls_by_item
        target.setdefault(item_hash, []).append(roll)
    return wl


async def fetch_wishlist(url: str, client: httpx.AsyncClient) -> Wishlist:
    resp = await client.get(url, timeout=60.0)
    resp.raise_for_status()
    return parse_wishlist(resp.text)
