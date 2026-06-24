import { SITE, canonicalUrl } from "./url";

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Destiny Advisor",
    url: SITE,
  };
}

export function weaponJsonLd(w: { name: string; slug: string; type?: string; element?: string }) {
  return {
    "@context": "https://schema.org",
    "@type": "ItemPage",
    name: w.name,
    url: canonicalUrl("/weapons/" + w.slug),
    ...(w.type ? { genre: w.type } : {}),
    ...(w.element ? { keywords: w.element } : {}),
  };
}
