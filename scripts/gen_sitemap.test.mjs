import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { sitemapXml, distPathsToUrls } from './gen_sitemap.mjs';

describe('sitemapXml', () => {
  test('contains urlset wrapper with correct xmlns', () => {
    const xml = sitemapXml(['/']);
    assert.ok(
      xml.includes('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'),
      'must have urlset xmlns wrapper'
    );
    assert.ok(xml.includes('</urlset>'), 'must close urlset');
  });

  test('contains xml declaration', () => {
    const xml = sitemapXml(['/']);
    assert.ok(
      xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>'),
      'must start with xml declaration'
    );
  });

  test('produces correct loc for root path', () => {
    const xml = sitemapXml(['/']);
    assert.ok(
      xml.includes('<loc>https://destinyopt.com/</loc>'),
      'root / must map to https://destinyopt.com/'
    );
  });

  test('produces correct loc for weapon path', () => {
    const xml = sitemapXml(['/weapons/foo-ab12']);
    assert.ok(
      xml.includes('<loc>https://destinyopt.com/weapons/foo-ab12</loc>'),
      'weapon path must have correct loc'
    );
  });

  test('handles multiple paths', () => {
    const xml = sitemapXml(['/', '/weapons/foo-ab12']);
    assert.ok(xml.includes('<loc>https://destinyopt.com/</loc>'));
    assert.ok(xml.includes('<loc>https://destinyopt.com/weapons/foo-ab12</loc>'));
  });

  test('does not produce double slashes', () => {
    const xml = sitemapXml(['/weapons/foo']);
    assert.ok(!xml.includes('//weapons'), 'must not have double slash before path');
  });

  test('does not contain /app', () => {
    const xml = sitemapXml(['/', '/weapons/foo-ab12']);
    assert.ok(!xml.includes('/app'), 'sitemap must not reference /app');
  });
});

describe('distPathsToUrls', () => {
  test('index.html maps to /', () => {
    const urls = distPathsToUrls(['index.html']);
    assert.deepEqual(urls, ['/']);
  });

  test('weapon html maps to /weapons/<slug> (no .html)', () => {
    const urls = distPathsToUrls(['weapons/foo-ab12.html']);
    assert.deepEqual(urls, ['/weapons/foo-ab12']);
  });

  test('app.html is excluded', () => {
    const urls = distPathsToUrls(['index.html', 'app.html']);
    assert.ok(!urls.includes('/app'), 'app.html must be excluded');
    assert.deepEqual(urls, ['/']);
  });

  test('app/ directory entries are excluded', () => {
    const urls = distPathsToUrls(['index.html', 'app/x.html']);
    assert.ok(!urls.some(u => u.startsWith('/app')), 'app/ paths must be excluded');
    assert.deepEqual(urls, ['/']);
  });

  test('404.html is excluded', () => {
    const urls = distPathsToUrls(['index.html', '404.html']);
    assert.ok(!urls.includes('/404'), '404.html must be excluded');
    assert.deepEqual(urls, ['/']);
  });

  test('200.html is excluded', () => {
    const urls = distPathsToUrls(['index.html', '200.html']);
    assert.ok(!urls.includes('/200'), '200.html must be excluded');
    assert.deepEqual(urls, ['/']);
  });

  test('full mix returns sorted unique paths', () => {
    const urls = distPathsToUrls([
      'index.html',
      'weapons/foo-ab12.html',
      'app.html',
      'app/x.html',
      '404.html',
    ]);
    assert.deepEqual(urls, ['/', '/weapons/foo-ab12']);
  });

  test('results are sorted', () => {
    const urls = distPathsToUrls([
      'weapons/zzz-0000.html',
      'weapons/aaa-1111.html',
      'index.html',
    ]);
    assert.deepEqual(urls, ['/', '/weapons/aaa-1111', '/weapons/zzz-0000']);
  });

  test('results are unique (deduped)', () => {
    const urls = distPathsToUrls(['index.html', 'index.html', 'weapons/foo.html']);
    const unique = [...new Set(urls)];
    assert.deepEqual(urls, unique);
  });
});
