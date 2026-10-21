import assert from 'node:assert/strict';
import { test } from 'node:test';

import { counterLabels, counterLayout, counterPads, regionBoxes } from '../js/layout.js';
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
    const frameWidth = measure('FRAME 8888', layout.fontSize).width;
    const lineHeight = 1.2 * layout.fontSize;
    assert.ok(layout.frame.x >= 0 && layout.frame.x + frameWidth <= width, `fits ${width}x${height}`);
    assert.ok(layout.frame.y - lineHeight / 2 > Math.max(...boxes.map((box) => box[3])));
    assert.ok(layout.second.y + lineHeight / 2 <= height);
  }
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
