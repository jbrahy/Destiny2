"""Blocklist enforcement — the guard against staging something irreplaceable.

Rules under test:
  equipped        -> blocked, override NEVER permitted (hard block, first)
  locked          -> blocked, override permitted
  exotic          -> blocked, override permitted
  god_roll        -> blocked, override permitted
  masterwork      -> blocked, override permitted
  good / no_data  -> allowed only if the user tagged them junk
  dismantle       -> suggested (unchecked), allowed when requested
  keep/favorite/infuse tags -> excluded entirely, never a candidate
"""
from app.dismantle import (
    BLOCK_EQUIPPED, BLOCK_EXOTIC, BLOCK_LOCKED, BLOCK_VERDICT,
    Candidate, classify, enforce_blocklist,
)
from app.models import OwnedWeapon, Verdict


def _weapon(instance_id, **kw):
    defaults = dict(
        item_hash=1, name="Test Gun", weapon_type="Hand Cannon", element="Arc",
        is_masterworked=False, is_random_roll=True, perks=frozenset(),
        location="Vault", power=1800, icon="/i.jpg", equipped=False,
        is_exotic=False, bucket_hash=1498876634, is_locked=False,
    )
    defaults.update(kw)
    return OwnedWeapon(instance_id=instance_id, **defaults)


def _scored(weapon, verdict, **kw):
    row = {"weapon": weapon, "verdict": verdict, "rated": [], "note": "",
           "tags": [], "is_duplicate": False}
    row.update(kw)
    return row


def test_junk_tagged_weapon_is_a_tagged_candidate():
    scored = [_scored(_weapon("a"), Verdict.GOOD)]
    out = classify(scored, {"a": "junk"})
    assert len(out) == 1
    assert out[0].source == "tagged"
    assert out[0].blocked == ""


def test_dismantle_verdict_is_a_suggestion():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    out = classify(scored, {})
    assert out[0].source == "suggested"
    assert out[0].blocked == ""


def test_good_and_no_data_are_not_candidates_without_a_junk_tag():
    scored = [_scored(_weapon("a"), Verdict.GOOD),
              _scored(_weapon("b"), Verdict.NO_DATA)]
    assert classify(scored, {}) == []


def test_keep_tag_excludes_a_dismantle_verdict_weapon():
    """An explicit keep beats the engine's suggestion."""
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    assert classify(scored, {"a": "keep"}) == []


def test_favorite_tag_excludes_a_dismantle_verdict_weapon():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    assert classify(scored, {"a": "favorite"}) == []


def test_infuse_tag_excludes_a_dismantle_verdict_weapon():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE)]
    assert classify(scored, {"a": "infuse"}) == []


def test_exotic_is_blocked_but_overridable():
    scored = [_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EXOTIC
    assert out[0].overridable is True


def test_locked_is_blocked_but_overridable():
    scored = [_scored(_weapon("a", is_locked=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_LOCKED
    assert out[0].overridable is True


def test_god_roll_and_masterwork_verdicts_are_blocked_but_overridable():
    scored = [_scored(_weapon("a"), Verdict.GOD_ROLL),
              _scored(_weapon("b"), Verdict.MASTERWORK)]
    out = classify(scored, {"a": "junk", "b": "junk"})
    assert {c.instance_id: c.blocked for c in out} == {
        "a": BLOCK_VERDICT, "b": BLOCK_VERDICT,
    }
    assert all(c.overridable for c in out)


def test_equipped_is_blocked_and_not_overridable():
    scored = [_scored(_weapon("a", equipped=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EQUIPPED
    assert out[0].overridable is False


def test_equipped_beats_exotic_in_block_precedence():
    """Rule precedence is load-bearing: reordering the if/elif chain would
    silently make an equipped exotic overridable. Pin equipped as first."""
    scored = [_scored(_weapon("a", equipped=True, is_exotic=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EQUIPPED
    assert out[0].overridable is False


def test_equipped_beats_high_verdict_in_block_precedence():
    scored = [_scored(_weapon("a", equipped=True), Verdict.GOD_ROLL)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EQUIPPED
    assert out[0].overridable is False


def test_equipped_beats_locked_in_block_precedence():
    scored = [_scored(_weapon("a", equipped=True, is_locked=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_EQUIPPED
    assert out[0].overridable is False


def test_locked_beats_exotic_in_block_precedence():
    """A locked exotic reports BLOCK_LOCKED, pinning the full ordering:
    equipped -> locked -> exotic -> high_verdict."""
    scored = [_scored(_weapon("a", is_locked=True, is_exotic=True), Verdict.DISMANTLE)]
    out = classify(scored, {"a": "junk"})
    assert out[0].blocked == BLOCK_LOCKED
    assert out[0].overridable is True


def test_dupe_demoted_suggestion_reports_the_duplicate_reason():
    scored = [_scored(_weapon("a"), Verdict.DISMANTLE, dupe_demoted=True,
                      note="A better-perked copy of this weapon exists in your inventory.")]
    out = classify(scored, {})
    assert "better-perked copy" in out[0].reason


def test_enforce_blocklist_allows_a_clean_request():
    cands = classify([_scored(_weapon("a"), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], [])
    assert allowed == ["a"]
    assert rejected == []


def test_enforce_blocklist_rejects_a_blocked_item_without_override():
    cands = classify([_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], [])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EXOTIC}]


def test_enforce_blocklist_permits_a_blocked_item_with_override():
    cands = classify([_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], ["a"])
    assert allowed == ["a"]
    assert rejected == []


def test_override_cannot_unblock_an_equipped_weapon():
    """The hard block. An override must never reach the equipped rule."""
    cands = classify([_scored(_weapon("a", equipped=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a"], ["a"])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EQUIPPED}]


def test_override_cannot_unblock_an_equipped_exotic_weapon():
    """Even though exotic alone is overridable, equipped takes precedence and
    stays a hard block no matter what else is true about the weapon."""
    cands = classify(
        [_scored(_weapon("a", equipped=True, is_exotic=True), Verdict.DISMANTLE)],
        {"a": "junk"},
    )
    allowed, rejected = enforce_blocklist(cands, ["a"], ["a"])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EQUIPPED}]


def test_enforce_blocklist_rejects_an_id_that_is_not_a_candidate():
    """A client asking to sweep something the preview never offered."""
    cands = classify([_scored(_weapon("a"), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["ghost-id"], [])
    assert allowed == []
    assert rejected == [{"instanceId": "ghost-id", "reason": "not_a_candidate"}]


def test_enforce_blocklist_deduplicates_a_repeated_allowed_id():
    """A client posting the same id twice must not double-charge capacity
    downstream in plan_batch — collapse to a single decision."""
    cands = classify([_scored(_weapon("a"), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a", "a"], [])
    assert allowed == ["a"]
    assert rejected == []


def test_enforce_blocklist_deduplicates_a_repeated_blocked_id():
    """A repeated id must not produce a duplicate rejected entry either."""
    cands = classify([_scored(_weapon("a", is_exotic=True), Verdict.DISMANTLE)], {"a": "junk"})
    allowed, rejected = enforce_blocklist(cands, ["a", "a"], [])
    assert allowed == []
    assert rejected == [{"instanceId": "a", "reason": BLOCK_EXOTIC}]


def test_enforce_blocklist_preserves_order_with_interleaved_duplicates():
    cands = classify(
        [_scored(_weapon("a"), Verdict.DISMANTLE),
         _scored(_weapon("b"), Verdict.DISMANTLE),
         _scored(_weapon("c"), Verdict.DISMANTLE)],
        {"a": "junk", "b": "junk", "c": "junk"},
    )
    allowed, rejected = enforce_blocklist(cands, ["a", "b", "a", "c"], [])
    assert allowed == ["a", "b", "c"]
    assert rejected == []
