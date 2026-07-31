"""Armour set membership and set bonuses.

NOTE: distinct from the "/api/armor-sets" endpoints, which are user-saved
armour loadouts. This module is about Destiny's own armour sets and their
2-piece / 4-piece bonuses.

Sets live in DestinyEquipableItemSetDefinition: each names its member item
hashes and its 2-piece / 4-piece bonuses, which point at sandbox perks for the
actual rules text. The app never downloaded either table, so it could not show
which set a piece belonged to or what wearing several of them does.

Pure: stdlib + app.manifest only. No I/O.
"""


def build_index(manifest) -> dict[int, int]:
    """item hash -> set hash, built once per manifest load.

    Returns {} for a manifest cached before the set tables existed, so callers
    degrade to "no sets" rather than crashing.
    """
    index: dict[int, int] = {}
    for set_hash in manifest.item_sets:
        for item_hash in manifest.set_items(set_hash):
            index[item_hash] = set_hash
    return index


def set_for(item_hash: int, index: dict[int, int], manifest) -> tuple[str, int] | None:
    """(set name, set hash) for an item, or None when it belongs to no set."""
    set_hash = index.get(item_hash)
    if set_hash is None:
        return None
    name = manifest.item_sets.get(set_hash, {}).get("displayProperties", {}).get("name", "")
    return name, set_hash


def set_bonuses(set_hash: int, manifest) -> list[dict]:
    """[{count, name, description}] for a set, ordered 2-piece before 4-piece.

    An unresolvable perk still reports its count: knowing a 4-piece bonus
    exists is useful even when its text is missing.
    """
    bonuses = []
    for perk in manifest.set_perks(set_hash):
        name, description = manifest.perk_text(perk.get("sandboxPerkHash"))
        bonuses.append({
            "count": perk.get("requiredSetCount", 0),
            "name": name,
            "description": description,
        })
    bonuses.sort(key=lambda b: b["count"])
    return bonuses


def equipped_set_counts(set_hashes: list[int | None]) -> dict[int, int]:
    """How many pieces of each set are present, so the UI can say '3/4'."""
    counts: dict[int, int] = {}
    for set_hash in set_hashes:
        if set_hash is not None:
            counts[set_hash] = counts.get(set_hash, 0) + 1
    return counts
