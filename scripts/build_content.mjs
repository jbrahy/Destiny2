/**
 * build_content.mjs — Build-time Bungie manifest content generator
 *
 * Reads DestinyInventoryItemDefinition + DestinyStatDefinition from Bungie,
 * merges with perk_ratings_seed.json, and writes static JSON content files
 * consumed by the frontend SSG build.
 *
 * Usage (CLI):
 *   BUNGIE_API_KEY=<key> node scripts/build_content.mjs
 *
 * Exports (ESM):
 *   slugify(name, hashSuffix)
 *   weaponsFromManifest(itemDefs, statDefs, ratingsSeed)
 *   generate({ fetchManifest, ratingsSeed, outDir, limit })
 */

import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

// Damage type → element name
const ELEMENT_MAP = {
  1: 'Kinetic',
  2: 'Arc',
  3: 'Solar',
  4: 'Void',
  6: 'Stasis',
  7: 'Strand',
};

const AMMO_MAP = { 1: 'Primary', 2: 'Special', 3: 'Heavy' };

// Ratings that qualify for god roll
const GOD_ROLL_TIERS = new Set(['S', 'A']);

/**
 * Produce a stable, URL-safe slug from a weapon name + a short hash suffix.
 * @param {string} name
 * @param {string} hashSuffix  — a short hex string from the item hash
 * @returns {string}  e.g. "the-messenger-ab12"
 */
export function slugify(name, hashSuffix) {
  const base = name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')   // remove non-alphanumeric except spaces/hyphens
    .trim()
    .replace(/[\s-]+/g, '-');        // collapse spaces/hyphens to single hyphen
  return `${base}-${hashSuffix}`;
}

/**
 * Derive a short 4-char hex suffix from an item hash number.
 * Stable: same hash always produces same suffix.
 * @param {number|string} itemHash
 * @returns {string}
 */
function hashSuffix(itemHash) {
  return createHash('sha1')
    .update(String(itemHash))
    .digest('hex')
    .slice(0, 4);
}

/**
 * Pure transform: manifest item/stat defs → structured weapon content.
 *
 * @param {Object} itemDefs   — keyed by item hash (string or number)
 * @param {Object} statDefs   — keyed by stat hash (string or number)
 * @param {Object} ratingsSeed — keyed by perk name → { rating, reason, ... }
 * @returns {{ index: Array, weapons: Object }}
 */
export function weaponsFromManifest(itemDefs, statDefs, ratingsSeed) {
  const index = [];
  const weapons = {};

  for (const [rawHash, def] of Object.entries(itemDefs)) {
    // Filter: must be a weapon, named, and non-redacted
    if (def.itemType !== 3) continue;
    const name = def.displayProperties?.name;
    if (!name) continue;
    if (def.redacted) continue;

    const suffix = hashSuffix(rawHash);
    const slug = slugify(name, suffix);

    const element = ELEMENT_MAP[def.defaultDamageType] ?? 'Kinetic';
    const ammoType = AMMO_MAP[def.equippingBlock?.ammoType] ?? '';
    const frame = def.itemTypeDisplayName ?? '';

    // Map stats: [{ name, value }]
    const statsRaw = def.stats?.stats ?? {};
    const stats = Object.values(statsRaw)
      .map(({ statHash, value }) => {
        const statDef = statDefs[String(statHash)] ?? statDefs[statHash];
        const statName = statDef?.displayProperties?.name ?? '';
        return { name: statName, value };
      })
      .filter(s => s.name); // drop unnamed stats

    // Derive perk names from def.perkNames (our fixture convention) or
    // sockets.socketEntries (fallback if real Bungie data uses that shape).
    // Real Bungie data encodes plugs inside socketEntries; for this build-time
    // tool we rely on perkNames being pre-resolved (see _main for approach).
    const perkNames = def.perkNames ?? [];

    // Map perks against ratingsSeed
    const perks = perkNames.map(perkName => {
      const seedEntry = ratingsSeed[perkName];
      return {
        name: perkName,
        description: seedEntry?.reason ?? '',
        rating: seedEntry?.rating,
      };
    });

    const godRoll = perks
      .filter(p => GOD_ROLL_TIERS.has(p.rating))
      .map(p => p.name);

    const weapon = {
      slug,
      name,
      type: frame,
      element,
      ammoType,
      frame,
      stats,
      perks,
      godRoll,
    };

    index.push({ slug, name, type: frame, element });
    weapons[slug] = weapon;
  }

  return { index, weapons };
}

/**
 * Async generator: fetches manifest, transforms, writes JSON files.
 *
 * @param {object} opts
 * @param {Function} opts.fetchManifest  — async () => { itemDefs, statDefs }
 * @param {Object}  opts.ratingsSeed
 * @param {string}  opts.outDir          — directory to write into
 * @param {number}  [opts.limit]         — cap number of weapons written (default: no limit)
 * @returns {Promise<{ count: number }>}
 */
export async function generate({ fetchManifest, ratingsSeed, outDir, limit }) {
  const { itemDefs, statDefs } = await fetchManifest();
  const { index, weapons } = weaponsFromManifest(itemDefs, statDefs, ratingsSeed);

  const slicedIndex = typeof limit === 'number' ? index.slice(0, limit) : index;
  const count = slicedIndex.length;

  // mkdir -p outDir/weapons
  await fs.mkdir(path.join(outDir, 'weapons'), { recursive: true });

  // Write weapons-index.json
  await fs.writeFile(
    path.join(outDir, 'weapons-index.json'),
    JSON.stringify(slicedIndex, null, 2),
    'utf-8'
  );

  // Write per-weapon files
  for (const entry of slicedIndex) {
    const weapon = weapons[entry.slug];
    await fs.writeFile(
      path.join(outDir, 'weapons', `${entry.slug}.json`),
      JSON.stringify(weapon, null, 2),
      'utf-8'
    );
  }

  console.log(`Content generated: ${count} weapon(s) written to ${outDir}`);
  return { count };
}

/**
 * CLI entry point — only runs when this file is executed directly.
 * Requires BUNGIE_API_KEY env var.
 */
async function _main() {
  const BUNGIE_API_KEY = process.env.BUNGIE_API_KEY;
  if (!BUNGIE_API_KEY) {
    throw new Error(
      'BUNGIE_API_KEY environment variable is required. ' +
      'Set it in destiny-weapon-advisor/backend/.env and export it before running.'
    );
  }

  const BUNGIE_BASE = 'https://www.bungie.net';
  const headers = { 'X-API-Key': BUNGIE_API_KEY };

  async function fetchManifest() {
    // 1. Fetch manifest metadata
    const metaRes = await fetch(`${BUNGIE_BASE}/Platform/Destiny2/Manifest/`, { headers });
    if (!metaRes.ok) {
      throw new Error(
        `Bungie manifest metadata fetch failed: ${metaRes.status} ${metaRes.statusText}`
      );
    }
    const meta = await metaRes.json();
    const paths = meta?.Response?.jsonWorldComponentContentPaths?.en;
    if (!paths) {
      throw new Error('Bungie manifest response missing jsonWorldComponentContentPaths.en');
    }

    // 2. Fetch DestinyInventoryItemDefinition
    const itemRes = await fetch(`${BUNGIE_BASE}${paths.DestinyInventoryItemDefinition}`, {
      headers,
    });
    if (!itemRes.ok) {
      throw new Error(
        `Bungie item definition fetch failed: ${itemRes.status} ${itemRes.statusText}`
      );
    }
    const itemDefs = await itemRes.json();

    // 3. Fetch DestinyStatDefinition
    const statRes = await fetch(`${BUNGIE_BASE}${paths.DestinyStatDefinition}`, { headers });
    if (!statRes.ok) {
      throw new Error(
        `Bungie stat definition fetch failed: ${statRes.status} ${statRes.statusText}`
      );
    }
    const statDefs = await statRes.json();

    return { itemDefs, statDefs };
  }

  // Load ratings seed
  const seedPath = path.join(
    REPO_ROOT,
    'destiny-weapon-advisor/backend/app/data/perk_ratings_seed.json'
  );
  const rawSeed = await fs.readFile(seedPath, 'utf-8');
  const ratingsSeed = JSON.parse(rawSeed);

  const outDir = path.join(REPO_ROOT, 'destiny-weapon-advisor/frontend/src/content');
  const limit = 12;

  await generate({ fetchManifest, ratingsSeed, outDir, limit });
}

// Run _main only when invoked directly (not when imported)
const isMain =
  process.argv[1] && path.resolve(process.argv[1]) === path.resolve(fileURLToPath(import.meta.url));

if (isMain) {
  _main().catch(err => {
    console.error('build_content error:', err.message);
    process.exit(1);
  });
}
