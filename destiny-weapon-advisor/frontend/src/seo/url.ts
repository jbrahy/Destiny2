export const SITE = "https://destinyopt.com";

/**
 * Returns an absolute canonical URL by joining SITE with path.
 * Guarantees exactly one slash between SITE and path, no trailing double-slash.
 */
export function canonicalUrl(path: string): string {
  const base = SITE.replace(/\/$/, "");
  const normalised = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalised}`;
}
