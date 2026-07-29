"""Dismantle-sweep decision logic.

Bungie's API cannot dismantle an item, so a "sweep" stages weapons onto one
character and unlocks them; the user dismantles the batch in-game. Everything
in this module is pure — no I/O — so the rules that protect a user's inventory
are cheap to test exhaustively.
"""
from dataclasses import dataclass

from app.models import Verdict

# Destiny 2 weapon inventory buckets. A character holds 9 unequipped per bucket
# (the equipped item lives in characterEquipment, a separate bucket).
WEAPON_BUCKETS = {
    1498876634: "Kinetic",
    2465295065: "Energy",
    953998645: "Power",
}
BUCKET_CAPACITY = 9

BLOCK_EXOTIC = "exotic"
BLOCK_VERDICT = "high_verdict"
BLOCK_EQUIPPED = "equipped"
BLOCK_LOCKED = "locked"

# Verdicts good enough that staging one requires an explicit override.
_BLOCKED_VERDICTS = {Verdict.GOD_ROLL, Verdict.MASTERWORK}
# The verdict the engine already flags as not worth keeping.
_SUGGESTED_VERDICT = Verdict.DISMANTLE


@dataclass
class Candidate:
    instance_id: str
    item_hash: int
    name: str
    icon: str
    power: int
    bucket_hash: int
    verdict: str
    source: str        # "tagged" | "suggested"
    reason: str
    blocked: str       # "" | BLOCK_EQUIPPED | BLOCK_LOCKED | BLOCK_EXOTIC | BLOCK_VERDICT
    overridable: bool


def classify(scored: list[dict], tags: dict[str, str]) -> list[Candidate]:
    """Build the sweep candidate list from scored weapons and the user's tags.

    A weapon is a candidate if the user tagged it 'junk', or if the scoring
    engine returned Verdict.DISMANTLE. An explicit 'keep', 'favorite', or
    'infuse' tag always wins and excludes the weapon entirely.
    Blocked candidates are still returned — the UI shows them greyed with a
    reason, so a block is visible rather than a silent omission.
    """
    out: list[Candidate] = []
    for row in scored:
        weapon = row["weapon"]
        tag = tags.get(weapon.instance_id, "")
        if tag in ("keep", "favorite", "infuse"):
            continue

        if tag == "junk":
            source, reason = "tagged", "You tagged this junk."
        elif row["verdict"] == _SUGGESTED_VERDICT:
            source = "suggested"
            reason = (
                row.get("note")
                if row.get("dupe_demoted")
                else "Suggested: only low-value perks."
            )
        else:
            continue

        if weapon.equipped:
            blocked, overridable = BLOCK_EQUIPPED, False
        elif weapon.is_locked:
            blocked, overridable = BLOCK_LOCKED, True
        elif weapon.is_exotic:
            blocked, overridable = BLOCK_EXOTIC, True
        elif row["verdict"] in _BLOCKED_VERDICTS:
            blocked, overridable = BLOCK_VERDICT, True
        else:
            blocked, overridable = "", False

        out.append(Candidate(
            instance_id=weapon.instance_id,
            item_hash=weapon.item_hash,
            name=weapon.name,
            icon=weapon.icon,
            power=weapon.power,
            bucket_hash=weapon.bucket_hash,
            verdict=row["verdict"].value,
            source=source,
            reason=reason,
            blocked=blocked,
            overridable=overridable,
        ))
    return out


def enforce_blocklist(
    candidates: list[Candidate], requested_ids: list[str], overrides: list[str],
) -> tuple[list[str], list[dict]]:
    """Filter a client's requested sweep down to what is actually permitted.

    Re-run server-side on every sweep even though preview already reported the
    blocks — the client is not trusted to have honored them. Returns
    (allowed_instance_ids, rejected) where rejected entries are
    {"instanceId": str, "reason": str}.
    """
    by_id = {c.instance_id: c for c in candidates}
    override_set = set(overrides)
    allowed: list[str] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for instance_id in requested_ids:
        if instance_id in seen:
            continue
        seen.add(instance_id)
        candidate = by_id.get(instance_id)
        if candidate is None:
            rejected.append({"instanceId": instance_id, "reason": "not_a_candidate"})
            continue
        if not candidate.blocked:
            allowed.append(instance_id)
            continue
        if candidate.overridable and instance_id in override_set:
            allowed.append(instance_id)
            continue
        rejected.append({"instanceId": instance_id, "reason": candidate.blocked})

    return allowed, rejected


@dataclass
class BatchPlan:
    staged: list[str]
    deferred: list[str]
    per_bucket: dict[int, dict]


def bucket_occupancy(profile: dict, character_id: str) -> dict[int, int]:
    """Count weapons already sitting unequipped in each of the target
    character's weapon buckets. Equipped items live in characterEquipment and
    do not consume inventory space, so they are correctly not counted here."""
    occupancy = {bucket: 0 for bucket in WEAPON_BUCKETS}
    inventories = profile.get("characterInventories", {}).get("data", {})
    for item in inventories.get(character_id, {}).get("items", []):
        bucket = item.get("bucketHash")
        if bucket in occupancy:
            occupancy[bucket] += 1
    return occupancy


def plan_batch(
    candidates: list[Candidate], allowed_ids: list[str], occupancy: dict[int, int],
) -> BatchPlan:
    """Split an approved sweep into what fits on the character now and what
    waits for the next pass. Preserves request order within each bucket."""
    by_id = {c.instance_id: c for c in candidates}
    free = {
        bucket: max(0, BUCKET_CAPACITY - occupancy.get(bucket, 0))
        for bucket in WEAPON_BUCKETS
    }
    staged_per_bucket = {bucket: 0 for bucket in WEAPON_BUCKETS}
    staged: list[str] = []
    deferred: list[str] = []
    staged_set: set[str] = set()

    for instance_id in allowed_ids:
        if instance_id in staged_set:
            continue
        candidate = by_id.get(instance_id)
        bucket = candidate.bucket_hash if candidate else None
        if bucket not in free or free[bucket] <= 0:
            deferred.append(instance_id)
            continue
        free[bucket] -= 1
        staged_per_bucket[bucket] += 1
        staged.append(instance_id)
        staged_set.add(instance_id)

    per_bucket = {
        bucket: {
            "name": name,
            "free": max(0, BUCKET_CAPACITY - occupancy.get(bucket, 0)),
            "staged": staged_per_bucket[bucket],
        }
        for bucket, name in WEAPON_BUCKETS.items()
    }
    return BatchPlan(staged=staged, deferred=deferred, per_bucket=per_bucket)
