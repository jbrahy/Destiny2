import { SITE } from "./url";

export function websiteJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "Destiny Advisor",
    url: SITE,
  };
}

export function weaponJsonLd(w: { name: string; type?: string; element?: string }) {
  return {
    "@context": "https://schema.org",
    "@type": "ItemPage",
    name: w.name,
    ...(w.type ? { genre: w.type } : {}),
    ...(w.element ? { keywords: w.element } : {}),
  };
}
