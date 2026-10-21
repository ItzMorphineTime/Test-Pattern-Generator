/**
 * Minimal MP4 (ISO BMFF) writer for a single H.264 video track.
 *
 * Takes AVCC-format samples (what WebCodecs emits with `avc: { format: 'avc' }`:
 * each frame's NAL units prefixed with their length) plus the encoder's avcC
 * configuration record, and writes ftyp + moov + mdat. The movie box comes
 * first ("fast start"), so players can begin before reading the whole file.
 *
 * Samples are added in decode order with their presentation (display) index.
 * When an encoder reorders frames (B-frames), a signed composition-offset
 * table maps them back to display order.
 */

import { fpsFraction, framesPerSecond } from './timing.js';

const MOVIE_TIMESCALE = 1000;
const MAX_32 = 0xffffffff;

// WebCodecs VideoColorSpace names -> ISO/IEC 23091-2 code points for 'colr'.
const PRIMARIES = { bt709: 1, bt470bg: 5, smpte170m: 6, bt2020: 9, smpte432: 12 };
const TRANSFER = { bt709: 1, smpte170m: 6, linear: 8, 'iec61966-2-1': 13, pq: 16, hlg: 18 };
const MATRIX = { rgb: 0, bt709: 1, bt470bg: 5, smpte170m: 6, 'bt2020-ncl': 9 };

export class Mp4Writer {
  constructor({ width, height, fps }) {
    this.width = width;
    this.height = height;
    const { num, den } = fpsFraction(fps);
    if (den === 1) {
      this.timescale = num * 1000; // integer rates: the usual 1000x timescale
      this.delta = 1000;
    } else {
      const k = num < 1000 ? Math.ceil(1000 / num) : 1;
      this.timescale = num * k; // e.g. 29.97 fps -> 30000 / 1001, exactly
      this.delta = den * k;
    }
    this.samplesPerChunk = framesPerSecond(fps); // interleave in ~1 s chunks
    this.samples = [];
    this.dataSize = 0;
    this.description = null;
    this.colorSpace = null;
  }

  /** The avcC record (WebCodecs `decoderConfig.description`). */
  setDescription(description) {
    this.description = toBytes(description).slice();
  }

  /** WebCodecs `decoderConfig.colorSpace`; written as a 'colr' box when known. */
  setColorSpace(colorSpace) {
    this.colorSpace = colorSpace;
  }

  addSample(data, isKey, presentationIndex) {
    if (this.samples.length === 0 && !isKey) {
      throw new Error('The first video frame must be a key frame.');
    }
    const bytes = toBytes(data);
    this.samples.push({ bytes, isKey, presentationIndex });
    this.dataSize += bytes.length;
  }

  get sampleCount() {
    return this.samples.length;
  }

  /** The finished file as a Blob. */
  finish() {
    if (!this.samples.length) throw new Error('No video frames were encoded.');
    if (!this.description) throw new Error('The encoder did not provide an H.264 configuration.');
    const ftyp = this.ftyp();
    const mdatHeaderSize = 8;
    // stco entries are fixed-width, so the moov size doesn't depend on their values.
    const dataStart = ftyp.length + this.moov(0).length + mdatHeaderSize;
    if (dataStart + this.dataSize > MAX_32) {
      throw new Error('The video would exceed 4 GB; shorten it or lower the quality.');
    }
    const mdatHeader = concat([u32(mdatHeaderSize + this.dataSize), ascii('mdat')]);
    return new Blob([ftyp, this.moov(dataStart), mdatHeader, ...this.samples.map((s) => s.bytes)],
      { type: 'video/mp4' });
  }

  // -- boxes ----------------------------------------------------------
  compositionOffsets() {
    const offsets = this.samples.map((s, i) => (s.presentationIndex - i) * this.delta);
    return offsets.some((offset) => offset !== 0) ? offsets : null;
  }

  ftyp() {
    const brands = ['isom', 'iso2', 'avc1', 'mp41'];
    if (this.compositionOffsets()) brands.push('iso6'); // signed composition offsets
    return box('ftyp', ascii('isom'), u32(512), ...brands.map(ascii));
  }

  moov(dataStart) {
    const mediaDuration = this.samples.length * this.delta;
    const movieDuration = Math.round((mediaDuration * MOVIE_TIMESCALE) / this.timescale);
    return box('moov', this.mvhd(movieDuration),
      box('trak', this.tkhd(movieDuration),
        box('mdia', this.mdhd(mediaDuration), this.hdlr(), this.minf(dataStart))));
  }

  mvhd(duration) {
    return fullBox('mvhd', 0, 0,
      u32(0), u32(0), // creation and modification time
      u32(MOVIE_TIMESCALE), u32(duration),
      u32(0x00010000), // playback rate 1.0
      u16(0x0100), zeros(10), // volume 1.0, reserved
      IDENTITY_MATRIX,
      zeros(24), // pre-defined
      u32(2)); // next track ID
  }

  tkhd(duration) {
    return fullBox('tkhd', 0, 0x000003, // track enabled, used in the movie
      u32(0), u32(0), u32(1), u32(0), u32(duration), // times, track ID 1, reserved, duration
      zeros(8),
      u16(0), u16(0), u16(0), u16(0), // layer, alternate group, volume, reserved
      IDENTITY_MATRIX,
      u32(this.width * 0x10000), u32(this.height * 0x10000)); // 16.16 fixed point
  }

  mdhd(duration) {
    return fullBox('mdhd', 0, 0, u32(0), u32(0), u32(this.timescale), u32(duration),
      u16(0x55c4), u16(0)); // language "und"
  }

  hdlr() {
    return fullBox('hdlr', 0, 0, u32(0), ascii('vide'), zeros(12), ascii('VideoHandler'), u8(0));
  }

  minf(dataStart) {
    const vmhd = fullBox('vmhd', 0, 1, zeros(8)); // graphics mode + opcolor
    const dinf = box('dinf', fullBox('dref', 0, 0, u32(1), fullBox('url ', 0, 1)));
    return box('minf', vmhd, dinf, this.stbl(dataStart));
  }

  stbl(dataStart) {
    const n = this.samples.length;
    const tables = [this.stsd(), fullBox('stts', 0, 0, u32(1), u32(n), u32(this.delta))];

    const offsets = this.compositionOffsets();
    if (offsets) tables.push(fullBox('ctts', 1, 0, ...runLengths(offsets)));

    if (this.samples.some((s) => !s.isKey)) {
      const keys = [];
      this.samples.forEach((s, i) => s.isKey && keys.push(i + 1));
      tables.push(fullBox('stss', 0, 0, u32(keys.length), be32(keys)));
    }

    const perChunk = this.samplesPerChunk;
    const chunkCount = Math.ceil(n / perChunk);
    const lastChunkSamples = n - (chunkCount - 1) * perChunk;
    const stsc = [[1, Math.min(perChunk, n)]];
    if (chunkCount > 1 && lastChunkSamples !== perChunk) stsc.push([chunkCount, lastChunkSamples]);
    tables.push(fullBox('stsc', 0, 0, u32(stsc.length),
      be32(stsc.flatMap(([firstChunk, count]) => [firstChunk, count, 1]))));

    tables.push(fullBox('stsz', 0, 0, u32(0), u32(n), be32(this.samples.map((s) => s.bytes.length))));

    const chunkOffsets = [];
    let offset = dataStart;
    this.samples.forEach((s, i) => {
      if (i % perChunk === 0) chunkOffsets.push(offset);
      offset += s.bytes.length;
    });
    tables.push(fullBox('stco', 0, 0, u32(chunkOffsets.length), be32(chunkOffsets)));
    return box('stbl', ...tables);
  }

  stsd() {
    const children = [box('avcC', this.description)];
    const colr = this.colr();
    if (colr) children.push(colr);
    const avc1 = box('avc1',
      zeros(6), u16(1), // reserved, data reference index
      zeros(16), // pre-defined and reserved
      u16(this.width), u16(this.height),
      u32(0x00480000), u32(0x00480000), // 72 dpi
      u32(0), u16(1), // reserved, frames per sample
      zeros(32), // compressor name (empty)
      u16(0x0018), u16(0xffff), // 24-bit depth, pre-defined -1
      ...children);
    return fullBox('stsd', 0, 0, u32(1), avc1);
  }

  colr() {
    const cs = this.colorSpace;
    if (!cs) return null;
    const primaries = PRIMARIES[cs.primaries];
    const transfer = TRANSFER[cs.transfer];
    const matrix = MATRIX[cs.matrix];
    if (primaries === undefined || transfer === undefined || matrix === undefined) return null;
    return box('colr', ascii('nclx'), u16(primaries), u16(transfer), u16(matrix),
      u8(cs.fullRange ? 0x80 : 0));
  }
}

// -- byte helpers --------------------------------------------------------
const IDENTITY_MATRIX = be32([0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000]);

function box(type, ...parts) {
  const payload = concat(parts);
  return concat([u32(8 + payload.length), ascii(type), payload]);
}

function fullBox(type, version, flags, ...parts) {
  return box(type, u8(version), u8(flags >> 16), u8(flags >> 8), u8(flags), ...parts);
}

/** ctts entries: consecutive equal offsets collapse into one (count, offset) pair. */
function runLengths(offsets) {
  const entries = [];
  for (const offset of offsets) {
    const last = entries[entries.length - 1];
    if (last && last[1] === offset) last[0] += 1;
    else entries.push([1, offset]);
  }
  const table = new Uint8Array(entries.length * 8);
  const view = new DataView(table.buffer);
  entries.forEach(([count, offset], i) => {
    view.setUint32(i * 8, count);
    view.setInt32(i * 8 + 4, offset); // signed: version 1 table
  });
  return [u32(entries.length), table];
}

function u8(value) {
  return Uint8Array.of(value & 0xff);
}

function u16(value) {
  return Uint8Array.of((value >>> 8) & 0xff, value & 0xff);
}

function u32(value) {
  return be32([value]);
}

/** Big-endian unsigned 32-bit integers packed into one array (fast for long tables). */
function be32(values) {
  const bytes = new Uint8Array(values.length * 4);
  const view = new DataView(bytes.buffer);
  values.forEach((value, i) => view.setUint32(i * 4, value));
  return bytes;
}

function zeros(length) {
  return new Uint8Array(length);
}

function ascii(text) {
  return Uint8Array.from(text, (ch) => ch.charCodeAt(0));
}

function concat(parts) {
  const out = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    out.set(part, at);
    at += part.length;
  }
  return out;
}

function toBytes(data) {
  if (data instanceof Uint8Array) return data;
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  return new Uint8Array(data);
}
