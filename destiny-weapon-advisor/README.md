# Destiny 2 Weapon Advisor

A local web app that reads your Destiny 2 vault and inventory, scores every weapon against community DIM wishlists, and surfaces which ones are god rolls, solid keepers, or safe to dismantle — all without writing anything to your account.

> **Advice only.** This app reads your inventory but never modifies it. No dismantles, no transfers, no writes of any kind.
> Weapon scoring uses the [48klocs DIM voltron wishlist](https://github.com/48klocs/dim-wish-list-sources).

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A free Bungie developer app (see step 1 below)

---

## Setup

### 1. Register a Bungie application

Go to <https://www.bungie.net/en/Application> and create a new application with these exact settings:

| Field | Value |
|---|---|
| OAuth Client Type | **Confidential** |
| Redirect URL | `https://localhost:8443/callback` ← must match exactly |
| Scope | Read your Destiny vault and inventory + basic profile |

After saving, copy three values from the app detail page:
- **API Key**
- **OAuth client_id**
- **OAuth client_secret**

### 2. Configure the backend

```bash
cd destiny-weapon-advisor/backend
cp .env.example .env
```

Open `.env` and paste your three secrets:

```
BUNGIE_API_KEY=your_api_key_here
BUNGIE_CLIENT_ID=your_oauth_client_id_here
BUNGIE_CLIENT_SECRET=your_oauth_client_secret_here
```

The remaining defaults (`REDIRECT_URI`, `WISHLIST_URL`, `DB_PATH`) are correct as-is.

### 3. Start the backend

```bash
pip install -e ".[dev]"
python -m app.main
```

The backend generates a self-signed TLS certificate on first run and serves on **https://localhost:8443**.

### 4. Start the frontend

In a separate terminal:

```bash
cd destiny-weapon-advisor/frontend
npm install
npm run dev
```

The frontend serves on **http://localhost:5173**.

### 5. Log in

1. Open <http://localhost:5173> in your browser.
2. Click **Login with Bungie**.
3. Your browser will warn about the self-signed certificate for `https://localhost:8443` — click through the warning once (this is expected for local HTTPS).
4. Approve the OAuth prompt on Bungie.net.
5. You will be redirected back to the app, now authenticated.

> **First load note:** On your first weapon load the app downloads the Destiny 2 manifest (tens of MB). This may take a minute on slow connections — the page will populate once the download completes.

---

## What it does

| Step | Detail |
|---|---|
| Reads inventory | Calls the Bungie API for your vault, character inventory, and equipped weapons |
| Resolves names | Downloads and caches the Destiny 2 manifest to turn hash IDs into readable perk/weapon names |
| Scores weapons | Compares each weapon's perk columns against the DIM voltron community wishlist |
| Assigns a verdict | God Roll, Decent Roll, Keep, Junk, or Unknown (if no wishlist entry exists) |
| Shows the "why" | Each weapon detail panel lists the matched perks and the community note from the wishlist |

Use the filter controls to narrow by verdict, weapon type, or damage element. The detail panel opens on click.

---

## Troubleshooting

- **Certificate warning on every launch** — the self-signed cert regenerates each run; accept it once per browser session.
- **Empty inventory** — confirm your Bungie app scopes include inventory access and that you approved them during OAuth.
- **Manifest download hangs** — check your internet connection; the file is ~50–100 MB and is cached locally after the first download.
- **`BUNGIE_CLIENT_SECRET` mismatch** — ensure the secret in `.env` matches the Bungie app page exactly (no extra whitespace).
