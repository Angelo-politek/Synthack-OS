// Contenitore ELE3 dentro il .syx: port di container.c, integrity.c e firmware.c di elektron-firmware-tool
// (Marcel Bierling, MIT), solo per ELE3. La chiave dell'HMAC si ricava dall'immagine stessa ed e' accettata
// solo se riproduce il digest dell'immagine.

import { depack, pack, SECT_HDR } from "./aplib.ts";
import { hmacSha256, Sha256 } from "./sha256.ts";
import { decode, declaredPackets, encode, PREAMBLE, type Transport } from "./transport.ts";

const BUILD_OFF = 0x07, COUNT_OFF = 0x1c, TABLE_OFF = 0x20, ENTRY = 16, MAX_SECTIONS = 64, ALIGN = 16, DIGEST = 32;
export const SYNTAKT = 0x16;

export interface Section {
  id: number;
  offset: number;
  compLen: number;
  dest: number;
}

export interface Verify {
  ok: boolean;
  problems: string[];
}

const be32 = (d: Uint8Array, o: number): number => ((d[o] << 24) | (d[o + 1] << 16) | (d[o + 2] << 8) | d[o + 3]) >>> 0;
const wr32 = (d: Uint8Array, o: number, v: number): void => {
  d[o] = v >>> 24; d[o + 1] = v >>> 16; d[o + 2] = v >>> 8; d[o + 3] = v;
};
const align = (v: number): number => (v + ALIGN - 1) & ~(ALIGN - 1);
const isAlnum = (c: number): boolean => (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122);

/** Checksum del preambolo: somma delle parole BE, ognuna in XOR col suo indice da 1. */
export function contentChecksum(c: Uint8Array, len: number): number {
  let acc = 0;
  for (let k = 0, n = len >>> 2; k < n; k++) acc = (acc + ((be32(c, 4 * k) ^ (k + 1)) >>> 0)) >>> 0;
  return acc;
}

function deriveKey(s: Uint8Array, cnst: Uint8Array): Uint8Array {
  const h = new Sha256().update(s).digest();
  const hr = new Sha256().update(s.slice().reverse()).digest();
  return h.map((x, i) => x ^ hr[i] ^ cnst[i]);
}

/** Chiave dal blocco materiale (ancora, stringa ASCII, zero, 32 byte), verificata contro il digest. */
function extractKey(fw: Uint8Array, msg: Uint8Array, expect: Uint8Array): Uint8Array | null {
  const anchor = [0xbe, 0xf9, 0xa3, 0xf7, 0xc6, 0x71, 0x78, 0xf2];
  outer: for (let i = fw.indexOf(anchor[0]); i >= 0 && i + 8 <= fw.length; i = fw.indexOf(anchor[0], i + 1)) {
    for (let k = 1; k < 8; k++) if (fw[i + k] !== anchor[k]) continue outer;
    const s = i + 8;
    let p = s;
    while (p < fw.length && fw[p] >= 0x20 && fw[p] < 0x7f && p - s < 64) p++;
    if (p === s || p >= fw.length || fw[p] !== 0 || p + 1 + 32 > fw.length) continue;
    const cand = deriveKey(fw.subarray(s, p), fw.subarray(p + 1, p + 33));
    const dig = hmacSha256(cand, msg);
    if (dig.every((x, j) => x === expect[j])) return cand;
  }
  return null;
}

export class Firmware {
  readonly raw: Uint8Array;
  readonly transport: Transport;
  readonly data: Uint8Array;          // contenitore (fino alla fine del flusso decodificato)
  readonly declaredSize: number;
  readonly sections: Section[] = [];
  readonly device: number;
  readonly version: string;
  readonly trailerBytes: number;      // oltre la fine allineata delle sezioni: [riempimento][0000][HMAC]
  key: Uint8Array | null = null;      // la Syntakt 1.41 non ha la coda HMAC: niente chiave
  private cache = new Map<number, Uint8Array | null>();

  constructor(raw: Uint8Array) {
    if (raw[0] !== 0xf0) throw new Error("not a .syx file");
    this.raw = raw;
    this.transport = decode(raw);
    this.device = this.transport.device;
    const st = this.transport.stream;
    let off = -1;
    for (let e = 0; e + 4 <= st.length; e++)
      if (st[e] === 0x45 && st[e + 1] === 0x4c && st[e + 2] === 0x45 && st[e + 3] === 0x33) { off = e; break; }
    if (off < PREAMBLE) throw new Error("not an ELE3 OS image");
    this.data = st.subarray(off);
    if (this.data.length < TABLE_OFF) throw new Error("container too short");
    this.declaredSize = be32(st, 0);
    const declared = be32(this.data, COUNT_OFF);
    if (declared > MAX_SECTIONS) throw new Error("malformed section table");
    const n = Math.min(declared, Math.floor((this.data.length - TABLE_OFF) / ENTRY));
    for (let s = 0; s < n; s++) {
      const e = TABLE_OFF + s * ENTRY;
      this.sections.push({ id: be32(this.data, e), offset: be32(this.data, e + 4), compLen: be32(this.data, e + 8), dest: be32(this.data, e + 12) });
    }
    const lim = Math.min(COUNT_OFF, this.data.length);
    let v = "";
    for (let i = BUILD_OFF; i + 2 < lim; i++) {
      const c = this.data;
      if (c[i] >= 48 && c[i] <= 57 && c[i + 1] === 46 && c[i + 2] >= 48 && c[i + 2] <= 57) {
        for (let j = i; j < lim && (isAlnum(c[j]) || c[j] === 46); j++) v += String.fromCharCode(c[j]);
        break;
      }
    }
    this.version = v;
    const end = Math.max(0, ...this.sections.map((s) => s.offset + s.compLen));
    this.trailerBytes = Math.max(0, this.declaredSize - align(end));
    this.findKey();
  }

  section(id: number): Section {
    const s = this.sections.find((x) => x.id === id);
    if (!s) throw new Error(`no section ${id}`);
    return s;
  }

  storedLen(s: Section): number {
    const avail = s.offset < this.data.length ? this.data.length - s.offset : 0;
    return s.compLen && s.compLen <= avail ? s.compLen : avail;
  }

  /** Contenuto decompresso, o null se la sezione e' salvata grezza. */
  depacked(s: Section): Uint8Array | null {
    if (!this.cache.has(s.id)) {
      const cl = this.storedLen(s);
      const d = cl ? depack(this.data.subarray(s.offset, s.offset + cl), true) : null;
      this.cache.set(s.id, d && d.length ? d : null);
    }
    return this.cache.get(s.id)!;
  }

  /** Byte della sezione come li estrae il tool: decompressi, oppure grezzi. */
  extract(id: number): Uint8Array {
    const s = this.section(id);
    const d = this.depacked(s);
    if (d) return d;
    const end = Math.min(this.data.length, s.offset + s.compLen);
    return this.data.slice(Math.min(s.offset, end), end);
  }

  /** Il contenitore come lo scrive --emit-container (fino alla dimensione dichiarata). */
  container(): Uint8Array {
    const n = this.declaredSize && this.declaredSize <= this.data.length ? this.declaredSize : this.data.length;
    return this.data.subarray(0, n);
  }

  private findKey(): void {
    const size = this.declaredSize;
    if (size < 4 + DIGEST || size > this.data.length) return;
    const msg = this.data.subarray(0, size - DIGEST), expect = this.data.subarray(size - DIGEST, size);
    for (const s of this.sections) {
      const d = this.depacked(s);
      if (!d) continue;
      const k = extractKey(d, msg, expect);
      if (k) { this.key = k; return; }
    }
  }

  /** Tutte le verifiche che il file porta (come fw_verify). */
  verify(): Verify {
    const t = this.transport, problems: string[] = [];
    if (t.pktBad) problems.push(`${t.pktBad} SysEx packets with a wrong checksum`);
    const np = declaredPackets(t);
    if (np !== null && np !== t.ndata) problems.push("packet count does not match the start marker");
    const size = this.declaredSize;
    if (size <= this.data.length && be32(t.stream, 4) !== contentChecksum(this.data, size))
      problems.push("content checksum mismatch");
    for (const s of this.sections) {
      if (s.offset + SECT_HDR > this.data.length || !this.depacked(s)) continue;
      const p = s.offset, slen = be32(this.data, p);
      let acc = 0;
      for (let k = 0; k < slen && p + SECT_HDR + k < this.data.length; k++) acc = (acc + this.data[p + SECT_HDR + k]) >>> 0;
      if (acc !== be32(this.data, p + 4)) problems.push(`section ${s.id}: stream checksum mismatch`);
    }
    if (this.key && size >= 4 + DIGEST && size <= this.data.length && !problems.length) {
      const dig = hmacSha256(this.key, this.data.subarray(0, size - DIGEST));
      if (!dig.every((x, j) => x === this.data[size - DIGEST + j])) problems.push("HMAC digest mismatch");
    }
    return { ok: !problems.length, problems };
  }

  /** Nuovo .syx con alcune sezioni sostituite (byte grezzi): le compresse vengono ricompresse, poi
   * tabella, checksum, HMAC (se l'immagine lo porta) e pacchetti ricalcolati (come elektron-firmware-tool -c). */
  rebuild(replace: Map<number, Uint8Array>, level = 3, progress?: (id: number, done: number, total: number) => void): Uint8Array {
    if (!this.key && this.trailerBytes) throw new Error("unrecognized container trailer: cannot rebuild this image safely");
    const c = this.data;
    const order = this.sections.map((s, i) => ({ s, i })).sort((a, b) => a.s.offset - b.s.offset);
    const firstOff = Math.min(c.length, ...this.sections.map((s) => s.offset));
    const parts: { pos: number; bytes: Uint8Array; i: number }[] = [];
    let pos = firstOff;
    for (const { s, i } of order) {
      pos = align(pos);
      const ov = replace.get(s.id);
      let bytes: Uint8Array;
      if (ov && this.depacked(s)) bytes = pack(ov, level, progress && ((d, t) => progress(s.id, d, t)));
      else if (ov) bytes = ov;
      else {
        const stored = this.storedLen(s);
        bytes = c.subarray(stored ? s.offset : c.length, (stored ? s.offset : c.length) + stored);
      }
      parts.push({ pos, bytes, i });
      pos += bytes.length;
    }
    const hmacOff = align(pos + 4);
    const nc = new Uint8Array(this.key ? hmacOff + DIGEST : align(pos));
    nc.set(c.subarray(0, firstOff));
    for (const p of parts) {
      nc.set(p.bytes, p.pos);
      wr32(nc, TABLE_OFF + p.i * ENTRY + 4, p.pos);
      wr32(nc, TABLE_OFF + p.i * ENTRY + 8, p.bytes.length);
    }
    if (this.key) nc.set(hmacSha256(this.key, nc.subarray(0, hmacOff)), hmacOff);
    const pre = new Uint8Array(PREAMBLE);
    wr32(pre, 0, nc.length);
    wr32(pre, 4, contentChecksum(nc, nc.length));
    return encode(nc, pre, this.device, this.transport.base, this.transport.markerInfo);
  }
}
