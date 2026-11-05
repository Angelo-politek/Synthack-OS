// SPDX-License-Identifier: GPL-2.0-or-later
// Data RPC of the Syntakt over MIDI SysEx: port of Synfact's elekloader/sdk/syntakt/data_rpc.py (GSM1980, on
// elekloader by irpina). Only DataRead*/DataWrite* (0x54..0x59). OS 1.42: a probe that closes its job after the
// header gets "Reader did not complete" (0x4010AA2E); the job is released all the same (mods/long-samples).

export const HDR = Uint8Array.from([0xf0, 0x00, 0x20, 0x3c, 0x10, 0x00]);
export const WINDOW = 0x80000;
export const RAW_FIRST = 8185;

const CRC = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

/** zlib.crc32(data, prev): prev 0 = the usual CRC-32; Synfact's crc() is crc32(data, 0xffffffff). */
export function crc32(data: Uint8Array, prev = 0): number {
  let c = ~prev >>> 0;
  for (let i = 0; i < data.length; i++) c = CRC[(c ^ data[i]) & 255] ^ (c >>> 8);
  return ~c >>> 0;
}
export const crc = (data: Uint8Array): number => crc32(data, 0xffffffff);

export function be32(n: number): Uint8Array {
  return Uint8Array.of(n >>> 24 & 255, n >>> 16 & 255, n >>> 8 & 255, n & 255);
}
export function u32(b: Uint8Array, o: number): number {
  if (o + 4 > b.length) throw new Error("truncated Data RPC integer");
  return (b[o] << 24 | b[o + 1] << 16 | b[o + 2] << 8 | b[o + 3]) >>> 0;
}
export function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

export function encode87(raw: Uint8Array): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < raw.length; i += 7) {
    const g = raw.subarray(i, i + 7);
    let hi = 0;
    g.forEach((b, j) => { if (b & 128) hi |= 0x40 >> j; });
    out.push(hi, ...Array.from(g, (b) => b & 127));
  }
  return Uint8Array.from(out);
}

export function decode87(raw: Uint8Array): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < raw.length; i += 8) {
    if (raw.length - i === 1) throw new Error("truncated SysEx group");
    const hi = raw[i];
    for (let j = 1; j < 8 && i + j < raw.length; j++) {
      const b = raw[i + j];
      if (b & 128) throw new Error("invalid SysEx encoding");
      out.push(b | ((hi & (0x40 >> (j - 1))) ? 128 : 0));
    }
  }
  return Uint8Array.from(out);
}

function ok(reply: Uint8Array, kind: number): Uint8Array {
  if (reply.length < 6 || reply[4] !== (kind | 128)) throw new Error("invalid Data RPC response");
  if (!reply[5]) {
    const end = reply.indexOf(0, 6);
    throw new Error(new TextDecoder("latin1").decode(reply.subarray(6, end < 0 ? undefined : end)) || "device error");
  }
  return reply;
}

/** 31-byte header + body + 12-byte footer, as the native backup objects */
export function objectPack(n: number, body: Uint8Array): Uint8Array {
  const h = new Uint8Array(31);
  const v = new DataView(h.buffer);
  v.setUint32(0, 0xac11d303); h[4] = 2; v.setUint16(5, 8); v.setUint16(7, 13); h.set([0x30, 0x30, 0x39, 0x34], 9);
  v.setUint32(13, 8); v.setUint32(17, 0xffffffff); v.setUint32(21, n); v.setUint32(25, body.length); h[29] = 0; h[30] = 12;
  return concat(h, body, be32(crc(body)), be32(body.length), be32(0xaaa1daaa));
}

export function objectUnpack(obj: Uint8Array, n: number): Uint8Array {
  if (obj.length < 43) throw new Error("truncated Data object");
  const h = obj.subarray(0, 31), body = obj.subarray(31, obj.length - 12), f = obj.subarray(obj.length - 12);
  const head = [0xac, 0x11, 0xd3, 0x03, 0x02, 0x00, 0x08, 0x00, 0x0d];
  if (head.some((b, i) => h[i] !== b) || u32(h, 13) !== 8 || u32(h, 21) !== n || u32(h, 25) !== body.length
      || h[29] !== 0 || h[30] !== 12) throw new Error("invalid Data object header");
  if (u32(f, 0) !== crc(body) || u32(f, 4) !== body.length || u32(f, 8) !== 0xaaa1daaa) {
    throw new Error("invalid Data object checksum/footer");
  }
  return body;
}

/** A SysEx link: send one message, get each complete message back. WebMIDI in the page, a double in the tests. */
export interface Link {
  send(msg: Uint8Array): void;
  onMessage(fn: (msg: Uint8Array) => void): void;
}

export class Transport {
  private seq = 1;
  private waiting: ((rx: Uint8Array) => void) | null = null;
  private link: Link;
  private timeout: number;
  constructor(link: Link, timeout = 15000) {
    this.link = link;
    this.timeout = timeout;
    link.onMessage((m) => {
      if (m[0] !== 0xf0 || m[m.length - 1] !== 0xf7 || HDR.some((b, i) => m[i] !== b)) return;
      try { this.waiting?.(decode87(m.subarray(HDR.length, m.length - 1))); } catch { /* not ours */ }
    });
  }
  call(kind: number, payload: Uint8Array = new Uint8Array()): Promise<Uint8Array> {
    if (kind < 0x54 || kind > 0x59) throw new Error("only Data read/write RPC is allowed");
    const seq = this.seq;
    this.seq = (seq + 1) & 0x3fff || 1;
    const head = Uint8Array.of(seq >> 8, seq & 255, 0, 0, kind);
    return new Promise((done, fail) => {
      const timer = setTimeout(() => { this.waiting = null; fail(new Error("Data RPC timed out")); }, this.timeout);
      this.waiting = (rx) => {
        if (rx.length >= 6 && rx[2] === seq >> 8 && rx[3] === (seq & 255) && rx[4] === (kind | 128)) {
          clearTimeout(timer);
          this.waiting = null;
          done(rx);
        }
      };
      this.link.send(concat(HDR, encode87(concat(head, payload)), Uint8Array.of(0xf7)));
    });
  }
}

const ascii = (s: string): Uint8Array => Uint8Array.from(s, (c) => c.charCodeAt(0) & 127);

export class DataClient {
  private t: Transport;
  private block: number;
  constructor(t: Transport, block = 2048) {
    this.t = t;
    this.block = block;
  }
  private async call(kind: number, payload: Uint8Array): Promise<Uint8Array> {
    return ok(await this.t.call(kind, payload), kind);
  }
  /** the length of stock sample slot n (1..64), 0 when the Syntakt has none there: one header probe */
  async stockLength(n: number): Promise<number> {
    if (n < 1 || n > 64) throw new Error("stock slots are 1..64");
    let rx: Uint8Array;
    try {
      rx = await this.call(0x54, concat(ascii(`/samples/${n}`), Uint8Array.of(0), be32(this.block), Uint8Array.of(0)));
    } catch {
      return 0;
    }
    const job = u32(rx, 6), out: number[] = [];
    try {
      for (let seq = 0; out.length < 31 && seq < 64; seq++) {
        rx = await this.call(0x55, concat(be32(job), be32(seq)));
        if (rx.length < 27 || u32(rx, 6) !== job) throw new Error("invalid read response/job");
        for (const b of rx.subarray(27)) out.push(b);
        if (rx[18] && out.length < 31) return 0;
      }
      const o = Uint8Array.from(out.slice(0, 31));
      return out.length >= 31 && o[0] === 0xac ? u32(o, 25) : 0;
    } finally {
      try { await this.call(0x56, be32(job)); } catch { /* OS 1.42 answers "Reader did not complete" on an early close */ }
    }
  }
  /** a raw high-zone window /samples/(RAW_FIRST + k): the body, or with headerOnly its length */
  async read(k: number, headerOnly = false): Promise<Uint8Array | number> {
    if (k < 0x600 || k >= 0x2000) throw new Error("unsupported read destination");
    const n = RAW_FIRST + k;
    let rx = await this.call(0x54, concat(ascii(`/samples/${n}`), Uint8Array.of(0), be32(this.block), Uint8Array.of(0)));
    const job = u32(rx, 6);
    const out: number[] = [];
    let seq = 0, empty = 0, expected = -1;
    try {
      while (expected < 0 || out.length < expected) {
        rx = await this.call(0x55, concat(be32(job), be32(seq++)));
        if (rx.length < 27 || u32(rx, 6) !== job) throw new Error("invalid read response/job");
        const size = u32(rx, 23), chunk = rx.subarray(27);
        if (chunk.length !== size || size > this.block) throw new Error("invalid read chunk size");
        for (const b of chunk) out.push(b);
        empty = size ? 0 : empty + 1;
        if (empty > 64) throw new Error("read made no progress");
        if (out.length >= 31 && expected < 0) {
          const o = Uint8Array.from(out.slice(0, 31));
          const len = u32(o, 25);
          if (len > WINDOW) throw new Error("read object exceeds destination size");
          expected = 43 + len;
          if (headerOnly) {
            if (u32(o, 21) !== n || o[0] !== 0xac) throw new Error("invalid probe header");
            return len;
          }
        }
        if (rx[18] && (expected < 0 || out.length < expected)) throw new Error("truncated Data object");
      }
      if (out.length !== expected) throw new Error("extra Data object bytes");
      return objectUnpack(Uint8Array.from(out), n);
    } finally {
      try { await this.call(0x56, be32(job)); } catch (e) { if (!headerOnly) throw e; }
    }
  }
  /** write a body to /samples/(RAW_FIRST + k); progress(sent, total) */
  async write(k: number, body: Uint8Array, cardBytes: number, progress?: (a: number, b: number) => void): Promise<void> {
    if (k < 0x600 || k >= 0x2000) throw new Error("not a high-zone window");
    if (!body.length || k * WINDOW + body.length > Math.min(cardBytes, 2 ** 32)) throw new Error("write passes card boundary");
    const n = RAW_FIRST + k, obj = objectPack(n, body);
    let rx = await this.call(0x57, concat(be32(obj.length), ascii(`/samples/${n}`), Uint8Array.of(0)));
    const job = u32(rx, 6);
    let sent = 0, seq = 0;
    try {
      for (const part of [obj.subarray(0, obj.length - 12), obj.subarray(obj.length - 12)]) {
        for (let off = 0; off < part.length; off += this.block) {
          const chunk = part.subarray(off, off + this.block);
          rx = await this.call(0x58, concat(be32(job), be32(seq), be32(crc(chunk)), be32(chunk.length), chunk));
          sent += chunk.length;
          if (u32(rx, 6) !== job || u32(rx, 10) !== seq || u32(rx, 14) !== sent) throw new Error("write acknowledgment differs");
          seq++;
          progress?.(sent, obj.length);
        }
      }
    } catch (e) {
      try { await this.call(0x59, concat(be32(job), be32(obj.length))); } catch { /* keep the first error */ }
      throw e;
    }
    rx = await this.call(0x59, concat(be32(job), be32(obj.length)));
    if (u32(rx, 6) !== job || u32(rx, 10) !== obj.length) throw new Error("write close was not confirmed");
  }
}
