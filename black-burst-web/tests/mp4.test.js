import assert from 'node:assert/strict';
import { test } from 'node:test';

import { Mp4Writer } from '../js/mp4.js';

const DESCRIPTION = Uint8Array.of(1, 0x64, 0, 0x28, 0xff, 0xe1, 0, 0); // stand-in avcC
const BT709 = { primaries: 'bt709', transfer: 'bt709', matrix: 'bt709', fullRange: false };

// Where child boxes start inside each container we descend into.
const CHILD_OFFSET = { moov: 0, trak: 0, mdia: 0, minf: 0, stbl: 0, dinf: 0, stsd: 8, avc1: 78 };

function boxesIn(bytes, start, end) {
  const view = new DataView(bytes.buffer, bytes.byteOffset);
  const boxes = [];
  for (let at = start; at < end;) {
    const size = view.getUint32(at);
    boxes.push({ type: String.fromCharCode(...bytes.subarray(at + 4, at + 8)), start: at, size, body: at + 8 });
    at += size;
  }
  return boxes;
}

function find(bytes, path) {
  let boxes = boxesIn(bytes, 0, bytes.length);
  let found;
  for (const [depth, type] of path.entries()) {
    found = boxes.find((b) => b.type === type);
    assert.ok(found, `missing ${path.slice(0, depth + 1).join('/')}`);
    if (depth < path.length - 1) {
      boxes = boxesIn(bytes, found.body + CHILD_OFFSET[type], found.start + found.size);
    }
  }
  return found;
}

const STBL = ['moov', 'trak', 'mdia', 'minf', 'stbl'];

/** u32 fields of a full box, after its version/flags word. */
function fields(bytes, box) {
  const view = new DataView(bytes.buffer, bytes.byteOffset);
  const out = [];
  for (let at = box.body + 4; at < box.start + box.size; at += 4) out.push(view.getUint32(at));
  return out;
}

async function build({ fps = 30, count = 65, order = null, colorSpace = BT709 } = {}) {
  const writer = new Mp4Writer({ width: 640, height: 360, fps });
  writer.setDescription(DESCRIPTION);
  if (colorSpace) writer.setColorSpace(colorSpace);
  const presentation = order ?? Array.from({ length: count }, (_, i) => i);
  presentation.forEach((p, i) => {
    const sample = new Uint8Array(10 + (i % 7)).fill(i % 251);
    writer.addSample(sample, i % 30 === 0, p);
  });
  return new Uint8Array(await writer.finish().arrayBuffer());
}

test('fast-start layout with correct sample tables for an in-order stream', async () => {
  const bytes = await build();
  assert.deepEqual(boxesIn(bytes, 0, bytes.length).map((b) => b.type), ['ftyp', 'moov', 'mdat']);

  const mdhd = fields(bytes, find(bytes, ['moov', 'trak', 'mdia', 'mdhd']));
  assert.equal(mdhd[2], 30000); // timescale
  assert.equal(mdhd[3], 65 * 1000); // duration

  assert.deepEqual(fields(bytes, find(bytes, [...STBL, 'stts'])), [1, 65, 1000]);
  assert.deepEqual(fields(bytes, find(bytes, [...STBL, 'stss'])), [3, 1, 31, 61]);
  assert.deepEqual(fields(bytes, find(bytes, [...STBL, 'stsc'])), [2, 1, 30, 1, 3, 5, 1]);

  const stsz = fields(bytes, find(bytes, [...STBL, 'stsz']));
  assert.equal(stsz[1], 65);
  assert.deepEqual(stsz.slice(2, 9), [10, 11, 12, 13, 14, 15, 16]);

  // Each chunk offset points at the first byte of its first sample.
  const [chunkCount, ...offsets] = fields(bytes, find(bytes, [...STBL, 'stco']));
  assert.equal(chunkCount, 3);
  assert.deepEqual(offsets.map((at) => bytes[at]), [0, 30, 60]);
  const mdat = boxesIn(bytes, 0, bytes.length)[2];
  assert.equal(offsets[0], mdat.body);
});

test('an in-order stream has no composition-offset table', async () => {
  const bytes = await build();
  const stbl = find(bytes, STBL);
  const children = boxesIn(bytes, stbl.body, stbl.start + stbl.size).map((b) => b.type);
  assert.deepEqual(children, ['stsd', 'stts', 'stss', 'stsc', 'stsz', 'stco']);
});

test('reordered (B-frame) streams map back to display order with signed offsets', async () => {
  // Decode order I0 P3 B1 B2 P6 B4 B5 -> display offsets in frames: 0 +2 -1 -1 +2 -1 -1
  const bytes = await build({ count: 7, order: [0, 3, 1, 2, 6, 4, 5] });
  const ctts = find(bytes, [...STBL, 'ctts']);
  const view = new DataView(bytes.buffer, bytes.byteOffset);
  assert.equal(bytes[ctts.body], 1); // version 1: signed offsets
  const entries = [];
  const count = view.getUint32(ctts.body + 4);
  for (let i = 0, at = ctts.body + 8; i < count; i++, at += 8) {
    entries.push([view.getUint32(at), view.getInt32(at + 4)]);
  }
  assert.deepEqual(entries, [[1, 0], [1, 2000], [2, -1000], [1, 2000], [2, -1000]]);
  const brands = String.fromCharCode(...bytes.subarray(16, find(bytes, ['ftyp']).size));
  assert.ok(brands.includes('iso6'));
});

test('NTSC rates use the exact 1001 fraction', async () => {
  const bytes = await build({ fps: 29.97, count: 3 });
  assert.equal(fields(bytes, find(bytes, ['moov', 'trak', 'mdia', 'mdhd']))[2], 30000);
  assert.deepEqual(fields(bytes, find(bytes, [...STBL, 'stts'])), [1, 3, 1001]);
});

test('the sample entry carries the encoder config and colour space', async () => {
  const bytes = await build({ count: 1 });
  const avcC = find(bytes, [...STBL, 'stsd', 'avc1', 'avcC']);
  assert.deepEqual([...bytes.subarray(avcC.body, avcC.start + avcC.size)], [...DESCRIPTION]);
  const colr = find(bytes, [...STBL, 'stsd', 'avc1', 'colr']);
  assert.deepEqual([...bytes.subarray(colr.body, colr.start + colr.size)],
    [0x6e, 0x63, 0x6c, 0x78, 0, 1, 0, 1, 0, 1, 0]); // 'nclx', BT.709 x3, limited range

  const noColour = await build({ count: 1, colorSpace: null });
  const avc1 = find(noColour, [...STBL, 'stsd', 'avc1']);
  const inner = boxesIn(noColour, avc1.body + 78, avc1.start + avc1.size).map((b) => b.type);
  assert.deepEqual(inner, ['avcC']);
});

test('refuses streams that cannot be played', () => {
  const writer = new Mp4Writer({ width: 64, height: 64, fps: 30 });
  assert.throws(() => writer.addSample(Uint8Array.of(1), false, 0), /key frame/);
  writer.addSample(Uint8Array.of(1), true, 0);
  assert.throws(() => writer.finish(), /configuration/);
});
