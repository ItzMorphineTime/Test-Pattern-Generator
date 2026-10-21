/**
 * Minimal ZIP writer. Entries are stored uncompressed: the PNG frames inside
 * are already compressed, so deflating them again would gain nothing.
 * Limited to 65,535 entries and 4 GB (no ZIP64), which a sync test won't reach.
 */

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

export const MAX_ZIP_ENTRIES = 0xffff;
const MAX_OFFSET = 0xffffffff;
const UTF8_NAMES = 0x0800;

export class ZipWriter {
  constructor(date = new Date()) {
    this.parts = [];
    this.entries = [];
    this.offset = 0;
    this.time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1);
    this.date = ((Math.max(1980, date.getFullYear()) - 1980) << 9) |
      ((date.getMonth() + 1) << 5) | date.getDate();
  }

  get size() {
    return this.entries.length;
  }

  add(name, bytes) {
    if (this.entries.length >= MAX_ZIP_ENTRIES) {
      throw new Error(`A ZIP can hold at most ${MAX_ZIP_ENTRIES.toLocaleString('en-US')} files.`);
    }
    const nameBytes = new TextEncoder().encode(name);
    const crc = crc32(bytes);
    const header = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true); // local file header signature
    view.setUint16(4, 20, true); // version needed to extract (2.0)
    view.setUint16(6, UTF8_NAMES, true);
    view.setUint16(8, 0, true); // stored
    view.setUint16(10, this.time, true);
    view.setUint16(12, this.date, true);
    view.setUint32(14, crc, true);
    view.setUint32(18, bytes.length, true); // compressed size
    view.setUint32(22, bytes.length, true); // uncompressed size
    view.setUint16(26, nameBytes.length, true);
    view.setUint16(28, 0, true); // extra field length
    header.set(nameBytes, 30);

    this.entries.push({ nameBytes, crc, size: bytes.length, offset: this.offset });
    this.parts.push(header, bytes);
    this.offset += header.length + bytes.length;
    if (this.offset > MAX_OFFSET) throw new Error('The ZIP would exceed 4 GB.');
  }

  /** The finished archive as a Blob. */
  finish() {
    const directory = [];
    let directorySize = 0;
    for (const entry of this.entries) {
      const record = new Uint8Array(46 + entry.nameBytes.length);
      const view = new DataView(record.buffer);
      view.setUint32(0, 0x02014b50, true); // central directory signature
      view.setUint16(4, 20, true); // version made by
      view.setUint16(6, 20, true); // version needed to extract
      view.setUint16(8, UTF8_NAMES, true);
      view.setUint16(10, 0, true); // stored
      view.setUint16(12, this.time, true);
      view.setUint16(14, this.date, true);
      view.setUint32(16, entry.crc, true);
      view.setUint32(20, entry.size, true);
      view.setUint32(24, entry.size, true);
      view.setUint16(28, entry.nameBytes.length, true);
      // extra length, comment length, disk number, internal and external
      // attributes are all zero (bytes 30-41).
      view.setUint32(42, entry.offset, true);
      record.set(entry.nameBytes, 46);
      directory.push(record);
      directorySize += record.length;
    }

    const end = new Uint8Array(22);
    const view = new DataView(end.buffer);
    view.setUint32(0, 0x06054b50, true); // end of central directory signature
    view.setUint16(8, this.entries.length, true); // entries on this disk
    view.setUint16(10, this.entries.length, true); // total entries
    view.setUint32(12, directorySize, true);
    view.setUint32(16, this.offset, true); // central directory offset
    return new Blob([...this.parts, ...directory, end], { type: 'application/zip' });
  }
}
