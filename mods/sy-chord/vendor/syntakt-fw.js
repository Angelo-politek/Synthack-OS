// Syntakt OS .syx codec + SY CHORD wave bank access. Pure functions, no dependencies
// beyond the sibling aplib.js; runs in browsers and in Node (ES module). Never ships or
// fetches firmware: every byte of Elektron data comes from the file the user supplies.
//
// Layers: SysEx messages -> 8-in-7 packed packets -> [size:4][checksum:4] + ELE3 container.
//
// Two ways to write a section:
//   replaceRawSection()  patches the packets of the loaded file in place. Same length only,
//                        raw sections only; every offset stays put. The wave bank uses this.
//   replaceSection()     rebuilds the container from its section table and re-encodes the
//                        whole transport, so the packed length may change and later sections
//                        move. Compressed sections are packed with aplib.js on the way in.
// The rebuild mirrors elektron-firmware-tool's ELE3 path (container.c build_ele3 +
// transport.c syx_encode) byte for byte; see the notes on rebuildContainer/encodeSyx.
import { depack as apDepack, pack as apPack } from "./aplib.js";

export const SUPPORTED = {
  // sha256 of the official file -> description
  "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e": "Syntakt OS 1.41",
};

export const WAVE = {
  SECTION_ID: 7,
  SECTION_LEN: 383760,
  SECTION_SHA256: "daf6451cf9587c0b628e901b7bb6b25f4e2633d448c534c0c181dd35ec783bc2",
  BANK_END: 0x1e3fc, // frame k (1..31) starts at BANK_END - k * STEP, i.e. stored in reverse
  STEP: 0x404,
  SAMPLES: 257, // one cycle in 256 samples + guard (y[256] == y[0])
  FRAMES: 31,
  PEAK: 0x7fff0000,
  SINE_OFF: 0x53e50, // frame 0: a sine SHARED with other machines
};

const PKT = 126, HDR = 9, ENC = 116, CK = 125, CK_FROM = 6, CK_SPAN = 119, DEC_PER_PKT = 101;
const MARKER_LEN = 14, INFO_OFF = 7, INFO_LEN = 7, DEV_OFF = 3;
/** ELE3 container geometry: section count word, then 16-byte table entries. */
const ELE3 = { COUNT_OFF: 0x1c, TABLE_OFF: 0x20, ENTRY: 16, ALIGN: 16 };

const align = (v, a) => v + ((a - (v % a)) % a);

export async function sha256hex(bytes) {
  const d = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function be32(a, o) { return ((a[o] << 24) | (a[o + 1] << 16) | (a[o + 2] << 8) | a[o + 3]) >>> 0; }
function wr32(a, o, v) { a[o] = v >>> 24; a[o + 1] = (v >>> 16) & 255; a[o + 2] = (v >>> 8) & 255; a[o + 3] = v & 255; }

export function contentChecksum(container) {
  let acc = 0;
  for (let k = 0, n = container.length >>> 2; k < n; k++) acc = (acc + (((k + 1) ^ be32(container, 4 * k)) >>> 0)) >>> 0;
  return acc;
}

export function packetChecksum(body, base) {
  let acc = 0;
  for (let i = 0; i < CK_SPAN; i++) acc += body[CK_FROM + i] ^ ((base + i) & 0xff);
  return (base + acc) & 0x7f;
}

/** Split the file into SysEx messages and decode the data packets. Throws on anything unexpected. */
export function parseSyx(file) {
  const msgs = []; // {start, end} of each body (between F0 and F7)
  let i = 0;
  while (i < file.length) {
    if (file[i] !== 0xf0) throw new Error("byte " + i + ": expected F0");
    const e = file.indexOf(0xf7, i);
    if (e < 0) throw new Error("unterminated SysEx message");
    msgs.push({ start: i + 1, end: e });
    i = e + 1;
  }
  const data = msgs.filter((m) => m.end - m.start === PKT && file[m.start + 5] === 0x7e);
  const markers = msgs.filter((m) => file[m.start + 5] === 0x7f);
  if (markers.length !== 2 || data.length + 2 !== msgs.length) throw new Error("unexpected message layout");
  const base = file[markers[0].start + 7];
  const decoded = new Uint8Array(data.length * DEC_PER_PKT);
  let o = 0;
  for (const m of data) {
    const body = file.subarray(m.start, m.end);
    if (packetChecksum(body, base) !== body[CK]) throw new Error("packet checksum mismatch: damaged file");
    for (let k = HDR; k < HDR + ENC; k += 8) {
      const ms = body[k], nd = Math.min(7, HDR + ENC - k - 1);
      for (let n = 0; n < nd; n++) decoded[o++] = body[k + 1 + n] | (((ms >> (6 - n)) & 1) << 7);
    }
  }
  const size = be32(decoded, 0);
  if (size + 8 > decoded.length) throw new Error("declared container size exceeds the data");
  const container = decoded.subarray(8, 8 + size);
  if (String.fromCharCode(...container.subarray(0, 4)) !== "ELE3") throw new Error("not an ELE3 container");
  if (contentChecksum(container) !== be32(decoded, 4)) throw new Error("container checksum mismatch");
  const sections = [];
  for (let s = 0, n = be32(container, 0x1c); s < n; s++) {
    const t = 0x20 + 16 * s;
    sections.push({ id: be32(container, t), offset: be32(container, t + 4), length: be32(container, t + 8), dest: be32(container, t + 12) });
  }
  // Everything the encoder needs to put the transport back together: the device id and the
  // start marker's 7 info bytes (checksum seed, first block/seq counter, packet count).
  const device = file[markers[0].start + DEV_OFF];
  const markerInfo = file.slice(markers[0].start + INFO_OFF, markers[0].start + INFO_OFF + INFO_LEN);
  return { file, data, base, device, markerInfo, decoded, container, sections, version: String.fromCharCode(...container.subarray(0x14, 0x18)) };
}

export function getSection(parsed, id) {
  const s = parsed.sections.find((x) => x.id === id);
  if (!s) throw new Error("no section " + id);
  return parsed.container.slice(s.offset, s.offset + s.length);
}

/** Return a new .syx with raw section `id` replaced by same-length `bytes`; all checksums recomputed. */
export function replaceRawSection(parsed, id, bytes) {
  const s = parsed.sections.find((x) => x.id === id);
  if (!s || bytes.length !== s.length) throw new Error("replacement must have exactly the size of the section");
  const decoded = parsed.decoded.slice();
  decoded.set(bytes, 8 + s.offset);
  wr32(decoded, 4, contentChecksum(decoded.subarray(8, 8 + be32(decoded, 0))));
  const out = parsed.file.slice();
  let o = 0;
  for (const m of parsed.data) {
    const body = out.subarray(m.start, m.end);
    for (let k = HDR; k < HDR + ENC; k += 8) {
      const nd = Math.min(7, HDR + ENC - k - 1);
      let ms = 0;
      for (let n = 0; n < nd; n++) { const v = decoded[o++]; if (v & 0x80) ms |= 1 << (6 - n); body[k + 1 + n] = v & 0x7f; }
      body[k] = ms;
    }
    body[CK] = packetChecksum(body, parsed.base);
  }
  return out;
}

// ---- compressed sections, container rebuild, transport encode -----------------------

/** Cache of the "is this section an aPLib stream?" answer, per parsed image. */
const compCache = new WeakMap();

/**
 * Is section `id` stored as an aPLib stream rather than raw?
 * Derived exactly the way the C tool does it (container.c build_ele3): try to depack the
 * stored bytes; a section that decodes to something non-empty is compressed. There is no
 * flag in the table and no hard-coded list, so no assumption about a particular OS build.
 */
export function isCompressed(parsed, id) {
  let m = compCache.get(parsed);
  if (!m) compCache.set(parsed, (m = new Map()));
  if (m.has(id)) return m.get(id);
  let yes = false;
  try { yes = apDepack(getSection(parsed, id)).length > 0; } catch { yes = false; }
  m.set(id, yes);
  return yes;
}

/** Section contents as the device sees them: decompressed if the section is compressed. */
export function getSectionRaw(parsed, id) {
  const stored = getSection(parsed, id);
  return isCompressed(parsed, id) ? apDepack(stored) : stored;
}

/**
 * Rebuild the ELE3 container with zero or more sections replaced. Mirrors build_ele3:
 * everything before the first section (header + table) is copied verbatim, the sections
 * are laid out in offset order each 16-byte aligned, the table's offset and length fields
 * are rewritten in place (id and dest are kept), and the container is padded to a 16-byte
 * boundary. Padding is zero, as in the C tool's calloc'd buffer.
 * Only the no-HMAC ELE3 layout is implemented - the one Syntakt uses. An image with bytes
 * past the aligned end of its sections carries a trailer this code cannot reproduce, so it
 * is refused rather than silently rebuilt without it (cmd_replace refuses it too).
 */
function rebuildContainer(parsed, overrides, level, onProgress) {
  const c = parsed.container, secs = parsed.sections;
  let end = 0;
  for (const s of secs) end = Math.max(end, s.offset + s.length);
  if (c.length > align(end, ELE3.ALIGN)) throw new Error("container has a trailer this build path cannot reproduce");
  const firstOff = Math.min(...secs.map((s) => s.offset));

  // Sorted view of the table; the entries keep their original table slots.
  const order = secs.map((s, i) => i).sort((a, b) => secs[a].offset - secs[b].offset);
  const stored = new Map(); // table index -> bytes to write
  for (const i of order) {
    const s = secs[i];
    const ov = overrides.find((o) => o.id === s.id);
    if (!ov) stored.set(i, c.subarray(s.offset, s.offset + s.length));
    else stored.set(i, isCompressed(parsed, s.id) ? apPack(ov.bytes, level, onProgress) : ov.bytes);
  }

  let pos = firstOff;
  const at = new Map();
  for (const i of order) { pos = align(pos, ELE3.ALIGN); at.set(i, pos); pos += stored.get(i).length; }
  const out = new Uint8Array(align(pos, ELE3.ALIGN));
  out.set(c.subarray(0, firstOff));
  for (const i of order) {
    out.set(stored.get(i), at.get(i));
    const t = ELE3.TABLE_OFF + i * ELE3.ENTRY;
    wr32(out, t + 4, at.get(i));
    wr32(out, t + 8, stored.get(i).length);
  }
  return out;
}

/** 8-in-7, MSB byte first: 7 data bytes per group, their high bits collected in the lead byte. */
function encode8in7(src, from, n, dst, at) {
  let o = at;
  for (let i = 0; i < n; i += 7) {
    const nd = Math.min(7, n - i);
    let ms = 0;
    for (let k = 0; k < nd; k++) if (src[from + i + k] & 0x80) ms |= 1 << (6 - k);
    dst[o++] = ms;
    for (let k = 0; k < nd; k++) dst[o++] = src[from + i + k] & 0x7f;
  }
  return o;
}

/**
 * Wrap a container in the SysEx transport, the way syx_encode does: the decoded stream is
 * [size][content checksum] + container, zero-padded to a whole number of 126-byte data
 * packets (always one packet more than the payload strictly needs), between a start and an
 * end marker. Device, checksum seed and the marker's counter fields come from `parsed`,
 * so an unchanged container re-encodes to the file it came from.
 */
function encodeSyx(container, parsed) {
  const clen = container.length, npkt = Math.floor((8 + clen) / DEC_PER_PKT) + 1;
  const stream = new Uint8Array(npkt * DEC_PER_PKT);
  wr32(stream, 0, clen);
  wr32(stream, 4, contentChecksum(container));
  stream.set(container, 8);

  const info = parsed.markerInfo.slice();
  info[0] = parsed.base;
  info[4] = (npkt >>> 14) & 0x7f; info[5] = (npkt >>> 7) & 0x7f; info[6] = npkt & 0x7f;
  const startBlock = (info[1] << 7) | info[2], startSeq = info[3];

  const out = new Uint8Array(2 * (MARKER_LEN + 2) + npkt * (PKT + 2));
  let o = 0;
  const marker = (kind) => {
    out[o++] = 0xf0;
    out.set([0x00, 0x20, 0x3c, parsed.device, 0x00, 0x7f, kind], o);
    out.set(info, o + INFO_OFF);
    o += MARKER_LEN;
    out[o++] = 0xf7;
  };
  marker(0x01);
  for (let k = 0; k < npkt; k++) {
    out[o++] = 0xf0;
    const b = o;
    out.set([0x00, 0x20, 0x3c, parsed.device, 0x00, 0x7e], b);
    const block = startBlock + ((startSeq + k) >>> 7);
    out[b + 6] = (block >>> 7) & 0x7f; out[b + 7] = block & 0x7f;
    out[b + 8] = (startSeq + k) & 0x7f;
    encode8in7(stream, k * DEC_PER_PKT, DEC_PER_PKT, out, b + HDR);
    out[b + CK] = packetChecksum(out.subarray(b, b + PKT), parsed.base);
    o = b + PKT;
    out[o++] = 0xf7;
  }
  marker(0x02);
  return out;
}

/** The .syx file bytes of a parsed image (round trips an untouched one exactly). */
export function buildSyx(parsed) {
  return encodeSyx(parsed.container, parsed);
}

/**
 * A new parsed image with section `id` holding `bytes`, compressing them first if the
 * section is compressed. The stored length may change, in which case every later section
 * moves and the table, the container size and all checksums are recomputed. `level` is the
 * aPLib effort 0..3; level 3 reproduces the reference C tool's output byte for byte.
 * The result is produced by parsing the rebuilt file, so it is verified before it is returned.
 */
export function replaceSection(parsed, id, bytes, { level = 3, onProgress = null } = {}) {
  if (!parsed.sections.some((s) => s.id === id)) throw new Error("no section " + id);
  const container = rebuildContainer(parsed, [{ id, bytes }], level, onProgress);
  return parseSyx(encodeSyx(container, parsed));
}

// ---- SY CHORD wave bank -------------------------------------------------------------

export function frameOffset(k) {
  if (k === 0) return WAVE.SINE_OFF;
  if (k < 1 || k > WAVE.FRAMES) throw new Error("frame must be 0..31");
  return WAVE.BANK_END - k * WAVE.STEP;
}

/** Frame k of a section-7 image as Float64Array(256) in -1..1 (guard sample dropped). */
export function readFrame(section, k) {
  const v = new DataView(section.buffer, section.byteOffset + frameOffset(k), WAVE.SAMPLES * 4);
  const y = new Float64Array(256);
  for (let i = 0; i < 256; i++) y[i] = v.getInt32(4 * i) / 2147483648;
  return y;
}

/** Write a 256-sample cycle (floats, any scale) as frame k: DC removed, peak-normalised, y[0] = 0, guard added.
 *  The caller is responsible for phase (the cycle should start at a rising zero crossing) and band-limiting. */
export function writeFrame(section, k, cycle) {
  if (cycle.length !== 256) throw new Error("cycle must have 256 samples");
  let mean = 0; for (const x of cycle) mean += x; mean /= 256;
  let peak = 0; for (const x of cycle) peak = Math.max(peak, Math.abs(x - mean));
  if (!(peak > 0)) throw new Error("silent cycle");
  const v = new DataView(section.buffer, section.byteOffset + frameOffset(k), WAVE.SAMPLES * 4);
  for (let i = 0; i < 256; i++) v.setInt32(4 * i, i === 0 ? 0 : Math.round(((cycle[i] - mean) / peak) * WAVE.PEAK));
  v.setInt32(4 * 256, 0);
}

/** Byte range in which `b` differs from `a`, as [first, last], or null: used by the self-check. */
export function diffRange(a, b) {
  if (a.length !== b.length) return [0, Math.max(a.length, b.length) - 1];
  let first = -1, last = -1;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) { if (first < 0) first = i; last = i; }
  return first < 0 ? null : [first, last];
}
