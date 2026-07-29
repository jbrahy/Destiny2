"""Batch planning — a character holds BUCKET_CAPACITY unequipped weapons per
bucket, so a large sweep is necessarily split across several in-game passes."""
from app.dismantle import (
    BUCKET_CAPACITY, Candidate, bucket_occupancy, plan_batch,
)

KINETIC, ENERGY, POWER = 1498876634, 2465295065, 953998645


def _cand(instance_id, bucket_hash=KINETIC):
    return Candidate(
        instance_id=instance_id, item_hash=1, name="Gun", icon="/i.jpg",
        power=1800, bucket_hash=bucket_hash, verdict="dismantle",
        source="tagged", reason="", blocked="", overridable=False,
    )


def test_everything_fits_in_an_empty_bucket():
    cands = [_cand(f"k{i}") for i in range(5)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert plan.staged == ["k0", "k1", "k2", "k3", "k4"]
    assert plan.deferred == []


def test_overflow_is_deferred_in_request_order():
    cands = [_cand(f"k{i}") for i in range(12)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert len(plan.staged) == BUCKET_CAPACITY
    assert plan.staged == [f"k{i}" for i in range(9)]
    assert plan.deferred == ["k9", "k10", "k11"]


def test_existing_occupancy_reduces_free_space():
    cands = [_cand(f"k{i}") for i in range(5)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {KINETIC: 7})
    assert plan.staged == ["k0", "k1"]
    assert plan.deferred == ["k2", "k3", "k4"]


def test_a_full_bucket_stages_nothing_from_it():
    cands = [_cand("k0")]
    plan = plan_batch(cands, ["k0"], {KINETIC: BUCKET_CAPACITY})
    assert plan.staged == []
    assert plan.deferred == ["k0"]


def test_buckets_are_budgeted_independently():
    cands = [_cand(f"k{i}", KINETIC) for i in range(10)] + [_cand("e0", ENERGY), _cand("p0", POWER)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {})
    assert "e0" in plan.staged and "p0" in plan.staged
    assert plan.deferred == ["k9"]


def test_per_bucket_reports_free_and_staged_counts():
    cands = [_cand(f"k{i}") for i in range(4)]
    plan = plan_batch(cands, [c.instance_id for c in cands], {KINETIC: 6})
    assert plan.per_bucket[KINETIC] == {"free": 3, "staged": 3, "name": "Kinetic"}


def test_unknown_bucket_is_deferred_rather_than_staged():
    """Defensive: a non-weapon bucket must never be staged."""
    plan = plan_batch([_cand("x", 999)], ["x"], {})
    assert plan.staged == []
    assert plan.deferred == ["x"]


def test_bucket_occupancy_counts_only_the_target_character_weapon_buckets():
    profile = {"characterInventories": {"data": {
        "char-1": {"items": [
            {"bucketHash": KINETIC}, {"bucketHash": KINETIC}, {"bucketHash": POWER},
            {"bucketHash": 138197802},  # general/vault-ish bucket, must be ignored
        ]},
        "char-2": {"items": [{"bucketHash": KINETIC}]},
    }}}
    assert bucket_occupancy(profile, "char-1") == {KINETIC: 2, ENERGY: 0, POWER: 1}


def test_bucket_occupancy_of_an_unknown_character_is_all_zero():
    assert bucket_occupancy({"characterInventories": {"data": {}}}, "nope") == {
        KINETIC: 0, ENERGY: 0, POWER: 0,
    }
