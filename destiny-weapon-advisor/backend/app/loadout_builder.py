from app.recommend import element_for_subclass, recommend_weapons

_SLOTS = ("Primary", "Special", "Heavy")


def build_loadout(
    weapons: list[dict], activity: dict, build: dict | None, top_n: int = 5
) -> dict:
    """Compose a full loadout suggestion for an activity: top owned weapon per
    ammo slot (via recommend_weapons) plus the seeded subclass build and simple
    element-coverage signals. Pure — no DB/network."""
    element = element_for_subclass(activity.get("recommendedSubclass", ""))
    ranked = recommend_weapons(
        weapons,
        {"label": activity.get("name", ""), "element": element},
        top_n=top_n,
    )
    chosen = {slot: (ranked["slots"][slot][0] if ranked["slots"][slot] else None) for slot in _SLOTS}

    elements = sorted({c["element"] for c in chosen.values() if c and c.get("element")})
    return {
        "activity": activity.get("name", ""),
        "subclass": {
            "class": activity.get("recommendedClass", ""),
            "subclass": activity.get("recommendedSubclass", ""),
            "build": build,
        },
        "weapons": chosen,
        "elementCoverage": {
            "elements": elements,
            "activityElement": element,
            "matchesActivity": bool(element) and element in elements,
        },
        "guidance": activity.get("weapons", ""),
    }
