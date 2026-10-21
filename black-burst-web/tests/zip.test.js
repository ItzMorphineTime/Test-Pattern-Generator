import assert from 'node:assert/strict';
import { test } from 'node:test';

import { crc32, ZipWriter } from '../js/zip.js';

test('crc32 matches the standard check value', () => {
  assert.equal(crc32(new TextEncoder().encode('123456789')), 0xcbf43926);
});

test('archive has valid local headers, central directory, and end record', async () => {
  const zip = new ZipWriter(new Date(2026, 9, 21, 12, 30, 10));
  zip.add('frame_0000.png', Uint8Array.of(1, 2, 3));
  zip.add('frame_0001.png', Uint8Array.of(4, 5, 6, 7));
  const bytes = new Uint8Array(await zip.finish().arrayBuffer());
  const view = new DataView(bytes.buffer);

  const endAt = bytes.length - 22;
  assert.equal(view.getUint32(endAt, true), 0x06054b50);
  assert.equal(view.getUint16(endAt + 10, true), 2);
  const directorySize = view.getUint32(endAt + 12, true);
  const directoryAt = view.getUint32(endAt + 16, true);
  assert.equal(directoryAt + directorySize, endAt);

  const names = [];
  for (let at = directoryAt, i = 0; i < 2; i++) {
    assert.equal(view.getUint32(at, true), 0x02014b50);
    const crc = view.getUint32(at + 16, true);
    const size = view.getUint32(at + 24, true);
    const nameLength = view.getUint16(at + 28, true);
    const localAt = view.getUint32(at + 42, true);
    names.push(new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLength)));

    assert.equal(view.getUint32(localAt, true), 0x04034b50);
    const dataAt = localAt + 30 + view.getUint16(localAt + 26, true);
    assert.equal(crc32(bytes.subarray(dataAt, dataAt + size)), crc);
    at += 46 + nameLength;
  }
  assert.deepEqual(names, ['frame_0000.png', 'frame_0001.png']);
});
