// SPDX-License-Identifier: GPL-2.0-or-later
// HZFS long-sample catalogue and transactions over Data RPC: port of Synfact's sample_catalog.py and the Store of
// long_samples.py (GSM1980, on elekloader by irpina). Same disk format as the device's hzfs.c (mods/long-samples).
// Catalogue v1 and v2 are read; folders are kept as they are but not edited here.

import { crc, DataClient, u32, WINDOW } from "./datarpc.ts";

export const HZ_FIRST_K = 0x600, INDEX_K = [0x600, 0x601], DATA_FIRST_K = 0x602;
const ENTRIES_OFF = 0x140, ENTRY = 64, FOLDER_BYTES = 48;
export const MAX_ENTRIES = (WINDOW - ENTRIES_OFF) / ENTRY;
export const RATE = 48000;

export interface Entry {
  id: number; first: number; blocks: number; bytes: number; frames: number; crc: number; created: number; flags: number;
  name: string; folder?: number;
}

function logicalLength(version: number, count: number, folders = 0): number {
  if ((version !== 1 && version !== 2) || count < 0 || count > MAX_ENTRIES) throw new Error("unsupported catalogue");
  const size = ENTRIES_OFF + count * ENTRY + (version === 2 ? count * 4 + folders * FOLDER_BYTES : 0);
  if (size > WINDOW || (version === 1 && folders)) throw new Error("sample catalogue full");
  return size;
}

const enc = new TextEncoder(), dec = new TextDecoder();

export class Index {
  seq = 0; windows = 0; nextId = 1; entries: Entry[] = []; slotMap: number[] = new Array(64).fill(0);
  version = 1; folderRaw: Uint8Array = new Uint8Array(); folderCount = 0; nextFolder = 1;

  pack(): Uint8Array {
    const n = this.entries.length, f = this.folderCount;
    const raw = new Uint8Array(logicalLength(this.version, n, f));
    const v = new DataView(raw.buffer);
    [this.version, this.seq, n, WINDOW, DATA_FIRST_K, this.windows, this.nextId, 0, raw.length]
      .forEach((x, i) => v.setUint32(4 + 4 * i, x >>> 0));
    this.slotMap.forEach((x, i) => v.setUint32(64 + 4 * i, x >>> 0));
    if (this.version === 2) { v.setUint32(40, f); v.setUint32(44, this.nextFolder); }
    this.entries.forEach((e, i) => {
      const at = ENTRIES_OFF + ENTRY * i, name = enc.encode(e.name);
      if (name.length < 1 || name.length > 32 || name.includes(0)) throw new Error("sample name must use 1..32 UTF-8 bytes");
      [e.id, e.first, e.blocks, e.bytes, e.frames, e.crc, e.created, e.flags].forEach((x, k) => v.setUint32(at + 4 * k, x >>> 0));
      raw.set(name, at + 32);
      if (this.version === 2) v.setUint32(ENTRIES_OFF + ENTRY * n + 4 * i, e.folder ?? 0);
    });
    if (this.version === 2) raw.set(this.folderRaw, ENTRIES_OFF + 68 * n);
    raw.set([0x48, 0x5a, 0x46, 0x53], 0);                     // HZFS
    v.setUint32(32, crc(raw));
    return raw;
  }

  static unpack(raw: Uint8Array): Index | null {
    try {
      if (raw.length < ENTRIES_OFF || dec.decode(raw.subarray(0, 4)) !== "HZFS") return null;
      const w = (o: number) => u32(raw, o);
      const [version, seq, n, block, first, windows, nextId, check, size] = [4, 8, 12, 16, 20, 24, 28, 32, 36].map(w);
      const f = version === 2 ? w(40) : 0, nextFolder = version === 2 ? w(44) : 1;
      if (block !== WINDOW || first !== DATA_FIRST_K || size !== logicalLength(version, n, f) || size > raw.length) return null;
      const copy = raw.slice(0, size);
      copy.fill(0, 32, 36);
      if (crc(copy) !== check) return null;
      const ix = new Index();
      Object.assign(ix, { version, seq, windows, nextId, folderCount: f, nextFolder });
      for (let i = 0; i < n; i++) {
        const at = ENTRIES_OFF + ENTRY * i, nm = raw.subarray(at + 32, at + 64), end = nm.indexOf(0);
        const e: Entry = {
          id: w(at), first: w(at + 4), blocks: w(at + 8), bytes: w(at + 12), frames: w(at + 16), crc: w(at + 20),
          created: w(at + 24), flags: w(at + 28), name: dec.decode(nm.subarray(0, end < 0 ? 32 : end)),
        };
        if (version === 2) e.folder = w(ENTRIES_OFF + ENTRY * n + 4 * i);
        ix.entries.push(e);
      }
      if (version === 2) ix.folderRaw = raw.slice(ENTRIES_OFF + 68 * n, ENTRIES_OFF + 68 * n + FOLDER_BYTES * f);
      ix.slotMap = Array.from({ length: 64 }, (_, i) => w(64 + 4 * i));
      return ix;
    } catch {
      return null;
    }
  }

  used(): [number, number][] { return this.entries.map((e) => [e.first, e.first + e.blocks]); }

  problems(): string[] {
    const out: string[] = [], names = new Set<string>(), ids = new Set<number>(), spans: [number, number][] = [];
    if (!(this.seq > 0 && this.windows > DATA_FIRST_K && this.windows <= 0x2000 && this.nextId > 0)) out.push("invalid catalogue header");
    for (const e of this.entries) {
      if (!(DATA_FIRST_K <= e.first && e.first < e.first + e.blocks && e.first + e.blocks <= this.windows)) out.push(`${e.name}: outside the data area`);
      if (e.blocks !== Math.ceil(e.bytes / WINDOW) || e.bytes !== 64 + 2 * e.frames) out.push(`${e.name}: size fields inconsistent`);
      const key = `${e.folder ?? 0}/${e.name}`;
      if (names.has(key) || ids.has(e.id)) out.push(`${e.name}: duplicate name or id`);
      names.add(key); ids.add(e.id);
      if (!e.id || e.id >= this.nextId) out.push(`${e.name}: bad id`);
      spans.push([e.first, e.first + e.blocks]);
    }
    spans.sort((a, b) => a[0] - b[0]);
    for (let i = 1; i < spans.length; i++) if (spans[i][0] < spans[i - 1][1]) out.push("extents overlap");
    this.slotMap.forEach((id, s) => { if (id && !ids.has(id)) out.push(`slot ${65 + s} -> missing id ${id}`); });
    return out;
  }
}

/** first fit over the blocks free in every valid copy */
export function allocate(blocks: number, copies: (Index | null)[], windows: number): number {
  const used = copies.flatMap((c) => (c ? c.used() : [])).sort((a, b) => a[0] - b[0]);
  let k = DATA_FIRST_K;
  for (const [lo, hi] of used) {
    if (lo - k >= blocks) return k;
    k = Math.max(k, hi);
  }
  if (windows - k >= blocks) return k;
  throw new Error(`no ${blocks} contiguous free blocks (${(blocks * WINDOW / 2 ** 20).toFixed(1)} MiB)`);
}

export function freeSpace(copies: (Index | null)[], windows: number): { free: number; largest: number } {
  const spans = copies.flatMap((c) => (c ? c.used() : [])).sort((a, b) => a[0] - b[0]);
  let at = DATA_FIRST_K, free = 0, largest = 0;
  for (const [lo, hi] of spans) {
    const hole = Math.max(0, lo - at);
    free += hole; largest = Math.max(largest, hole); at = Math.max(at, hi);
  }
  const hole = Math.max(0, windows - at);
  return { free: (free + hole) * WINDOW, largest: Math.max(largest, hole) * WINDOW };
}

export class Store {
  windows = 0; cardBytes = 0;
  client: DataClient;
  log: (s: string) => void;
  constructor(client: DataClient, log: (s: string) => void = () => {}) {
    this.client = client;
    this.log = log;
  }

  async capacity(): Promise<number> {
    if (this.windows) return this.windows;
    const size = (k: number) => this.client.read(k, true) as Promise<number>;
    if ((await size(HZ_FIRST_K)) !== WINDOW) throw new Error("high-zone storage unavailable: is long-samples in the build?");
    let lo = HZ_FIRST_K, hi = 0x2000;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (await size(mid)) lo = mid; else hi = mid;
    }
    const last = await size(lo);
    if (!(last > 0 && last <= WINDOW) || last % 512) throw new Error("invalid card geometry");
    this.cardBytes = lo * WINDOW + last;
    this.windows = Math.floor(this.cardBytes / WINDOW);
    if (this.windows <= DATA_FIRST_K) throw new Error("no high-zone sample space");
    return this.windows;
  }

  private async window(k: number): Promise<Uint8Array> { return this.client.read(k) as Promise<Uint8Array>; }

  private async writeAt(k: number, body: Uint8Array, progress?: (a: number, b: number) => void): Promise<void> {
    await this.capacity();
    if (k < HZ_FIRST_K || !body.length || k * WINDOW + body.length > this.windows * WINDOW) throw new Error("write outside the high zone");
    await this.client.write(k, body, this.cardBytes, progress);
  }

  async readBlocks(first: number, count: number, length: number, progress?: (a: number, b: number) => void): Promise<Uint8Array> {
    await this.capacity();
    if (first < DATA_FIRST_K || first + count > this.windows || !(length > 0 && length <= count * WINDOW)) throw new Error("read outside the data");
    const out = new Uint8Array(length);
    let o = 0;
    for (let k = first; k < first + count; k++) {
      const chunk = await this.window(k);
      if (chunk.length !== WINDOW) throw new Error("short storage window");
      const n = Math.min(WINDOW, length - o);
      out.set(chunk.subarray(0, n), o);
      o += n;
      progress?.(o, length);
    }
    return out;
  }

  async copies(): Promise<{ copies: (Index | null)[]; raws: Uint8Array[] }> {
    const cap = await this.capacity(), copies: (Index | null)[] = [], raws: Uint8Array[] = [];
    for (const k of INDEX_K) {
      const raw = await this.window(k);
      if (raw.length !== WINDOW) throw new Error("short catalogue read");
      const ix = Index.unpack(raw);
      if (ix && (ix.problems().length || ix.windows > cap)) throw new Error("CRC-valid catalogue contains inconsistent entries");
      copies.push(ix); raws.push(raw);
    }
    return { copies, raws };
  }

  async ensure(): Promise<void> {
    const { copies, raws } = await this.copies();
    if (copies.some(Boolean)) return;
    if (raws.some((r) => r.some((b) => b !== 0 && b !== 255))) throw new Error("unknown catalogue data: formatting refused");
    const ix = new Index();
    ix.seq = 1; ix.windows = await this.capacity();
    const body = ix.pack();
    for (const k of INDEX_K) {
      await this.writeAt(k, body);
      if (!eq((await this.window(k)).subarray(0, body.length), body)) throw new Error("catalogue readback differs");
    }
    this.log("HZFS created in empty high-zone storage");
  }

  async current(): Promise<{ index: Index; copies: (Index | null)[] }> {
    const { copies } = await this.copies();
    const valid = copies.filter((c): c is Index => !!c);
    if (!valid.length) throw new Error("no valid HZFS catalogue");
    return { index: valid.reduce((a, b) => (b.seq > a.seq ? b : a)), copies };
  }

  async commit(index: Index, copies: (Index | null)[]): Promise<void> {
    const seqs = copies.map((c) => (c ? c.seq : 0));
    if (Math.max(...seqs) === 0xffffffff) throw new Error("catalogue sequence exhausted");
    const target = seqs[0] <= seqs[1] ? 0 : 1;
    index.seq = Math.max(...seqs) + 1;
    const p = index.problems();
    if (p.length) throw new Error(`inconsistent catalogue: ${p.join("; ")}`);
    const body = index.pack();
    await this.writeAt(INDEX_K[target], body);
    const back = await this.window(INDEX_K[target]);
    if (!eq(back.subarray(0, body.length), body) || !Index.unpack(back)) throw new Error("catalogue commit readback differs");
  }

  /** a SAMP body (64-byte header + PCM16BE mono 48 kHz) under name; progress(sent, total) */
  async put(name: string, body: Uint8Array, progress?: (a: number, b: number) => void): Promise<Entry> {
    if (!name || enc.encode(name).length > 32 || name.includes("\0")) throw new Error("name must be 1..32 UTF-8 bytes");
    await this.ensure();
    const { index, copies } = await this.current();
    if (index.entries.length >= MAX_ENTRIES || index.nextId === 0xffffffff) throw new Error("catalogue full");
    logicalLength(index.version, index.entries.length + 1, index.folderCount);
    if (index.entries.some((e) => e.name === name && (e.folder ?? 0) === 0)) throw new Error(`"${name}" already exists`);
    const blocks = Math.ceil(body.length / WINDOW), first = allocate(blocks, copies, index.windows);
    await this.writeAt(first, body, progress);
    if (!eq(await this.readBlocks(first, blocks, body.length), body)) throw new Error("sample readback differs; catalogue unchanged");
    const e: Entry = {
      id: index.nextId, first, blocks, bytes: body.length, frames: u32(body, 8), crc: crc(body),
      created: Math.floor(Date.now() / 1000) >>> 0, flags: 0, name,
    };
    if (index.version === 2) e.folder = 0;
    index.entries.push(e);
    index.nextId++;
    await this.commit(index, copies);
    this.log(`Stored ${name}: ${(e.frames / RATE).toFixed(1)} s`);
    return e;
  }

  async remove(id: number): Promise<void> {
    const { index, copies } = await this.current();
    const i = index.entries.findIndex((e) => e.id === id);
    if (i < 0) throw new Error("sample not found");
    index.entries.splice(i, 1);
    index.slotMap = index.slotMap.map((x) => (x === id ? 0 : x));
    await this.commit(index, copies);
  }

  async rename(id: number, name: string): Promise<void> {
    if (!name || enc.encode(name).length > 32 || name.includes("\0")) throw new Error("name must be 1..32 UTF-8 bytes");
    const { index, copies } = await this.current();
    const e = index.entries.find((x) => x.id === id);
    if (!e) throw new Error("sample not found");
    if (e.name === name) return;
    if (index.entries.some((x) => x !== e && x.name === name && (x.folder ?? 0) === (e.folder ?? 0))) throw new Error(`"${name}" already exists`);
    e.name = name;
    await this.commit(index, copies);
  }

  /** the SAMP body of a stored sample (read back over MIDI: slow, ~5 s for 10 s of audio) */
  async body(id: number, progress?: (a: number, b: number) => void): Promise<Uint8Array> {
    const { index } = await this.current();
    const e = index.entries.find((x) => x.id === id);
    if (!e) throw new Error("sample not found");
    return this.readBlocks(e.first, e.blocks, e.bytes, progress);
  }

  /** L1..L64 -> ids (0 = empty); all zero: the device plays the catalogue order */
  async setSlots(map: number[]): Promise<void> {
    const { index, copies } = await this.current();
    if (map.length !== 64) throw new Error("64 positions");
    index.slotMap = map.slice();
    await this.commit(index, copies);
  }
}

function eq(a: Uint8Array, b: Uint8Array): boolean {
  return a.length === b.length && a.every((x, i) => x === b[i]);
}
