# Destiny 2 Advisor — Feature Roadmap (20 candidates)

**Date:** 2026-06-21
**Author:** planning session

## Context: what already exists (do not re-propose)

Backend (FastAPI + SQLite KV cache, Bungie OAuth, manifest cache): weapon vault
assembly + per-perk scoring/verdicts, perk ratings store, armor assembly +
ratings, subclass builds, activities catalog, loadouts (save/apply), postmaster
pull, transfer/equip, account switching, and the **new recommendations engine**
(`recommend_weapons` + `/api/recommendations`).

Frontend: Weapons grid/filters/detail/compare, Perks page, Armor list/compare,
Builds, Activities, Loadouts, Postmaster, Recommend tab, account switcher.

All 20 features below are **new** relative to that surface.

## Scoring legend

- **Value:** ★ (nice) → ★★★★★ (transformative for the user)
- **Effort:** S (≈1 plan/day) · M (≈2–3 days) · L (≈1 week+)
- **API risk:** Low (data already cached / known-good endpoints) · Med (new
  profile components, mostly read) · High (Bungie limitations, e.g. the
  subclass-ownership #1572 issue already hit in this project)

---

## Tier 1 — Build on the recommendations engine (highest momentum)

### 1. Activity Loadout Builder (Recommendations Hub #2)
Compose `recommend_weapons` output + subclass builds into a full recommended
loadout per activity: best Primary/Special/Heavy from vault + the seeded
subclass build, with cross-weapon constraints (element coverage, DPS-vs-add-clear
role balance). One-click "apply" via the existing loadouts/transfer plumbing.
**Value ★★★★★ · Effort M · API risk Low.** Depends on: recommendations engine (done), loadouts/transfer (done).

### 2. Weapons-to-Chase (Recommendations Hub #3)
Curated meta-weapon seed dataset (god-roll perk combos per activity/slot) diffed
against the vault: "you don't own / don't have a good roll of X — worth
grinding." Editable seed like builds/activities.
**Value ★★★★ · Effort M · API risk Low.** Depends on: a new `meta_weapons_seed.json`.

### 3. Per-character recommendation context
Recommendations are vault-wide today. Tie them to a character's currently
equipped subclass/element so "Recommend" reflects who you're playing.
**Value ★★★ · Effort S · API risk Low.** Depends on: recommendations engine, characters endpoint (done).

---

## Tier 2 — Armor & stat optimization

### 4. Armor Stat-Tier Optimizer
Across all owned armor, compute the best 5-piece combination to hit a target
Armor 3.0 stat spread (or maximize a chosen stat), respecting one-exotic rule.
The long-standing "armor mod optimizer" gap.
**Value ★★★★★ · Effort L · API risk Low** (armor + stats already assembled).

### 5. Armor Mod Planner
Given a chosen build, recommend the armor mods (and required energy) to slot for
champion/elemental-well/charged-with-light style synergies. Editable mod dataset.
**Value ★★★ · Effort M · API risk Med** (mod sockets in manifest).

### 6. Power-Level Optimizer
Per character, show which owned items to equip to maximize total power, and the
delta to next pinnacle/powerful cap. Pure math over assembled power values.
**Value ★★★★ · Effort M · API risk Low.**

---

## Tier 3 — Vault management & hygiene

### 7. Vault Cleanup Assistant
Surface DISMANTLE-tier dupes and low-verdict random rolls as a "junk" worklist;
bulk-tag them and optionally herd them to one character for fast manual delete
(API can't dismantle, but can move/tag). Reuses verdicts + bulk transfer.
**Value ★★★★ · Effort M · API risk Low.**

### 8. Inventory-Pressure Dashboard
Vault capacity meter, per-character slot fullness, and postmaster-near-full
warnings (lost-item risk). Reuses counts + postmaster endpoints.
**Value ★★★ · Effort S · API risk Low.**

### 9. Advanced Search & Saved Filters
Extend the existing query parser with structured tokens (`is:masterworked`,
`perk:`, `verdict:`, `ammo:`, `element:`) and persist named saved searches.
**Value ★★★ · Effort M · API risk Low** (frontend-heavy, parser exists).

### 10. Loadout Import/Export (shareable codes)
Encode/decode loadouts to a portable string (DIM-compatible where feasible) so
users can share or back up loadouts.
**Value ★★★ · Effort M · API risk Low.**

---

## Tier 4 — Collection & progression tracking

### 11. Weapon Crafting Tracker
Track craftable patterns: which you've unlocked, deepsight progress, and which
enhanced perks are worth crafting given your perk ratings.
**Value ★★★★ · Effort L · API risk Med** (craftable/patterns components).

### 12. Catalyst Completion Tracker
Exotic catalyst progress (owned, in-progress %, not-acquired) with objective
breakdowns.
**Value ★★★ · Effort M · API risk Med.**

### 13. Collections Gap Finder
God-roll-capable legendary weapons you've never obtained (collections vs
meta/ratings), as acquisition targets. Pairs with #2.
**Value ★★★ · Effort M · API risk Med** (collectibles component).

### 14. Triumph / Seal / Title Progress
Surface seal completion % and nearest triumphs, read from profile records.
**Value ★★ · Effort M · API risk Med.**

### 15. Bounty / Pursuit Tracker
Active bounties/quests across characters with progress and expiry.
**Value ★★ · Effort S · API risk Med.**

---

## Tier 5 — Live game data & external

### 16. Vendor Roll Viewer
Current rolls from Xûr / Banshee / Ada / focused vendors, scored against your
perk ratings ("Banshee has an A-tier Roll today"). Vendor components are
notoriously fiddly — scope a single vendor first.
**Value ★★★★ · Effort L · API risk High** (vendor sales components, rotation).

### 17. Reset / Rotation Calendar
Daily/weekly reset countdowns, GM nightfall + featured raid/dungeon rotation
(seed dataset + date math; verify against live rotation).
**Value ★★ · Effort S · API risk Low.**

### 18. Champion-Coverage Checker per Activity
For a chosen activity's weekly champion mods, verify a proposed loadout covers
Barrier/Overload/Unstoppable and flag gaps. Composes with #1.
**Value ★★★ · Effort M · API risk Med** (weekly modifiers).

---

## Tier 6 — Platform & UX

### 19. Theme & Visual Polish Pass
Dark/light theme toggle, element/ammo badges consistently across all cards,
weapon-frame icons, and an empty/loading-state cleanup sweep.
**Value ★★ · Effort S · API risk None.**

### 20. PWA / Offline Cache
Installable PWA with offline read of the last-synced vault (cache already lives
in SQLite KV; expose a read-only offline mode + service worker).
**Value ★★ · Effort M · API risk None.**

---

## Recommended sequencing

1. **#1 Activity Loadout Builder** — highest value, directly extends the engine
   just shipped, all dependencies already exist. **← deep plan written next.**
2. #4 Armor Stat-Tier Optimizer — closes the biggest long-standing gap.
3. #2 Weapons-to-Chase — completes the Recommendations Hub trilogy.
4. #7 Vault Cleanup Assistant — high daily-use utility, low risk.
5. #6 Power-Level Optimizer — quick, satisfying win.

Then pick from Tiers 4–6 by interest. High-API-risk items (#16 vendors, #11
crafting) should be spiked (small feasibility probe) before committing a full
plan, given the project already hit a Bungie API limitation (#1572).
