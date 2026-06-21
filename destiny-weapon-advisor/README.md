# Destiny 2 Advisor

A local web app for your Destiny 2 account. It reads your inventory and helps you decide
what to keep, what to chase, and what to run — with optional one-click moving of gear
between your characters and the vault.

**Features**

- **Weapons** — every weapon scored (God Roll / Upgrade / Good / Dismantle / No Data) by the
  ratings of the perks it actually rolled, with power, element, ammo, frame, full stats, and the
  rolled perks. Filter by character, verdict, type, or name.
- **Perks** — an editable rating book: rate each perk **per weapon type** (S/A/B/C/D), with the
  in-game description and your own notes. Your ratings drive the weapon verdicts.
- **Armor** — a stat optimizer: pick a class and the stats you care about, and it computes the
  best owned piece per slot (max one exotic) with totals and tiers. Uses live stats, so it tracks
  the current Armor 3.0 system automatically.
- **Move / Equip** — transfer weapons between characters and the vault and equip them, with a
  confirmation. (This writes to your account; see the scope note below.)
- **Multiple accounts** — if you have more than one Destiny membership (e.g. Xbox and PSN that
  aren't cross-saved), it auto-selects your most recently played one and lets you switch.

Everything is cached locally in SQLite; a **Refresh** button re-pulls from Bungie on demand.

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A free Bungie developer app (step 1)

## 1. Register a Bungie application

Go to <https://www.bungie.net/en/Application> and create an app:

| Field | Value |
|---|---|
| OAuth Client Type | **Confidential** |
| Redirect URL | `https://localhost:8443/callback` ← must match exactly |
| Scopes | **Read your Destiny vault and inventory** + **Move or equip your Destiny equipment** + basic profile |

> The **Move or equip** scope is what enables the transfer/equip feature. If you add it *after*
> first logging in, click **Re-login** in the app to issue a fresh token that includes it.

Copy three values from the app page: **API Key**, **OAuth client_id**, **OAuth client_secret**.

## 2. Configure

```bash
cd destiny-weapon-advisor/backend
cp .env.example .env
```

Paste your three secrets into `.env`:

```
BUNGIE_API_KEY=...
BUNGIE_CLIENT_ID=...
BUNGIE_CLIENT_SECRET=...
```

The other defaults are correct as-is.

## 3. Run (single-server — recommended)

```bash
./scripts/run.sh
```

This builds the frontend and starts the backend, which serves **both the app and the API** at
**<https://localhost:8443>**. Open that URL, click **Login with Bungie**, accept the one-time
self-signed-certificate warning, and approve the OAuth prompt.

> Equivalent manual steps: `cd frontend && npm install && npm run build`, then
> `cd ../backend && pip install -e ".[dev]" && python -m app.main`.

> **First load** downloads the Destiny manifest (~tens of MB) and is cached after that.

### Dev mode (hot-reloading frontend)

For frontend development, run the Vite dev server separately and point the OAuth redirect back to
it: set `FRONTEND_URL=http://localhost:5173` in `.env`, run the backend, then
`cd frontend && npm run dev` and use <http://localhost:5173> (it proxies `/api` to the backend).

---

## Notes & troubleshooting

- **Advice + writes.** Reads are always safe; the only writes are the explicit Move/Equip actions,
  which require the move scope and a confirmation. Changing perks/masterworks is *not* possible via
  the Bungie API for personal apps, so the app advises and you do those in-game.
- **Moving fails / HTTP error** — you likely haven't re-logged-in since adding the move scope.
  Click **Re-login**. Equipped weapons can't be moved — equip something else first.
- **Wrong characters / missing a character** — you probably have multiple non-cross-saved accounts.
  Use the account dropdown (top-right) to switch, then **Refresh**.
- **Certificate warning** — the self-signed cert is generated once and reused; accept it in the
  browser. Delete `backend/.certs/` to regenerate.
- **Perk ratings** are seeded from general early-2026 knowledge — treat them as a starting point and
  edit to your taste / the current season.

## Tests

```bash
cd backend && python -m pytest -q     # backend
cd frontend && npm run build          # frontend typecheck + build
```
