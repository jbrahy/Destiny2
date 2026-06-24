# Rotating Ad System — Design Spec

**Sub-project:** B (of program: C → A → B → D)
**Date:** 2026-06-23
**Status:** Approved design — pending implementation plan
**Builds on:** A (multi-user FastAPI + MySQL) and C (`docs/offers/270920-offers-manifest.json`, 104 enabled offers with tracking URLs).

---

## 1. Goal

Monetize destinyopt.com with a non-intrusive, always-present sponsored unit: **4 rotating offers shown on every page**, with custom sales-pitch creatives and click tracking, so "the site pays for itself." Offers come from partner **270920**'s enabled inventory (sub-project C).

**Non-goals:** admin UI for editing creatives (future), A/B testing of copy, per-user offer targeting (offers are global), deployment (sub-project D).

---

## 2. Architecture

- A **global `offers` table** (same inventory for all users) seeded from C's manifest, with per-offer creative copy (`headline`/`blurb`/`cta`) and optional `image_url`.
- `GET /api/ads?n=4` returns a random sample of active offers with creative fields + a backend click URL.
- `GET /api/ads/{offer_id}/click` logs the click and `302`-redirects to the offer's 270920 tracking URL.
- A `<SponsoredAds>` React component renders the 4-card "Sponsored" grid below every page's content and re-fetches on navigation → natural per-page rotation.
- All ad routes sit behind the existing `get_current_user` auth (logged-in users only). Offers/ads data is global; only `ad_clicks` records `user_id`.

```
SponsoredAds (App.tsx, every section)
  → GET /api/ads?n=4 ──> offers table (random active sample)
  → CTA click → GET /api/ads/{id}/click ──> ad_clicks insert ──> 302 tracking_url
import_offers.py: manifest + offer_creatives.json (+ Everflow images) → upsert offers
```

---

## 3. Data model (MySQL 8, InnoDB, utf8mb4_unicode_ci, migration `0003_offers.sql`)

### `offers` (global)
| column | type | notes |
|---|---|---|
| `offer_id` | BIGINT(20) UNSIGNED PK | Everflow offer id (from manifest) |
| `name` | VARCHAR(255) NOT NULL | offer name |
| `category` | VARCHAR(128) | |
| `advertiser` | VARCHAR(190) | |
| `countries` | VARCHAR(64) | e.g. "US", "GLOBAL" |
| `payout_type` | VARCHAR(16) | CPA/CPL/CPC/PRV |
| `payout_amount` | DECIMAL(12,2) DEFAULT 0.00 | |
| `tracking_url` | TEXT NOT NULL | 270920 affiliate link |
| `headline` | VARCHAR(190) NOT NULL | creative |
| `blurb` | VARCHAR(400) NOT NULL | creative |
| `cta` | VARCHAR(40) NOT NULL | e.g. "Claim offer" |
| `image_url` | TEXT NULL | best-effort Everflow creative image |
| `status` | ENUM('active','paused') DEFAULT 'active' | |
| `created_at` / `updated_at` | TIMESTAMP | `updated_at` ON UPDATE |

### `ad_clicks`
| column | type | notes |
|---|---|---|
| `click_id` | BIGINT(20) UNSIGNED PK AUTO_INCREMENT | |
| `offer_id` | BIGINT(20) UNSIGNED NOT NULL, INDEX | no FK (keep history if offer removed) |
| `user_id` | BIGINT(20) UNSIGNED NOT NULL, INDEX, FK→users ON DELETE CASCADE | |
| `clicked_at` | TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP | |

---

## 4. Creatives pipeline (`scripts/import_offers.py`)

Idempotent importer (forward-runnable any time):
1. Read `docs/offers/270920-offers-manifest.json`.
2. For each offer set creative fields by this precedence (the 1+2+3 blend):
   - **Authored copy** — `app/data/offer_creatives.json` keyed by `offer_id` → `{headline, blurb, cta}`. Custom punchy per-offer copy is authored for all 104 offers during implementation and committed.
   - **Template fallback** — for any offer with no authored entry: `headline = name`, `blurb = f"{advertiser} — check out this offer."`, `cta = "Learn more"`.
   - **Everflow imagery (best-effort)** — query the Everflow API for the offer's creative assets; if an image/banner asset URL exists, store it in `image_url`; otherwise `image_url` stays NULL (text-only card). Failures here never block the import (logged, skipped).
3. Upsert into `offers` (`INSERT ... ON DUPLICATE KEY UPDATE` on `offer_id`). Offers in the table but absent from the manifest are set `status='paused'` (not deleted).

`tracking_url`, `name`, `category`, `advertiser`, `countries`, `payout_*` come straight from the manifest.

---

## 5. API (FastAPI, behind `get_current_user`)

- **`GET /api/ads`** — query `n` (default 4, capped at 8). Returns `{"ads": [{offer_id, headline, blurb, cta, image_url, click_url}]}` where `click_url = "/api/ads/{offer_id}/click"`. Selects a random sample of `status='active'` offers (`ORDER BY RAND() LIMIT n` — acceptable at this table size). 401 without session.
- **`GET /api/ads/{offer_id}/click`** — look up the offer; if missing or `paused` → 404. Insert an `ad_clicks` row `(offer_id, user_id, now)`. Return `RedirectResponse(tracking_url, status_code=302)`. 401 without session.

Repositories: `app/repositories/offers.py` (`list_random_active(pool, n)`, `get_active(pool, offer_id)`, `upsert(pool, offer)`, `pause_missing(pool, keep_ids)`) and `ad_clicks` insert (`log_click(pool, offer_id, user_id)`). Explicit parameterized SQL.

---

## 6. Frontend (`<SponsoredAds>`)

- New `frontend/src/components/SponsoredAds.tsx`: on mount and whenever the active `section` changes, fetch `/api/ads?n=4` via `apiFetch`. Render a labeled **"Sponsored"** responsive 4-card grid: optional `image_url` thumbnail, `headline` (bold), `blurb`, and a CTA button/link → `click_url` with `target="_blank" rel="noopener sponsored"`.
- Mounted in `App.tsx` **below the content div**, inside the authed layout, so it appears on every section. Pass `section` as a prop (or key) so navigation re-fetches and rotates the 4 ads.
- Styling matches the app (system-ui), visually distinct as sponsored, never overlaps content. Renders nothing (graceful) if the fetch fails or returns empty.

---

## 7. Error handling

| Condition | Behavior |
|---|---|
| `/api/ads` fails / empty | component renders nothing (no broken UI) |
| click on unknown/paused offer | 404 |
| Everflow image fetch fails at import | log + skip (image_url NULL); import continues |
| DB down | 503 (existing handling) |
| unauthenticated | 401 (ads hidden behind login gate) |

---

## 8. Testing

- **Backend** (pytest, MySQL fixtures): migration `0003` applies; `offers` upsert idempotent; `list_random_active` returns only active, respects `n` cap; `GET /api/ads` 401 without session, returns ≤n ads with `click_url`; `GET /api/ads/{id}/click` logs an `ad_clicks` row and 302s to the tracking_url; 404 on unknown/paused; click requires auth.
- **Import script**: authored-copy precedence over template fallback; offers absent from manifest get `status='paused'`.
- **Frontend** (vitest): `<SponsoredAds>` renders 4 cards from a mocked `/api/ads`; CTA href = `click_url`; re-fetches when `section` prop changes; renders nothing on fetch error.

---

## 9. Rollout

Built on the `feat/public-multiuser-and-offers` branch atop A. The importer is run as a deploy step (sub-project D) and re-runnable whenever C's manifest is refreshed. No per-user migration needed (global data).
