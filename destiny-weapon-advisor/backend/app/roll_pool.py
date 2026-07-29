"""A weapon's trait roll pool, resolved from the manifest.

What a weapon CAN roll, per trait column. The profile's `reusablePlugs`
component does NOT contain this — it holds only plugs insertable right now for
free (barrels, magazines, mods, origin traits), which is why crafted trait
alternatives are absent from it. The traits live in the manifest's socket
entries, behind `randomizedPlugSetHash` / `reusablePlugSetHash`.

Pure: stdlib + app.manifest only. No I/O.

THE RULE EVERYTHING ELSE DEPENDS ON: perks within one column are mutually
exclusive. Consumers must take one perk per column, never a union — two A-tier
perks in the same column would otherwise satisfy `strong >= 2` and promote a
weapon to a god roll the player can never actually hold.
"""


def trait_columns(item_hash: int, manifest, only_current: bool = False) -> list[list[str]]:
    """Trait perk names per trait column, in socket order.

    Each inner list is one mutually-exclusive choice group. Non-trait sockets
    (barrel, magazine, guard, blade, origin trait, mod, intrinsic) are excluded
    entirely — they don't decide a weapon's quality, and an origin-trait column
    would hand every weapon a free extra strong perk.

    `only_current` drops perks that can no longer drop, so a chase list never
    sends someone farming something that has left the loot pool.

    Returns [] when the manifest predates the plug-set download, so callers
    degrade to active-perk behaviour instead of crashing.
    """
    columns: list[list[str]] = []
    for entry in manifest.socket_entries(item_hash):
        hashes = _socket_plug_hashes(entry, manifest, only_current)
        names: list[str] = []
        seen: set[str] = set()
        for plug_hash in hashes:
            if not manifest.is_trait(plug_hash):
                continue
            # Base and enhanced variants share a display name; one entry each.
            name = manifest.name(plug_hash)
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
        if names:
            columns.append(names)
    return columns


def _socket_plug_hashes(entry: dict, manifest, only_current: bool) -> list[int]:
    """Candidate plugs for one socket.

    `randomizedPlugSetHash` is the real roll pool and wins when both are present;
    `reusablePlugSetHash` is the fixed selectable set; inline `reusablePlugItems`
    is the last resort for sockets that enumerate their options directly.
    """
    for key in ("randomizedPlugSetHash", "reusablePlugSetHash"):
        set_hash = entry.get(key)
        if set_hash is not None:
            hashes = manifest.plug_set_hashes(set_hash, only_current=only_current)
            if hashes:
                return hashes
    return [
        p["plugItemHash"] for p in entry.get("reusablePlugItems", [])
        if p.get("plugItemHash") is not None
    ]
