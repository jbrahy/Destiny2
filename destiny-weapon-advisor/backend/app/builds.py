import json
from pathlib import Path

_BUILDS_SEED = Path(__file__).parent / "data" / "builds_seed.json"
_ACTIVITIES_SEED = Path(__file__).parent / "data" / "activities_seed.json"


def _seed_builds() -> dict:
    data = json.loads(_BUILDS_SEED.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _seed_activities() -> list:
    return json.loads(_ACTIVITIES_SEED.read_text()).get("activities", [])
