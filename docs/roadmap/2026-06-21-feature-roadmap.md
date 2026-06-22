# Destiny 2 Advisor — Roadmap

**Date:** 2026-06-21 (backlog pruned 2026-06-22)

## Delivered

Single-user local tool (FastAPI + SQLite + React/TS), running at
`https://localhost:8443`. Shipped to `main`:

- Weapon vault assembly + per-perk scoring/verdicts; perk-ratings store
- Armor assembly + ratings; **Save Armor Sets** (optimizer → named set → equip)
- Subclass builds; activities catalog; loadouts (save/apply); postmaster pull;
  transfer/equip; account switching
- **Recommendations engine** — best-from-vault per slot (`/api/recommendations`)
- **Activity Loadout Builder** — full per-activity loadout + equip
- **Verdict explanation + upgrade path** in the weapon detail panel
- **"Masterwork → God Roll" verdict** (replaced the old "Upgrade" status)
- **macOS launcher app** (`scripts/install-macos-app.sh`)

## Backlog

Cleared 2026-06-22. The earlier 20-candidate backlog (weapons-to-chase, armor
stat-tier optimizer, vault cleanup, crafting/catalyst/collections trackers,
vendor rolls, etc.) was removed to refocus on the public-deployment question.
Prior versions are recoverable from git history if any idea is wanted later.

## Active direction

Evaluating whether/how to take the tool from single-user local to a
public-internet service. See `docs/` design notes once a direction is chosen.
