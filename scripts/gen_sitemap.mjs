/**
 * gen_sitemap.mjs — Sitemap generator for destinyopt.com
 *
 * Walks the vite-react-ssg dist/ output, derives public URL paths from flat
 * .html files, and writes dist/sitemap.xml.
 *
 * Usage (CLI):
 *   node scripts/gen_sitemap.mjs
 *
 * Exports (ESM):
 *   SITE         — canonical origin string
 *   sitemapXml(paths)         — pure: paths[] → XML string
 *   distPathsToUrls(files)    — pure: dist-relative file paths → URL paths[]
 */

import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

export const SITE = 'https://destinyopt.com';

/**
 * Build a valid sitemap XML string from an array of URL paths.
 * Each path must start with "/" (e.g. "/" or "/weapons/foo-ab12").
 *
 * @param {string[]} paths
 * @returns {string}
 */
export function sitemapXml(paths) {
  const locs = paths
    .map(p => {
      // Normalise: remove any accidental double-slash between SITE and path
      const url = p === '/' ? `${SITE}/` : `${SITE}${p.startsWith('/') ? p : '/' + p}`;
      return `  <url><loc>${url}</loc></url>`;
    })
    .join('\n');

  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
    locs +
    '\n</urlset>'
  );
}

/**
 * Map a list of dist-relative html file paths to public URL paths.
 *
 * Rules:
 *  - "index.html"          → "/"
 *  - "weapons/foo.html"    → "/weapons/foo"
 *  - Strip trailing ".html"
 *  - Strip trailing "/index" (nested index.html fallback)
 *  - Exclude anything that starts with "app" (e.g. app.html, app/x.html)
 *  - Exclude "404" and "200" fallback pages
 *
 * @param {string[]} files  — dist-relative paths, e.g. ["index.html","weapons/foo.html"]
 * @returns {string[]}      — sorted unique URL paths
 */
export function distPathsToUrls(files) {
  const seen = new Set();

  for (const file of files) {
    // Normalise separators to forward slash
    const normalised = file.replace(/\\/g, '/');

    // Exclude app paths and fallback pages
    const base = normalised.replace(/\.html$/, '');
    if (base === 'app' || base.startsWith('app/')) continue;
    if (base === '404' || base === '200') continue;

    // Derive URL path
    let urlPath;
    if (base === 'index') {
      urlPath = '/';
    } else {
      urlPath = '/' + base.replace(/\/index$/, '');
    }

    seen.add(urlPath);
  }

  return [...seen].sort((a, b) => a.localeCompare(b));
}

/**
 * CLI entry point — walks dist/ for *.html files and writes sitemap.xml.
 */
async function _main() {
  const distDir = path.join(
    REPO_ROOT,
    'destiny-weapon-advisor/frontend/dist'
  );

  // Recursively collect all .html files relative to distDir
  async function walkHtml(dir, rel = '') {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    const results = [];
    for (const entry of entries) {
      const entryRel = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        results.push(...(await walkHtml(path.join(dir, entry.name), entryRel)));
      } else if (entry.isFile() && entry.name.endsWith('.html')) {
        results.push(entryRel);
      }
    }
    return results;
  }

  const htmlFiles = await walkHtml(distDir);
  const urls = distPathsToUrls(htmlFiles);
  const xml = sitemapXml(urls);

  const outPath = path.join(distDir, 'sitemap.xml');
  await fs.writeFile(outPath, xml, 'utf-8');

  console.log(`Sitemap written: ${urls.length} URL(s) → ${outPath}`);
}

// Run _main only when invoked directly (not when imported)
const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMain) {
  _main().catch(err => {
    console.error('gen_sitemap error:', err.message);
    process.exit(1);
  });
}
