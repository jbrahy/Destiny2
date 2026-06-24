import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { slugify, weaponsFromManifest, generate } from './build_content.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

// Load the fixture
const fixturePath = path.join(
  REPO_ROOT,
  'destiny-weapon-advisor/frontend/src/content/__fixtures__/manifest.sample.json'
);
const fixture = JSON.parse(readFileSync(fixturePath, 'utf-8'));

// Small inline ratings seed for tests (only what the fixture weapons need)
const TEST_SEED = {
  'Outlaw': { rating: 'A', reason: 'Fast reload on precision kills.' },
  'Kill Clip': { rating: 'A', reason: 'Big damage on reload-after-kill.' },
  'Rapid Hit': { rating: 'A', reason: 'Reload + stability on precision hits.' },
  'Vorpal Weapon': { rating: 'B', reason: 'Damage vs bosses.' },
  'Opening Shot': { rating: 'A', reason: 'First-shot accuracy.' },
  'Incandescent': { rating: 'S', reason: 'Scorch/ignition AoE on kills.' },
};

describe('slugify', () => {
  test('basic kebab + hash suffix', () => {
    assert.equal(slugify('The Messenger', 'ab12'), 'the-messenger-ab12');
  });

  test('strips special characters', () => {
    const s = slugify("Hung Jury SR4", 'ff00');
    assert.equal(s, 'hung-jury-sr4-ff00');
  });

  test('collapses multiple spaces/hyphens', () => {
    const s = slugify('  Wild Card  ', '1234');
    assert.equal(s, 'wild-card-1234');
  });

  test('handles apostrophes and punctuation', () => {
    const s = slugify("D.A.R.C.I.", 'cafe');
    assert.equal(s, 'darci-cafe');
  });
});

describe('weaponsFromManifest – filtering', () => {
  const { index, weapons } = weaponsFromManifest(
    fixture.itemDefs,
    fixture.statDefs,
    TEST_SEED
  );

  test('only weapon itemType===3 entries appear in index', () => {
    // fixture has 3 named non-redacted weapons + 1 unnamed + 1 redacted + 2 non-weapons
    // expected: 3 (The Messenger x2 + Igneous Hammer)
    assert.equal(index.length, 3);
  });

  test('non-weapon defs are excluded', () => {
    const names = index.map(e => e.name);
    assert.ok(!names.includes('Helm of Saint-14'), 'armor must be excluded');
    assert.ok(!names.includes('Ghost Shell'), 'non-weapon must be excluded');
  });

  test('unnamed weapons are excluded', () => {
    // hash 4444444444 has empty name
    const slugs = Object.keys(weapons);
    const hasUnnamed = slugs.some(s => weapons[s].name === '');
    assert.ok(!hasUnnamed, 'unnamed weapon must be filtered');
  });

  test('redacted weapons are excluded', () => {
    const names = index.map(e => e.name);
    // hash 5555555555 is redacted
    assert.ok(!names.includes('Redacted') || index.every(e => !fixture.itemDefs[Object.keys(fixture.itemDefs).find(k => fixture.itemDefs[k].name === e.name)]?.redacted));
    const slugs = Object.keys(weapons);
    for (const slug of slugs) {
      assert.ok(!weapons[slug].redacted, 'redacted weapon must not appear');
    }
  });
});

describe('weaponsFromManifest – shape', () => {
  const { index, weapons } = weaponsFromManifest(
    fixture.itemDefs,
    fixture.statDefs,
    TEST_SEED
  );

  test('each index entry has required fields', () => {
    for (const entry of index) {
      assert.ok(entry.slug, `entry missing slug: ${JSON.stringify(entry)}`);
      assert.ok(entry.name, `entry missing name: ${JSON.stringify(entry)}`);
      assert.ok(entry.type, `entry missing type: ${JSON.stringify(entry)}`);
      assert.ok(entry.element !== undefined, `entry missing element: ${JSON.stringify(entry)}`);
    }
  });

  test('weapons map matches index slugs', () => {
    for (const entry of index) {
      assert.ok(weapons[entry.slug], `weapons map missing slug ${entry.slug}`);
    }
    assert.equal(Object.keys(weapons).length, index.length);
  });

  test('each weapon has full shape', () => {
    for (const [slug, w] of Object.entries(weapons)) {
      assert.ok(w.slug === slug, 'weapon slug mismatch');
      assert.ok(w.name, `weapon ${slug} missing name`);
      assert.ok(w.type, `weapon ${slug} missing type`);
      assert.ok(w.element !== undefined, `weapon ${slug} missing element`);
      assert.ok(w.ammoType !== undefined, `weapon ${slug} missing ammoType`);
      assert.ok(w.frame !== undefined, `weapon ${slug} missing frame`);
      assert.ok(Array.isArray(w.stats), `weapon ${slug} stats must be array`);
      assert.ok(Array.isArray(w.perks), `weapon ${slug} perks must be array`);
      assert.ok(Array.isArray(w.godRoll), `weapon ${slug} godRoll must be array`);
    }
  });
});

describe('weaponsFromManifest – duplicate name slug disambiguation', () => {
  const { index, weapons } = weaponsFromManifest(
    fixture.itemDefs,
    fixture.statDefs,
    TEST_SEED
  );

  test('two weapons with same name get distinct slugs', () => {
    const messengerEntries = index.filter(e => e.name === 'The Messenger');
    assert.equal(messengerEntries.length, 2, 'should have 2 Messenger entries');
    const slugs = messengerEntries.map(e => e.slug);
    assert.notEqual(slugs[0], slugs[1], 'slugs must differ');
  });
});

describe('weaponsFromManifest – perks and ratings', () => {
  const { weapons } = weaponsFromManifest(
    fixture.itemDefs,
    fixture.statDefs,
    TEST_SEED
  );

  test('perks carry name, description, rating from seed', () => {
    // Find Igneous Hammer (has Incandescent=S)
    const hammer = Object.values(weapons).find(w => w.name === 'Igneous Hammer');
    assert.ok(hammer, 'Igneous Hammer must exist');
    const incandescent = hammer.perks.find(p => p.name === 'Incandescent');
    assert.ok(incandescent, 'Incandescent perk must appear');
    assert.equal(incandescent.rating, 'S');
    assert.ok(typeof incandescent.description === 'string');
  });

  test('godRoll contains top-rated perk names (S or A)', () => {
    const hammer = Object.values(weapons).find(w => w.name === 'Igneous Hammer');
    assert.ok(hammer.godRoll.length > 0, 'godRoll must not be empty');
    assert.ok(hammer.godRoll.includes('Incandescent'), 'S-tier Incandescent must be in godRoll');
  });

  test('perks not in seed get rating undefined or empty', () => {
    // No seed entry for a missing perk name
    const { weapons: w2 } = weaponsFromManifest(
      fixture.itemDefs,
      fixture.statDefs,
      {} // empty seed
    );
    for (const weapon of Object.values(w2)) {
      for (const perk of weapon.perks) {
        assert.ok(
          perk.rating === undefined || perk.rating === '',
          `perk ${perk.name} should have no rating with empty seed`
        );
      }
    }
  });
});

describe('weaponsFromManifest – stats', () => {
  const { weapons } = weaponsFromManifest(
    fixture.itemDefs,
    fixture.statDefs,
    TEST_SEED
  );

  test('stats are named via statDefs', () => {
    const hammer = Object.values(weapons).find(w => w.name === 'Igneous Hammer');
    const statNames = hammer.stats.map(s => s.name);
    assert.ok(statNames.includes('Range'), 'Range stat must be present');
    assert.ok(statNames.includes('Stability'), 'Stability stat must be present');
  });
});

describe('generate', () => {
  test('writes index + per-weapon files and returns count', async () => {
    const { mkdtempSync, rmSync } = await import('node:fs');
    const os = await import('node:os');
    const tmpDir = mkdtempSync(path.join(os.tmpdir(), 'destiny-test-'));
    try {
      const fetchManifest = async () => ({
        itemDefs: fixture.itemDefs,
        statDefs: fixture.statDefs,
      });
      const result = await generate({
        fetchManifest,
        ratingsSeed: TEST_SEED,
        outDir: tmpDir,
        limit: 2,
      });
      assert.equal(result.count, 2, 'limit=2 should write 2 weapons');

      const { existsSync } = await import('node:fs');
      assert.ok(existsSync(path.join(tmpDir, 'weapons-index.json')), 'weapons-index.json must exist');
      assert.ok(existsSync(path.join(tmpDir, 'weapons')), 'weapons/ dir must exist');

      const indexData = JSON.parse(readFileSync(path.join(tmpDir, 'weapons-index.json'), 'utf-8'));
      assert.equal(indexData.length, 2, 'index file must have 2 entries');

      // Each weapon file should exist
      for (const entry of indexData) {
        const weaponFile = path.join(tmpDir, 'weapons', `${entry.slug}.json`);
        assert.ok(existsSync(weaponFile), `weapon file ${entry.slug}.json must exist`);
      }
    } finally {
      rmSync(tmpDir, { recursive: true });
    }
  });
});
