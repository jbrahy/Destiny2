from app.models import Verdict

_VERDICT_TIER = {
    Verdict.GOD_ROLL.value: 5,
    Verdict.MASTERWORK.value: 4,
    Verdict.GOOD.value: 3,
    Verdict.NO_DATA.value: 1,
    Verdict.DISMANTLE.value: 0,
}

_VERDICT_REASON = {
    Verdict.GOD_ROLL.value: "God roll",
    Verdict.MASTERWORK.value: "Strong roll",
    Verdict.GOOD.value: "Good roll",
    Verdict.NO_DATA.value: "Usable",
}

_SUBCLASS_ELEMENT = {
    "Solar": "Solar", "Arc": "Arc", "Void": "Void",
    "Stasis": "Stasis", "Strand": "Strand",
}

_SLOTS = ("Primary", "Special", "Heavy")


def element_for_subclass(subclass: str) -> str | None:
    """Map a subclass name to its damage element, or None for Prismatic/Any/unknown."""
    return _SUBCLASS_ELEMENT.get(subclass)


def recommend_weapons(weapons: list[dict], context: dict, top_n: int = 5) -> dict:
    """Rank owned weapons per ammo slot for a context.

    context: {"label": str, "element": str | None}. element is set only for
    activity contexts that resolve to a damage element; it grants a synergy bonus.
    """
    element = context.get("element")
    slots: dict[str, list[dict]] = {s: [] for s in _SLOTS}
    for w in weapons:
        base = _VERDICT_TIER.get(w.get("verdict"), 0)
        if base <= 0:  # DISMANTLE or unrecognized verdict — excluded
            continue
        ammo = w.get("ammoType")
        if ammo not in slots:
            continue
        matched = bool(element) and w.get("element") == element
        effective = base + (1 if matched else 0)
        reasons = [_VERDICT_REASON.get(w.get("verdict"), "")]
        if matched:
            reasons.append(f"element-matched for {element}")
        entry = dict(w)
        entry["recommendReason"] = " • ".join(r for r in reasons if r)
        entry["_rank"] = (
            -effective,
            -len(w.get("matchedPerks", [])),
            0 if w.get("isMasterworked") else 1,
            -int(w.get("power", 0)),
            w.get("name", ""),
        )
        slots[ammo].append(entry)
    for slot, entries in slots.items():
        entries.sort(key=lambda e: e["_rank"])
        slots[slot] = entries[:top_n]
        for e in slots[slot]:
            del e["_rank"]
    return {"context": context.get("label", ""), "slots": slots}
