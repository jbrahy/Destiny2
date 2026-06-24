# SEO Foundation (E1+E2) — Design Spec

**Sub-project:** E1+E2 (first slice of program E — SEO public content site), within C → A → B → **E** → D.
**Date:** 2026-06-23
**Status:** Approved design — pending implementation plan
**Builds on:** A (multi-user app, default perk-rating seed) and B (`SponsoredAds` unit). Charter: `docs/roadmap/sub-project-E-seo-content-site.md`.

---

## 1. Goal

Stand up the **public, crawlable content surface** for destinyopt.com: a static-site-generation (SSG) pipeline that prerenders public routes to HTML, full technical SEO plumbing, and a build-time content data layer from the Bungie manifest — proven end-to-end with one `/weapons/:slug` page. The private per-user app stays a client-only SPA, `noindex`, excluded from prerender.

**Non-goals (later E sub-projects):** full weapon catalog polish + perk pages (E3), guides (E4), on-site search + internal linking (E5), rich landing page (E6). E1 ships only a minimal landing page.

---

## 2. Decisions locked
- **Toolchain:** `vite-react-ssg` (`/daydreamer-riri/vite-react-ssg`), keeping the existing Vite + React stack.
- **URLs:** top-level paths — `/` (landing), `/weapons/:slug` (public); `/app/*` (private dashboard).
- **Rendering split:** public routes prerendered (SSG); `/app/*` client-only SPA, excluded via `ssgOptions.includedRoutes`, `noindex`.
- **Content source:** Bungie manifest (public, no auth) + default perk-rating seed (from A), generated to static JSON at build time. Non-user-specific.

---

## 3. Architecture

```
ViteReactSSG(routes) [src/main.tsx]
 routes.tsx:
   /            PublicLayout > LandingPage            (prerendered)
   /weapons/:slug  PublicLayout > WeaponPage          (prerendered; getStaticPaths + loader)
   /app/*       AppShell (existing dashboard)          (client-only, noindex, NOT prerendered)
PublicLayout: nav + footer + <SponsoredAds> (from B) + <Head> per page
build_content.mjs (build-time): Bungie manifest + default ratings -> src/content/*.json
post-build: generate dist/sitemap.xml from prerendered public paths
public/robots.txt: allow public, Disallow /app and /api, link sitemap
```

- **`src/main.tsx`** — replace the current `createRoot(...).render(<App/>)` with `export const createRoot = ViteReactSSG({ routes, basename: import.meta.env.BASE_URL })`.
- **`src/routes.tsx`** — `RouteRecord[]`: public routes + the `/app/*` private subtree (lazy, client-only).
- **`src/components/PublicLayout.tsx`** — header/nav (links: Home, Weapons, "Open the App" → `/app`), `<Outlet/>`, footer, `<SponsoredAds section="public"/>`.
- **Existing dashboard** (`App.tsx` content) is relocated under an `/app` route element (`AppShell`) — login gate (`fetchStatus`), Nav tabs, all pages, logout, and SponsoredAds all carry over unchanged in behavior; only its mount point moves from root to `/app`.

---

## 4. Technical SEO

- **Per-route head** via vite-react-ssg's head support (`<Head>` component): `<title>`, `<meta name="description">`, `<link rel="canonical">`, Open Graph (`og:title/description/type/url`), Twitter card tags. A small `src/seo/Seo.tsx` helper component centralizes this (props: `title`, `description`, `path`, `image?`, `noindex?`).
- **`public/robots.txt`** (static):
  ```
  User-agent: *
  Allow: /
  Disallow: /app
  Disallow: /api
  Sitemap: https://destinyopt.com/sitemap.xml
  ```
- **`sitemap.xml`** — `scripts/gen_sitemap.mjs` runs after the SSG build: scan `dist/` for generated `index.html` files, emit `<url>` entries for public paths only (exclude `/app`), absolute URLs under `https://destinyopt.com`. Wired as a `postbuild` npm step.
- **JSON-LD** — `src/seo/jsonld.ts` helpers returning structured-data objects; rendered via a `<script type="application/ld+json">` in `Seo.tsx`. Landing → `WebSite`; weapon page → `ItemPage`/`Product`-style object (name, description, category).
- **Private noindex** — the `/app` AppShell renders `<Seo noindex />` → `<meta name="robots" content="noindex,nofollow">`.

---

## 5. Public content data layer (E2, build-time)

- **`scripts/build_content.mjs`** (Node, run before `vite-react-ssg build`):
  1. Fetch the Bungie manifest: `GET https://www.bungie.net/Platform/Destiny2/Manifest/` then the `DestinyInventoryItemDefinition` + `DestinyStatDefinition` JSON world content (English). Requires the Bungie `X-API-Key` header (read from env `BUNGIE_API_KEY`).
  2. Read the default perk-rating seed `backend/app/data/perk_ratings_seed.json` (the non-user base ratings).
  3. Emit to `frontend/src/content/`:
     - `weapons-index.json` — array of `{ slug, name, type, element }` for every indexable weapon (weapons = manifest items with `itemType==3`, non-redacted, having a display name). `slug` = kebab-cased name + short hash suffix to guarantee uniqueness.
     - `weapons/<slug>.json` — per weapon: `{ slug, name, type, element, ammoType, frame, stats, perks: [{name, description, rating}], godRoll: [perk names] }` where `rating`/`godRoll` derive from the default seed.
  4. Idempotent: overwrites the content dir each run; safe to re-run.
- **`getStaticPaths`** for `/weapons/:slug` imports `weapons-index.json` and returns `weapons/<slug>` for each entry.
- **Per-page `loader`** reads `weapons/<slug>.json` (guarded `if (!import.meta.ssr) return ...client fallback`), exposed via `useLoaderData`.
- For the vertical slice, the generator may cap the emitted set (e.g., a curated handful) behind a flag to keep build fast; the full catalog is E3. Document the cap in the generator output (`log` count).

---

## 6. Components

| File | Responsibility |
|---|---|
| `frontend/src/main.tsx` | ViteReactSSG entry (replaces createRoot render) |
| `frontend/src/routes.tsx` | route tree (public + `/app/*`) |
| `frontend/src/components/PublicLayout.tsx` | public chrome + SponsoredAds + Outlet |
| `frontend/src/components/AppShell.tsx` | wraps the existing dashboard under `/app` (login gate carries over) |
| `frontend/src/pages/Landing.tsx` | minimal landing page (what the tool is + "Open the App" CTA + Seo) |
| `frontend/src/pages/WeaponPage.tsx` | `/weapons/:slug` page (loader + Seo + JSON-LD + content render) |
| `frontend/src/seo/Seo.tsx` | head/meta/OG/canonical/JSON-LD/noindex helper |
| `frontend/src/seo/jsonld.ts` | structured-data builders |
| `frontend/src/content/*` | generated content JSON (git-ignored or committed — see §9) |
| `scripts/build_content.mjs` | build-time content generator |
| `scripts/gen_sitemap.mjs` | post-build sitemap generator |
| `frontend/public/robots.txt` | crawl rules |
| `frontend/vite.config.ts` | add `ssgOptions.includedRoutes` (exclude `/app`) |
| `frontend/package.json` | add `vite-react-ssg`, `react-router-dom`; scripts: `build` = `build_content && vite-react-ssg build && gen_sitemap` |

---

## 7. Error handling

| Condition | Behavior |
|---|---|
| Bungie manifest fetch fails at build | generator exits non-zero with a clear message (build fails loudly — better than shipping empty content) |
| Missing `BUNGIE_API_KEY` at build | generator errors with guidance |
| Unknown weapon slug at runtime | WeaponPage shows a "not found" state (client nav); not prerendered so no broken static page |
| `/app` accessed by crawler | `noindex` + robots Disallow; app itself still works for users (client-only) |

---

## 8. Testing

- **Content generator** (`scripts/build_content.test.mjs`, node/vitest): slug uniqueness/stability; weapons-index + per-weapon shape; god-roll derived from seed; handles a small fixture manifest (do NOT hit the network in tests — pass a fixture).
- **SEO helpers** (vitest): `Seo` produces expected title/canonical/og/noindex; `jsonld` builders produce valid objects.
- **Build smoke** (a test or CI step): after `npm run build`, assert `dist/index.html` exists, `dist/weapons/<sample-slug>/index.html` exists and contains the weapon name + a `<title>` + canonical; `dist/sitemap.xml` exists, lists the weapon URL, excludes `/app`; `dist/robots.txt` present with `Disallow: /app`.
- **Route split**: assert `/app` is not emitted as prerendered static content and the AppShell carries `noindex`.
- **Regression**: existing frontend vitest + backend pytest still pass; the relocated dashboard still mounts at `/app` with its login gate.

---

## 9. Rollout / open choices

- **Content JSON**: generated at build; **git-ignore** `frontend/src/content/` (regenerated each build) — add to `.gitignore`. Commit a tiny fixture for tests.
- **Build pipeline**: `npm run build` orchestrates content → SSG → sitemap. Sub-project D wires the build + serving (nginx serving `dist/` static for public routes; the FastAPI app for `/api` and the `/app` SPA fallback) at destinyopt.com.
- **Hosting model** (decided in D): static `dist/` served by nginx/CDN with SPA fallback for `/app/*`; `/api/*` proxied to FastAPI.
