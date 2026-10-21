import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  fpsFraction,
  frameAt,
  frameFilePad,
  framesPerSecond,
  regionSplit,
  roundHalfEven,
  totalFrames,
} from '../js/timing.js';

test('rounding matches Python: exact halves go to the even neighbour', () => {
  assert.deepEqual([0.5, 1.5, 2.5, 12.5, -2.5, 2.4, 2.6].map(roundHalfEven), [0, 2, 2, 12, -2, 2, 3]);
});

test('a second is round(fps) whole frames, like timecode', () => {
  assert.equal(framesPerSecond(29.97), 30);
  assert.equal(framesPerSecond(23.976), 24);
  assert.equal(framesPerSecond(25), 25);
  assert.equal(frameAt(30, 29.97).second, 1);
});

test('regions cycle red, green, blue in thirds at 30 fps', () => {
  const regions = Array.from({ length: 30 }, (_, i) => frameAt(i, 30).region);
  assert.deepEqual(regions, [...Array(10).fill(0), ...Array(10).fill(1), ...Array(10).fill(2)]);
});

test('uneven frame rates give the spare frames to the earlier colours', () => {
  assert.deepEqual(regionSplit(30), [10, 10, 10]);
  assert.deepEqual(regionSplit(24), [8, 8, 8]);
  assert.deepEqual(regionSplit(25), [9, 8, 8]);
  assert.deepEqual(regionSplit(60), [20, 20, 20]);
  assert.deepEqual(regionSplit(29.97), [10, 10, 10]);
});

test('the background alternates black and white each second', () => {
  assert.deepEqual([0, 29, 30, 59, 60].map((i) => frameAt(i, 30).white),
    [false, false, true, true, false]);
});

test('frame counts and file-name padding match the desktop app', () => {
  assert.equal(totalFrames(10, 30), 300);
  assert.equal(totalFrames(0.5, 25), 12); // 12.5 rounds to even
  assert.equal(totalFrames(0.01, 30), 1);
  assert.equal(frameFilePad(300), 4);
  assert.equal(frameFilePad(99999, 1), 6);
});

test('frame rates become exact fractions, snapping NTSC rates', () => {
  assert.deepEqual(fpsFraction(29.97), { num: 30000, den: 1001 });
  assert.deepEqual(fpsFraction(23.976), { num: 24000, den: 1001 });
  assert.deepEqual(fpsFraction(59.94), { num: 60000, den: 1001 });
  assert.deepEqual(fpsFraction(25), { num: 25, den: 1 });
  assert.deepEqual(fpsFraction(23.5), { num: 47, den: 2 });
  assert.deepEqual(fpsFraction(12.5), { num: 25, den: 2 });
});
