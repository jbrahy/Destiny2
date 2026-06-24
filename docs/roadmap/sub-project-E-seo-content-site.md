# Sub-project E — SEO Public Content Site (charter)

**Status:** Chartered (not yet brainstormed). Build order: after **B** (ad system), before **D** (deploy).
**Decided 2026-06-23.**

## Why
The Destiny Advisor app is private/per-user behind Bungie OAuth and must stay `noindex`. SEO value comes from a **public, crawlable content surface** that ranks in search, drives organic traffic, and is monetized by the sub-project B ad unit.

## Decisions locked
- **Scope: full public content site** — many guide types, on-site search, internal linking. A multi-phase program; will get its own decomposition + spec(s) + plan(s) at brainstorm time.
- **Rendering: prerender public routes (SSG)** — keep the existing Vite SPA for the private app; add a static-prerender/SSG step that emits crawlable HTML for the public content routes only. No SSR/Next.js rewrite.
- **Sequencing:** finish B first (ads ship with the content so traffic is monetized day one), then E, then D deploys everything.

## Likely components (to refine when brainstormed)
- **Technical SEO:** per-route `<title>`/meta description, Open Graph/Twitter cards, canonical URLs, `robots.txt`, `sitemap.xml`, JSON-LD structured data, semantic HTML, Core Web Vitals/perf, mobile-friendly.
- **Public content engine (the traffic magnet):** indexable god-roll / perk-rating database, weapon pages, activity loadout guides — generated from the Bungie manifest + default (non-user) perk ratings. On-site search + internal linking between related pages.
- **Privacy boundary:** the authenticated app routes stay `noindex`/disallowed; only the generated public content is crawlable.
- **Serving (coordinates with D):** serve prerendered HTML for public routes with correct status codes/canonicals at destinyopt.com.

## Dependencies
- Consumes the Bungie manifest + default perk-rating seed (from A).
- Renders the sub-project B `<SponsoredAds>` unit on public content pages (monetization).
- Deployed/served via sub-project D.
