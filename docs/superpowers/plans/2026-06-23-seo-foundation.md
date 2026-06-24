# SEO Foundation (E1+E2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an SSG public content surface (vite-react-ssg) to the Destiny Advisor: prerendered `/` + `/weapons/:slug`, full technical SEO, a build-time content generator from the Bungie manifest, and the private app relocated to `/app` (noindex), proven end-to-end with one weapon page.

**Architecture:** Introduce React Router + `vite-react-ssg`; split routes into prerendered public pages (PublicLayout) and a client-only `/app` SPA (existing dashboard). A Node content generator emits static JSON the public pages render from. Post-build sitemap + static robots.

**Tech Stack:** Vite, React 18 + TypeScript, `vite-react-ssg`, `react-router-dom` v6, vitest, Node (ESM build scripts).

## Global Constraints

- Builds on branch `feat/public-multiuser-and-offers` (sub-projects A+B). Do NOT create branches.
- Toolchain `vite-react-ssg` (`/daydreamer-riri/vite-react-ssg`). **Implementers: verify current API via Context7 (`mcp__context7__query-docs`, libraryId `/daydreamer-riri/vite-react-ssg`) before writing SSG wiring** — entry is `export const createRoot = ViteReactSSG({ routes, basename })` in `main.tsx`; routes are `RouteRecord[]`; dynamic routes need `getStaticPaths`; build-time data via react-router `loader` (+ `import.meta.ssr` guard for server-only code); prerender selection via `ssgOptions.includedRoutes` in `vite.config.ts`.
- URLs: `/` landing, `/weapons/:slug` public (prerendered); `/app/*` private (client-only, NOT prerendered, `noindex`).
- Canonical host: `https://destinyopt.com` (no `www`).
- Existing private dashboard behavior (Bungie login gate via `fetchStatus`, tabs, logout, `<SponsoredAds>`) carries over unchanged — only its mount point moves to `/app`.
- Content JSON under `frontend/src/content/` is generated + git-ignored; commit only a small test fixture.
- TDD; commit per task. Frontend tests: `cd frontend && npm test`; build: `npm run build`.
- Tests must NOT hit the Bungie network — the content generator takes an injectable manifest (pass a fixture in tests).

## Spec

Source: `docs/superpowers/specs/2026-06-23-seo-foundation-design.md`.

---

## File Structure

**Create:** `frontend/src/routes.tsx`, `frontend/src/components/PublicLayout.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/Landing.tsx`, `frontend/src/pages/WeaponPage.tsx`, `frontend/src/seo/Seo.tsx`, `frontend/src/seo/jsonld.ts`, `frontend/public/robots.txt`, `scripts/build_content.mjs`, `scripts/gen_sitemap.mjs`, `frontend/src/content/__fixtures__/manifest.sample.json`, plus test files.
**Modify:** `frontend/src/main.tsx` (ViteReactSSG entry), `frontend/vite.config.ts` (ssgOptions), `frontend/package.json` (deps + build scripts), `frontend/.gitignore` (or repo `.gitignore`) for `src/content/` (except fixtures), `frontend/src/App.tsx` (becomes the AppShell body or is wrapped — see Task 1).

---

### Task 1: Toolchain + route restructure (app → /app, landing at /)

**Files:**
- Modify: `frontend/package.json` (add `vite-react-ssg`, `react-router-dom`), `frontend/src/main.tsx`, `frontend/vite.config.ts`, `frontend/src/App.tsx`
- Create: `frontend/src/routes.tsx`, `frontend/src/components/PublicLayout.tsx`, `frontend/src/components/AppShell.tsx`, `frontend/src/pages/Landing.tsx`
- Test: build smoke (manual command in steps) + existing vitest must still pass

**Interfaces:**
- Produces: `routes` (RouteRecord[]) exported from `routes.tsx`; `createRoot` from `main.tsx`; `<PublicLayout>` (renders nav + `<Outlet/>` + footer + `<SponsoredAds section="public"/>`); `<AppShell>` (renders the existing dashboard: login gate + Nav + pages + SponsoredAds).

- [ ] **Step 1: Verify the vite-react-ssg entry/route API via Context7** (`query-docs` libraryId `/daydreamer-riri/vite-react-ssg`, query "ViteReactSSG main entry, RouteRecord, includedRoutes, react-router v6 nested routes with Outlet"). Confirm exact import names before coding.
- [ ] **Step 2: Add deps** — `cd frontend && npm install vite-react-ssg react-router-dom` (record versions in package.json). Run `npm test` to confirm baseline still green BEFORE restructuring.
- [ ] **Step 3: Relocate the dashboard into `AppShell`** — move the current authed-UI body of `App.tsx` (login gate via `fetchStatus`, `<Nav>`, the section switch, `<SponsoredAds section={section}/>`, logout) into `frontend/src/components/AppShell.tsx` as a component. `App.tsx` is no longer the render root.
- [ ] **Step 4: Create `Landing.tsx`** — a minimal public landing: a heading, one paragraph on what the tool does, and an "Open the App" link to `/app`. (Seo is added in Task 2.)
- [ ] **Step 5: Create `PublicLayout.tsx`** — header with links (Home `/`, "Open the App" `/app`), `<Outlet/>` (react-router), a footer, and `<SponsoredAds section="public"/>` below the outlet.
- [ ] **Step 6: Create `routes.tsx`**:
```tsx
import type { RouteRecord } from 'vite-react-ssg'
import React from 'react'
import { PublicLayout } from './components/PublicLayout'

export const routes: RouteRecord[] = [
  {
    path: '/',
    element: <PublicLayout />,
    entry: 'src/components/PublicLayout.tsx',
    children: [
      { index: true, Component: React.lazy(() => import('./pages/Landing')) },
      // /weapons/:slug added in Task 4
    ],
  },
  {
    path: '/app/*',
    lazy: () => import('./components/AppShell').then(m => ({ Component: m.AppShell })),
  },
]
```
(Ensure `Landing.tsx` and `AppShell.tsx` export a default/`Component` per vite-react-ssg's lazy contract — verify shape via Context7.)
- [ ] **Step 7: Rewrite `main.tsx`** to the ViteReactSSG entry:
```tsx
import { ViteReactSSG } from 'vite-react-ssg'
import { routes } from './routes'
import './index.css'

export const createRoot = ViteReactSSG({ routes, basename: import.meta.env.BASE_URL })
```
- [ ] **Step 8: vite.config** — add `ssgOptions.includedRoutes` that drops anything under `/app`:
```ts
// inside defineConfig({ ... })
ssgOptions: {
  includedRoutes(paths) { return paths.filter(p => !p.startsWith('/app')) },
},
```
- [ ] **Step 9: Build + verify** — `npm run build` (still the default `vite build` script for now; vite-react-ssg's CLI is wired in Task 5). If vite-react-ssg requires its own build command, set `package.json` `"build": "vite-react-ssg build"` now. Verify: `test -f dist/index.html && grep -q "Open the App" dist/index.html` (landing prerendered). Run `npm test` — existing tests pass (update any test that imported `App` as root to target `AppShell` if needed).
- [ ] **Step 10: Commit** `feat(frontend): vite-react-ssg + react-router; app moved to /app, public landing at /`

---

### Task 2: SEO helpers (Seo.tsx, jsonld.ts) + robots.txt

**Files:**
- Create: `frontend/src/seo/Seo.tsx`, `frontend/src/seo/jsonld.ts`, `frontend/public/robots.txt`, `frontend/src/seo/Seo.test.ts`
- Modify: `frontend/src/pages/Landing.tsx` (use `<Seo>`), `frontend/src/components/AppShell.tsx` (use `<Seo noindex/>`)

**Interfaces:**
- Consumes: vite-react-ssg `Head` (verify import via Context7 — vite-react-ssg re-exports a `Head` component for head tags).
- Produces: `Seo({title, description, path, image?, noindex?, jsonLd?})` → renders `<Head>` with `<title>`, meta description, canonical (`https://destinyopt.com` + path), OG + Twitter tags, optional `<meta name="robots" content="noindex,nofollow">`, optional `<script type="application/ld+json">`. `jsonld.ts`: `websiteJsonLd()` and `weaponJsonLd(weapon)` returning plain objects.

- [ ] **Step 1: Verify `Head` usage** via Context7 (query "Head component for per-page title and meta tags").
- [ ] **Step 2: Write failing test** `Seo.test.ts` — since `<Head>` side-effects are hard to assert in jsdom, test the PURE helpers: `canonicalUrl(path)` returns `https://destinyopt.com/weapons/x` (no double slash); `jsonld.websiteJsonLd()` has `@type: "WebSite"` + url; `weaponJsonLd({name:"Foo",...})` has `@type` and `name: "Foo"`. Put `canonicalUrl` in `seo/Seo.tsx` (exported) or a `seo/url.ts`.
- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement** `seo/url.ts` (`canonicalUrl`), `jsonld.ts`, and `Seo.tsx` (uses `<Head>` + `canonicalUrl` + emits the JSON-LD script when `jsonLd` provided). Create `public/robots.txt` exactly:
```
User-agent: *
Allow: /
Disallow: /app
Disallow: /api
Sitemap: https://destinyopt.com/sitemap.xml
```
Wire `<Seo title=... description=... path="/" jsonLd={websiteJsonLd()} />` into Landing; `<Seo noindex title="Destiny Advisor" description="" path="/app" />` into AppShell.
- [ ] **Step 5: Run → PASS** (`npm test`), `npm run build`, verify `dist/index.html` contains `<title>` + canonical link + og tags, and `dist/robots.txt` exists with `Disallow: /app`.
- [ ] **Step 6: Commit** `feat(seo): Seo/JSON-LD helpers + robots.txt; landing meta, /app noindex`

---

### Task 3: Build-time content generator + fixture

**Files:**
- Create: `scripts/build_content.mjs`, `frontend/src/content/__fixtures__/manifest.sample.json`, `scripts/build_content.test.mjs`
- Modify: repo `.gitignore` (ignore `frontend/src/content/` except `__fixtures__/`)

**Interfaces:**
- Produces (ESM exports from `build_content.mjs`): `slugify(name, hash)`, `weaponsFromManifest(itemDefs, statDefs, ratingsSeed) -> { index: [{slug,name,type,element}], weapons: { [slug]: {slug,name,type,element,ammoType,frame,stats,perks:[{name,description,rating}],godRoll:[...]} } }`, and `async generate({ fetchManifest, ratingsSeed, outDir, limit })` that writes `weapons-index.json` + `weapons/<slug>.json`. `fetchManifest` is injectable (real Bungie fetch in `_main`, fixture in tests).

- [ ] **Step 1: Create the fixture** `manifest.sample.json` — a tiny hand-made manifest slice: 2-3 weapon item defs (`itemType:3`, displayProperties.name, stats, sockets/perks) + a couple stat defs + a few perk entries, enough to exercise `weaponsFromManifest`. (Shape it to match the real Bungie manifest keys the generator reads.)
- [ ] **Step 2: Write failing test** `build_content.test.mjs` (node:test or vitest): `slugify("The Messenger", "ab12") === "the-messenger-ab12"`; `weaponsFromManifest(fixture...)` returns an index whose length == number of weapon defs, each with slug/name/type/element, and a `weapons[slug]` with `perks` carrying ratings derived from the ratings seed (use a small seed in the test); two weapons with the same name get distinct slugs (hash suffix).
- [ ] **Step 3: Run → FAIL.**
- [ ] **Step 4: Implement** `build_content.mjs`: pure `slugify` (kebab + short stable hash of the item hash), `weaponsFromManifest` (filter itemType==3 + named + non-redacted; map stats via statDefs; derive perk list + ratings/godRoll from the seed by perk name), and `generate(...)` (calls `weaponsFromManifest`, writes JSON files, respects `limit` for the slice, `log`s the count written). Add `_main()` that fetches the real manifest using `BUNGIE_API_KEY` (env) — `GET https://www.bungie.net/Platform/Destiny2/Manifest/` then the en `DestinyInventoryItemDefinition` + `DestinyStatDefinition` — reads `../backend/app/data/perk_ratings_seed.json`, and writes to `frontend/src/content/` with a default `limit` (e.g. 12) for the vertical slice. Errors loudly if the fetch fails or the key is missing.
- [ ] **Step 5: Run → PASS.** Add `.gitignore` entries: `frontend/src/content/` then `!frontend/src/content/__fixtures__/`.
- [ ] **Step 6: Commit** `feat(content): build-time Bungie-manifest content generator + fixture`

---

### Task 4: Weapon page vertical slice (/weapons/:slug)

**Files:**
- Create: `frontend/src/pages/WeaponPage.tsx`
- Modify: `frontend/src/routes.tsx` (add the dynamic child route), and ensure content exists for the build (run `node scripts/build_content.mjs` against the fixture or real manifest before building)
- Test: build smoke in steps

**Interfaces:**
- Consumes: generated `frontend/src/content/weapons-index.json` + `weapons/<slug>.json`; `Seo`, `weaponJsonLd`.
- Produces: `/weapons/:slug` route with `getStaticPaths` + `loader`.

- [ ] **Step 1: Verify** `getStaticPaths` + `loader` + `useLoaderData` shape for vite-react-ssg via Context7.
- [ ] **Step 2: Add the route** to `routes.tsx` children:
```tsx
{
  path: 'weapons/:slug',
  lazy: () => import('./pages/WeaponPage'),
  getStaticPaths: async () => {
    const index = (await import('./content/weapons-index.json')).default as Array<{slug:string}>
    return index.map(w => `weapons/${w.slug}`)
  },
},
```
- [ ] **Step 3: Implement `WeaponPage.tsx`** — exports `Component` (default) + `loader`. `loader({ params })` (guard `if (!import.meta.ssr) {}` as needed) reads `weapons/<slug>.json` and returns the weapon object; the component uses `useLoaderData()` to render name (h1), type/element, a stats list, a perks list (name + rating), and the recommended god-roll, wrapped with `<Seo title={`${name} god roll & perks`} description=... path={`/weapons/${slug}`} jsonLd={weaponJsonLd(weapon)} />`. Unknown slug → a simple "Weapon not found" render. (SponsoredAds already renders via PublicLayout.)
- [ ] **Step 4: Generate content + build + verify** — `node scripts/build_content.mjs` (or against the fixture), then `npm run build`. Assert a real generated slug prerendered: pick the first slug from `weapons-index.json`, then `test -f "dist/weapons/<slug>/index.html"` and `grep` the weapon name + `<title>` in it.
- [ ] **Step 5: Run** `npm test` (no regression).
- [ ] **Step 6: Commit** `feat(seo): prerendered /weapons/:slug page (vertical slice)`

---

### Task 5: Sitemap generator + build pipeline + build-smoke test

**Files:**
- Create: `scripts/gen_sitemap.mjs`, `scripts/gen_sitemap.test.mjs`
- Modify: `frontend/package.json` (build pipeline scripts)

**Interfaces:**
- Produces: `sitemapXml(paths: string[]) -> string` (pure) and a `_main()` that scans `dist/` for `index.html` files, derives public URL paths (exclude `/app`), and writes `dist/sitemap.xml`.

- [ ] **Step 1: Write failing test** `gen_sitemap.test.mjs`: `sitemapXml(["/", "/weapons/foo-ab12"])` returns XML containing `<loc>https://destinyopt.com/</loc>` and `<loc>https://destinyopt.com/weapons/foo-ab12</loc>`, a valid `<urlset xmlns=...>` wrapper, and does NOT contain `/app`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `gen_sitemap.mjs` (pure `sitemapXml` + `_main` walking `dist/` for `**/index.html` → path, filter out `/app`, write `dist/sitemap.xml`). Wire `frontend/package.json` scripts:
  - `"build": "node ../../scripts/build_content.mjs && vite-react-ssg build && node ../../scripts/gen_sitemap.mjs"` (adjust relative paths to where scripts live; scripts are at repo `scripts/`).
  - keep `"dev": "vite"`, `"test": "vitest run"`.
  (Confirm the vite-react-ssg build command name via Context7/its package bin.)
- [ ] **Step 4: Full build + smoke assertions** — `cd frontend && npm run build`, then assert: `dist/index.html`, `dist/weapons/<slug>/index.html`, `dist/robots.txt` (with `Disallow: /app`), `dist/sitemap.xml` (lists `/` and the weapon URL, excludes `/app`) all present/correct. Capture these as a shell smoke check (and/or a `scripts/gen_sitemap.test.mjs` covers the pure part).
- [ ] **Step 5: Run** `npm test` (all green) + confirm backend pytest unaffected.
- [ ] **Step 6: Commit** `feat(seo): sitemap generator + content→SSG→sitemap build pipeline`

---

## Self-Review

**Spec coverage:**
- §3 architecture / route split (ViteReactSSG, routes, /app excluded) → Task 1. ✓
- §4 technical SEO (Head/meta/canonical/OG, robots, sitemap, JSON-LD, /app noindex) → Tasks 2 (head/robots/jsonld/noindex) + 5 (sitemap). ✓
- §5 content data layer (generator, weapons-index, per-weapon, getStaticPaths, loader) → Tasks 3 + 4. ✓
- §6 components → Tasks 1–5 (all files mapped). ✓
- §7 error handling (build fails on manifest error/missing key; unknown slug not-found; /app noindex) → Tasks 3 (loud fail) + 4 (not found) + 2 (noindex). ✓
- §8 testing (generator, SEO helpers, build smoke, route split, regression) → tests in Tasks 2,3,5 + build smokes in 1,4,5. ✓
- §9 rollout (git-ignore content, build pipeline; D wires serving) → Tasks 3 (gitignore) + 5 (pipeline). ✓

**Placeholder scan:** No TBD/TODO. SSG-API specifics are flagged for Context7 verification (the toolchain's exact import/CLI names can shift by version — this is a deliberate verify-step, not a content gap); core code (routes, main entry, robots, sitemapXml, generator interfaces, weapon route) is concrete.

**Type consistency:** `routes`/`createRoot`/`RouteRecord` consistent (Tasks 1,4). `weaponsFromManifest`/`generate`/`slugify` signatures consistent (Tasks 3,4). `Seo`/`canonicalUrl`/`weaponJsonLd`/`websiteJsonLd` consistent (Tasks 2,4). `sitemapXml` consistent (Task 5). Content file paths (`weapons-index.json`, `weapons/<slug>.json`) consistent (Tasks 3,4,5).

**Toolchain-risk note (non-blocking):** vite-react-ssg's exact entry/CLI/Head API can vary by version; each SSG task starts with a Context7 verification step so implementers code against the installed version, not assumptions.
