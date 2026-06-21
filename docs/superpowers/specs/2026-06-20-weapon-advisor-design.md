# Destiny 2 Weapon Advisor — Design (Layer 1)

**Date:** 2026-06-20
**Status:** Approved (design); pending implementation plan
**Author:** maintainer + Claude

## Context

This is **Layer 1** of a larger, layered Destiny 2 account tool. The user already
uses Destiny Item Manager (DIM) and wants something DIM does not do: *think for them*
about weapons. Specifically — given everything in their inventory, tell them which
weapons are best, which perks matter, and which are worth spending materials to
upgrade, with the reasoning why.

The full long-term vision spans four capabilities:

1. **Weapon advisor** (this spec) — rank weapons, identify best perks.
2. Subclass build optimizer — best aspects/fragments per class+subclass.
3. Armor build optimizer — stat tiers + mods.
4. Activity loadout recommender — best loadout per campaign/strike/raid, with reasoning.

We are deliberately building **only Layer 1 now**, then layering the rest on top of
its OAuth + inventory foundation.

### Key architectural fact driving the design

The Bungie API tells you **what you own** and the **static game data** (the
"manifest"). It does **not** know **what is good or why** — there is no endpoint for
weapon/build quality. That judgment must come from a separate knowledge source, and
Destiny's meta shifts every season, so any source can go stale.

For Layer 1 (weapons), the chosen knowledge source is **community god-roll lists
("wishlists")** — the same crowd-sourced files DIM imports. They are actively
maintained, current, and authoritative-ish, but cover *weapon perks only* (which is
exactly Layer 1's scope). Layers 2–4 will require a different/additional source and
are out of scope here.

## Goals

- Log in with the user's real Bungie account (OAuth).
- Read every weapon they own (vault, all characters, equipped) including the actual
  rolled perks on each instance.
- Compare each weapon's roll against community wishlists.
- Present a ranked, filterable view with a recommendation badge per weapon and a
  human-readable "why".

## Non-Goals (explicit scope guardrails)

- **No writes to the account.** No auto-transfer/equip/upgrade. Advice only; the user
  performs upgrades in-game. This keeps the app entirely clear of Bungie's restricted
  "Advanced Write Action" permissions, which personal apps generally cannot obtain.
  Consequently the app requests **no write OAuth scopes** and *cannot* modify the
  account even by accident.
- No armor, subclass, or activity recommendations (Layers 2–4).
- No cloud/hosted component. Everything runs locally on the user's machine.

## Architecture

A local web app: Python/FastAPI backend + React/TypeScript frontend, SQLite for local
caching. Five components:

### 1. Bungie API client
- OAuth Authorization Code flow (Confidential client).
- `GetMembershipsForCurrentUser` to resolve the user's Destiny membership.
- `GetProfile` with components for inventory + item instances/sockets/perks:
  ProfileInventories (vault), CharacterInventories, CharacterEquipment, ItemInstances,
  ItemSockets, ItemPerks, ItemStats.
- Sends `X-API-Key` on every request; `Authorization: Bearer` on user endpoints.
- Token storage + auto-refresh.

### 2. Manifest store
- Bungie returns numeric hashes; the manifest maps hash → human data
  (DestinyInventoryItemDefinition, plug/perk definitions).
- Downloaded once, cached in SQLite, version-checked and re-downloaded when Bungie
  bumps the manifest version.

### 3. Wishlist parser
- Fetches a community DIM wishlist (voltron.txt format) by URL.
- Parses into a lookup: `itemHash -> [ {perk-hash combo, tags (PvE/PvP), note} ]`.
- Default to a well-maintained public wishlist; user-configurable; weapons absent from
  the list are flagged "No data".

### 4. Scoring engine (the brain)
- For each owned weapon instance, reads its rolled perks (from sockets) and compares
  against the wishlist entries for that itemHash.
- Detects duplicates across the inventory.
- Emits one badge + a "why" (matched perks + community note) per weapon.
- Pure/deterministic — no I/O — so it is fully unit-testable with fixtures.

### 5. Web UI (React/TS, Vite)
- Sortable, filterable grid of weapons with a colored recommendation badge each.
- Filters: recommendation, weapon type, element, PvE/PvP, character/vault.
- Detail panel: which perks matched and the explanatory note.

### Recommendation badges

| Badge | Meaning |
|---|---|
| 🟢 God roll | Rolled perks match a known top-tier combo (PvE and/or PvP). Keep + worth upgrading. |
| 🟡 Good / partial | Hits some key perks but not the full combo. Keep, situational. |
| 🔵 Upgrade target | God-roll perks present but not masterworked/enhanced → the to-do list. |
| ⚪ No data | No wishlist entry for this gun; user decides. |
| 🔴 Dismantle candidate | Random-roll weapon, no notable perks, better copies owned. |

Each badge includes the matched perks and the community note as the "why".

## Data Flow

1. User clicks **Login with Bungie** → redirected to Bungie → approves → redirected
   back with an auth code.
2. Backend exchanges code for token, calls `GetMembershipsForCurrentUser`.
3. Backend calls `GetProfile` with inventory + socket/perk components.
4. Manifest translates hashes → names; scoring engine rates every weapon.
5. Backend returns JSON; UI renders the ranked, filterable grid.
6. Token auto-refreshes; a **Refresh** button re-fetches inventory.

## Setup / Prerequisites (user, one-time)

Register an app at `https://www.bungie.net/en/Application`. Yields three secrets stored
in a local gitignored `.env`:

- **API Key** — sent on every request.
- **OAuth client_id + client_secret** — **Confidential** client type.
- **OAuth scopes**: `ReadDestinyInventoryAndVault` + basic profile. No write scopes.

### OAuth gotcha (designed-in from the start)

Bungie requires the OAuth **redirect URL to be HTTPS even for local dev**. The app runs
on `https://localhost:<port>` with a backend-generated self-signed cert (one-time
browser "proceed anyway" warning). The registered redirect URL must match exactly.

## Error Handling

- OAuth token expiry → silent refresh; refresh failure → prompt re-login.
- Manifest download failure → keep using cached copy; surface a staleness warning.
- Manifest version bump → re-download before scoring.
- Weapon not in any wishlist → "No data" badge (not an error).
- Bungie API rate limits / transient errors → backoff + retry; surface a clear message.

## Testing

- **Scoring engine** — pure unit tests with fixture inventory + fixture wishlist;
  covers god-roll / partial / upgrade / dupe / no-data cases. TDD: tests first.
- **Manifest + wishlist parsers** — tested against small saved fixture files.
- **Bungie client** — tested against mocked/recorded API responses; no live API or
  login required in the test suite.

## Project Layout

```
destiny-weapon-advisor/
  backend/   FastAPI: oauth, bungie client, manifest, wishlist, scoring + tests
  frontend/  React/TS (Vite): weapon grid, filters, detail panel
  docs/      design + setup guide
  .env       secrets (gitignored)
```

## Open Items for the Implementation Plan

- Pick the specific default community wishlist URL.
- Confirm exact `GetProfile` component numbers and socket-reading details against the
  current API version during implementation.
- Decide the local HTTPS cert-generation approach (library vs. mkcert vs. openssl).
