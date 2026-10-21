import assert from 'node:assert/strict';
import { test } from 'node:test';

import { DEFAULTS, fileBase, fromQuery, normalise, summary, toQuery, validate } from '../js/settings.js';

test('normalise fills in defaults and clamps out-of-range values', () => {
  assert.deepEqual(normalise({}), { ...DEFAULTS });
  const settings = normalise({ width: 99999, fps: '29.97', startNumber: 5, duration: 'abc' });
  assert.equal(settings.width, 8192);
  assert.equal(settings.fps, 29.97);
  assert.equal(settings.startNumber, 1);
  assert.equal(settings.duration, DEFAULTS.duration);
});

test('share links keep only the changed settings and round-trip', () => {
  assert.equal(toQuery(DEFAULTS), '');
  const settings = normalise({ ...DEFAULTS, width: 3840, height: 2160, fps: 59.94, regionHeight: 0.3, startNumber: 1 });
  const query = toQuery(settings);
  assert.equal(query, '?w=3840&h=2160&fps=59.94&rh=30&start=1');
  assert.deepEqual(fromQuery(query), settings);
});

test('validation blocks low frame rates and notes odd sizes', () => {
  assert.equal(validate(normalise({ fps: 2 })).errors.length, 1);
  const odd = validate(normalise({ width: 1919 }));
  assert.equal(odd.errors.length, 0);
  assert.equal(odd.notes.length, 1);
  assert.deepEqual(validate(DEFAULTS), { errors: [], notes: [] });
});

test('summary and download names describe the settings', () => {
  assert.equal(summary(DEFAULTS), '300 frames · 10 s · R/G/B shown 10/10/10 frames each second');
  assert.equal(fileBase(normalise({ fps: 29.97, duration: 5 })), 'black_burst_1920x1080_29.97fps_5s');
});
