import json
import sqlite3
from pathlib import Path

_BUILDS_SEED = Path(__file__).parent / "data" / "builds_seed.json"
_ACTIVITIES_SEED = Path(__file__).parent / "data" / "activities_seed.json"


def _seed_builds() -> dict:
    data = json.loads(_BUILDS_SEED.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _seed_activities() -> list:
    return json.loads(_ACTIVITIES_SEED.read_text()).get("activities", [])


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS build_overrides (key TEXT PRIMARY KEY, data TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS activity_overrides (name TEXT PRIMARY KEY, data TEXT)")
    conn.commit()


def load_builds(conn: sqlite3.Connection) -> dict:
    """Seeded builds keyed 'Class|Subclass', with any saved edits replacing the seed."""
    _ensure(conn)
    builds = _seed_builds()
    for key, data in conn.execute("SELECT key, data FROM build_overrides"):
        builds[key] = json.loads(data)
    return builds


def save_build(conn: sqlite3.Connection, key: str, data: dict) -> None:
    _ensure(conn)
    conn.execute(
        "INSERT INTO build_overrides (key, data) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET data = excluded.data",
        (key, json.dumps(data)),
    )
    conn.commit()


def load_activities(conn: sqlite3.Connection) -> list:
    """Seeded activities with edits applied, plus any user-added activities."""
    _ensure(conn)
    overrides = {name: json.loads(data) for name, data in
                 conn.execute("SELECT name, data FROM activity_overrides")}
    result, seen = [], set()
    for activity in _seed_activities():
        name = activity["name"]
        seen.add(name)
        result.append(overrides.get(name, activity))
    for name, data in overrides.items():
        if name not in seen:
            result.append(data)
    return result


def save_activity(conn: sqlite3.Connection, name: str, data: dict) -> None:
    _ensure(conn)
    conn.execute(
        "INSERT INTO activity_overrides (name, data) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET data = excluded.data",
        (name, json.dumps(data)),
    )
    conn.commit()
