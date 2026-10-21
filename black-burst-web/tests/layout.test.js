import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  counterLabels,
  counterLayout,
  counterPads,
  markBox,
  markVariant,
  MONOGRAM_ASPECT,
  regionBoxes,
  relativeLuminance,
} from '../js/layout.js';
import { frameAt } from '../js/timing.js';

// A stand-in font: fixed-width characters, roughly the proportions of a sans-serif.
const measure = (text, size) => ({ width: 0.58 * size * text.length, ascent: 0.97 * size, descent: 0.23 * size });

test('region boxes match the desktop app at 1920x1080', () => {
  assert.deepEqual(regionBoxes(1920, 1080, 0.25, 0.04), [
    [77, 77, 613, 346],
    [691, 77, 1228, 346],
    [1306, 77, 1842, 346],
  ]);
});

test('regions are equal, evenly spaced, and symmetric', () => {
  const boxes = regionBoxes(3840, 2160, 0.3, 0.05);
  const widths = boxes.map(([left, , right]) => right - left);
  const gaps = [boxes[1][0] - boxes[0][2], boxes[2][0] - boxes[1][2]];
  assert.ok(Math.max(...widths) - Math.min(...widths) <= 1);
  assert.ok(Math.abs(gaps[0] - gaps[1]) <= 1);
  assert.ok(Math.abs(boxes[0][0] - (3840 - 1 - boxes[2][2])) <= 2);
});

test('counters fit inside the canvas, below the regions', () => {
  for (const [width, height, textSize] of [[1920, 1080, 0.12], [108, 192, 0.3], [640, 480, 0.4]]) {
    const boxes = regionBoxes(width, height, 0.25, 0.04);
    const pads = { framePad: 4, secondPad: 2 };
    const layout = counterLayout({ width, height, textSize, boxes, pads, measure });
    const [frameLine, secondLine] = layout.lines;
    const lineHeight = 1.2 * layout.fontSize;
    for (const line of layout.lines) {
      assert.ok(line.x >= 0 && line.x + line.width <= width, `fits ${width}x${height}`);
    }
    assert.ok(frameLine.y - lineHeight / 2 > Math.max(...boxes.map((box) => box[3])));
    assert.ok(secondLine.y + lineHeight / 2 <= height);
  }
});

test('digit cells are as wide as the widest digit in a proportional font', () => {
  // Like the brand font: "1" is narrow, "4" is the widest digit.
  const advances = { 0: 0.67, 1: 0.38, 2: 0.58, 3: 0.58, 4: 0.68, 5: 0.58, 6: 0.63, 7: 0.61, 8: 0.65, 9: 0.63 };
  const proportional = (text, size) => ({
    width: [...text].reduce((sum, ch) => sum + (advances[ch] ?? 0.6) * size, 0),
    ascent: 0.97 * size,
    descent: 0.23 * size,
  });
  const boxes = regionBoxes(1920, 1080, 0.25, 0.04);
  const layout = counterLayout({
    width: 1920, height: 1080, textSize: 0.12, boxes, pads: { framePad: 4, secondPad: 2 }, measure: proportional,
  });
  assert.equal(layout.digitWidth, 0.68 * layout.fontSize);
  const [frameLine] = layout.lines;
  assert.equal(frameLine.width, frameLine.prefixWidth + 4 * layout.digitWidth);
  assert.equal(frameLine.x, (1920 - frameLine.width) / 2); // centred once, never moves
});

test('the default counter is 12% of the canvas height when it fits', () => {
  const boxes = regionBoxes(1920, 1080, 0.25, 0.04);
  const layout = counterLayout({
    width: 1920, height: 1080, textSize: 0.12, boxes, pads: { framePad: 4, secondPad: 2 }, measure,
  });
  assert.equal(layout.fontSize, 130);
});

test('labels pad to the widest number and honour the start number', () => {
  const pads = counterPads(300, 30, 0);
  assert.deepEqual(pads, { framePad: 4, secondPad: 2 });
  assert.deepEqual(counterLabels(frameAt(0, 30), 0, pads), ['FRAME 0000', 'SECOND 00']);
  assert.deepEqual(counterLabels(frameAt(45, 30), 0, pads), ['FRAME 0045', 'SECOND 01']);
  assert.deepEqual(counterLabels(frameAt(0, 30), 1, counterPads(300, 30, 1)), ['FRAME 0001', 'SECOND 01']);
  assert.deepEqual(counterPads(108000, 30, 0), { framePad: 6, secondPad: 4 });
});

test('the Morph monogram sits bottom-right at a twentieth of the width, like the desktop app', () => {
  assert.deepEqual(markBox(1920, 1080), { x: 1792, y: 977, w: 96, h: 71 });
  const uhd = markBox(3840, 2160);
  assert.deepEqual([uhd.w, 3840 - uhd.x - uhd.w, 2160 - uhd.y - uhd.h], [192, 65, 65]);
  const wide = markBox(3840, 540);
  assert.ok(wide.h <= Math.round(0.08 * 540));
  assert.ok(Math.abs(wide.h / wide.w - MONOGRAM_ASPECT) / MONOGRAM_ASPECT < 0.03);
});

test('the monogram variant gives the M more contrast with the pixels behind it', () => {
  const solid = ([r, g, b]) => Uint8ClampedArray.from({ length: 64 * 4 }, (_, i) => [r, g, b, 255][i % 4]);
  const cases = [
    [[0, 0, 0], 'dark'], // white M on black
    [[255, 255, 255], 'light'], // black M on white
    [[230, 220, 30], 'light'], // yellow is bright
    [[30, 40, 220], 'dark'], // blue is dark
    [[128, 128, 128], 'light'], // mid grey sits just above the crossover
    [[100, 100, 100], 'dark'],
  ];
  for (const [rgb, expected] of cases) {
    assert.equal(markVariant(relativeLuminance(solid(rgb))), expected, `rgb(${rgb})`);
  }
});

test('luminance is the mean over every pixel and ignores alpha', () => {
  assert.equal(relativeLuminance(Uint8ClampedArray.of(0, 0, 0, 255)), 0);
  assert.equal(relativeLuminance(Uint8ClampedArray.of(255, 255, 255, 0)), 1);
  const half = Uint8ClampedArray.of(0, 0, 0, 255, 255, 255, 255, 255);
  assert.ok(Math.abs(relativeLuminance(half) - 0.5) < 1e-12);
  assert.equal(relativeLuminance(new Uint8ClampedArray(0)), 0);
});

test('the counters stay above the mark, even at the largest size', () => {
  const boxes = regionBoxes(1920, 1080, 0.25, 0.04);
  const mark = markBox(1920, 1080);
  const layout = counterLayout({
    width: 1920, height: 1080, textSize: 0.4, boxes, pads: { framePad: 4, secondPad: 2 },
    measure, bottomLimit: mark.y,
  });
  for (const line of layout.lines) assert.ok(line.y + (1.2 * layout.fontSize) / 2 <= mark.y);
});
