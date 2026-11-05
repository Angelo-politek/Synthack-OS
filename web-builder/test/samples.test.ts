// Long-sample uploader (Synfact's protocol, src/core/datarpc.ts, hzfs.ts, wav.ts) against a device double: Data RPC
// 0x54..0x59 over an in-memory card, high-zone windows as mods/long-samples routes them, OS 1.42's "Reader did not
// complete" on an early close. The disk format against the device's own C code: tests/test_long_samples.py.

import assert from "node:assert/strict";
import { test } from "node:test";
import { crc32 as zcrc } from "node:zlib";
import { readFileSync } from "node:fs";
import { concat, crc32, DataClient, decode87, encode87, HDR, objectPack, objectUnpack, RAW_FIRST, Transport, u32, WINDOW, be32, type Link } from "../src/core/datarpc.ts";
import { Index, Store } from "../src/core/hzfs.ts";
import { catalogueName, readWav, sampBody, wavBody } from "../src/core/wav.ts";
import { bodySamples, PAGE, peaks, POOL_PAGES, stockBytes, usage } from "../src/core/sampedit.ts";

const CARD = 0x3100_0000 + 40 * WINDOW;          // high zone: 40 data windows after the catalogues

class FakeSyntakt implements Link {
  card = new Map<number, Uint8Array>();           // window -> bytes
  private fn: (m: Uint8Array) => void = () => {};
  private jobs = new Map<number, { k: number; obj?: Uint8Array; pos: number; buf?: number[]; total?: number }>();
  private next = 1;
  early = 0;
  onMessage(fn: (m: Uint8Array) => void) { this.fn = fn; }
  send(msg: Uint8Array) {
    const rx = decode87(msg.subarray(HDR.length, msg.length - 1));
    const seq = rx.subarray(0, 2), kind = rx[4], p = rx.subarray(5);
    const reply = (okb: boolean, body: Uint8Array) =>
      queueMicrotask(() => this.fn(concat(HDR, encode87(concat(Uint8Array.of(0, 0), seq, Uint8Array.of(kind | 128, okb ? 1 : 0), body)), Uint8Array.of(0xf7))));
    const fail = (s: string) => reply(false, concat(new TextEncoder().encode(s), Uint8Array.of(0)));
    const window = (path: string) => {
      const n = Number(path.replace("/samples/", "")), k = n - RAW_FIRST;
      return k >= 0x600 && k < 0x2000 ? k : -1;
    };
    if (kind === 0x54 || kind === 0x57) {
      const text = kind === 0x54 ? p : p.subarray(4);
      const path = new TextDecoder().decode(text.subarray(0, text.indexOf(0)));
      const k = window(path);
      if (k < 0) return fail("not found");
      const job = this.next++;
      if (kind === 0x54) {
        const start = k * WINDOW, left = Math.max(0, Math.min(WINDOW, CARD - start));
        const body = (this.card.get(k) ?? new Uint8Array(WINDOW)).subarray(0, left);
        this.jobs.set(job, { k, obj: objectPack(RAW_FIRST + k, body), pos: 0 });
      } else {
        this.jobs.set(job, { k, pos: 0, buf: [], total: u32(p, 0) });
      }
      return reply(true, be32(job));
    }
    const job = this.jobs.get(u32(p, 0));
    if (!job) return fail("no job");
    if (kind === 0x55) {
      const block = 2048, chunk = job.obj!.subarray(job.pos, job.pos + block);
      job.pos += chunk.length;
      const meta = new Uint8Array(13);                                 // rx 10..22; size at 23, data at 27
      meta[8] = job.pos >= job.obj!.length ? 1 : 0;                   // rx[18]: last
      return reply(true, concat(be32(u32(p, 0)), meta, be32(chunk.length), chunk));
    }
    if (kind === 0x56) {
      this.jobs.delete(u32(p, 0));
      if (job.pos < job.obj!.length) { this.early++; return fail("Reader did not complete"); }
      return reply(true, new Uint8Array());
    }
    if (kind === 0x58) {
      const s = u32(p, 4), len = u32(p, 12), chunk = p.subarray(16, 16 + len);
      if (crc32(chunk, 0xffffffff) !== u32(p, 8)) return fail("chunk CRC");
      job.buf!.push(...chunk);
      return reply(true, concat(be32(u32(p, 0)), be32(s), be32(job.buf!.length)));
    }
    if (kind === 0x59) {
      this.jobs.delete(u32(p, 0));
      const body = objectUnpack(Uint8Array.from(job.buf!), RAW_FIRST + job.k);
      for (let o = 0; o < body.length; o += WINDOW) {
        const w = new Uint8Array(WINDOW);
        w.set(body.subarray(o, o + WINDOW));
        this.card.set(job.k + o / WINDOW, w);
      }
      return reply(true, concat(be32(u32(p, 0)), be32(job.buf!.length)));
    }
    fail("bad kind");
  }
}

function setup() {
  const dev = new FakeSyntakt();
  return { dev, store: new Store(new DataClient(new Transport(dev, 2000))) };
}

test("crc, 8-in-7 and Data objects", () => {
  const data = Uint8Array.from({ length: 999 }, (_, i) => (i * 37) & 255);
  assert.equal(crc32(data), zcrc(data));
  assert.equal(crc32(data, 0xffffffff), zcrc(data, 0xffffffff));
  assert.deepEqual(decode87(encode87(data)), data);
  assert.ok(encode87(data).every((b) => b < 128));
  assert.deepEqual(objectUnpack(objectPack(8800, data), 8800), data);
});

test("capacity, catalogues, put with readback, slots, remove", async () => {
  const { dev, store } = setup();
  assert.equal(await store.capacity(), Math.floor(CARD / WINDOW));
  assert.ok(dev.early > 0);                                         // the probes closed early: tolerated
  const pcm = new Float32Array(48000 * 2.5).map((_, i) => Math.sin(i / 7) * 0.5);
  const body = sampBody(pcm, "pad");
  const e = await store.put("pad 12", body);
  assert.equal(e.first, 0x602);
  assert.equal(e.frames, pcm.length);
  assert.equal(e.blocks, Math.ceil(body.length / WINDOW));
  await assert.rejects(store.put("pad 12", body), /already exists/);
  const e2 = await store.put("second", sampBody(new Float32Array(1000), "s"));
  assert.equal(e2.first, e.first + e.blocks);
  let { index, copies } = await store.current();
  assert.equal(index.entries.length, 2);
  assert.ok(copies[0] && copies[1]);                                 // A/B alternate
  await store.setSlots([e2.id, e.id, ...new Array(62).fill(0)]);
  ({ index } = await store.current());
  assert.deepEqual(index.slotMap.slice(0, 3), [e2.id, e.id, 0]);
  await store.remove(e2.id);
  ({ index } = await store.current());
  assert.deepEqual(index.entries.map((x) => x.name), ["pad 12"]);
  assert.deepEqual(index.slotMap.slice(0, 2), [0, e.id]);
  assert.deepEqual(await store.readBlocks(e.first, e.blocks, e.bytes), body);
});

test("catalogue written by the device's C code reads and packs back byte for byte", () => {
  const raw = new Uint8Array(readFileSync(new URL("./fixtures/hzfs-catalogue.bin", import.meta.url)));
  const ix = Index.unpack(raw)!;
  assert.ok(ix);
  assert.equal(ix.entries[0].name, "pad-12s");
  assert.equal(ix.entries[0].frames, 12 * 48000);
  assert.deepEqual(ix.pack(), raw.subarray(0, ix.pack().length));
});

test("WAV: 16-bit stereo 44.1 kHz to 48 kHz mono, names", () => {
  const n = 4410, ch = 2, data = new Uint8Array(44 + n * ch * 2), dv = new DataView(data.buffer);
  const s = (o: number, t: string) => [...t].forEach((c, i) => (data[o + i] = c.charCodeAt(0)));
  s(0, "RIFF"); dv.setUint32(4, 36 + n * 4, true); s(8, "WAVE"); s(12, "fmt "); dv.setUint32(16, 16, true);
  dv.setUint16(20, 1, true); dv.setUint16(22, ch, true); dv.setUint32(24, 44100, true); dv.setUint32(28, 44100 * 4, true);
  dv.setUint16(32, 4, true); dv.setUint16(34, 16, true); s(36, "data"); dv.setUint32(40, n * 4, true);
  for (let i = 0; i < n; i++) { dv.setInt16(44 + 4 * i, 16384, true); dv.setInt16(46 + 4 * i, 0, true); }
  const { rate, mono } = readWav(data);
  assert.equal(rate, 44100);
  assert.equal(mono.length, n);
  assert.ok(Math.abs(mono[10] - 0.25) < 1e-6);
  const body = wavBody(data, "x");
  assert.equal(u32(body, 8), Math.floor(n * 48000 / 44100));
  assert.equal(new DataView(body.buffer).getInt16(64 + 200), 8192);
  const used = new Set<string>();
  assert.equal(catalogueName("Avant - D&B 01 MagMag Vocal - 8 bar - 04 (175BPM).wav", used), "Avant - D&B 01 MagMag Vocal - 8");
  assert.equal(catalogueName("Avant - D&B 01 MagMag Vocal - 8 bar - 05.wav", used), "Avant - D&B 01 MagMag Vocal -~2");
});

test("rename, body read back", async () => {
  const { store } = setup();
  const pcm = new Float32Array(48000).map((_, i) => Math.sin(i / 5) * 0.25);
  const e = await store.put("loop", sampBody(pcm, "loop"));
  await store.put("other", sampBody(new Float32Array(100), "o"));
  await assert.rejects(store.rename(e.id, "other"), /already exists/);
  await assert.rejects(store.rename(e.id, "x".repeat(33)), /1..32/);
  await store.rename(e.id, "loop 2");
  const { index } = await store.current();
  assert.equal(index.entries.find((x) => x.id === e.id)!.name, "loop 2");
  const back = bodySamples(await store.body(e.id));
  assert.equal(back.length, pcm.length);
  assert.ok(back.every((v, i) => Math.abs(v - pcm[i]) < 1 / 32768 + 1e-9));
});

test("voice memory at boot as ls_plan fills it; waveform peaks", () => {
  const ent = (id: number, mb: number) => ({ id, first: 0, blocks: 0, bytes: mb * 2 ** 20, frames: 0, crc: 0, created: 0, flags: 0, name: `s${id}` });
  const u = usage(stockBytes([64 + 2 * 48000, 0, 64 + 2 * 1000]), [ent(1, 10), ent(2, 40), ent(3, 20)]);
  assert.equal(u.stockPages, Math.ceil((4 + 96000 + 4 + 2000) / PAGE));
  assert.deepEqual(u.files.map((f) => f.loads), [true, true, false]);       // 10 + 40 fit, 20 more don't
  assert.equal(u.freePages, POOL_PAGES - u.stockPages - 1 - u.files[0].pages - u.files[1].pages);
  const p = peaks(Float32Array.from([0, 0.5, -1, 0.25]), 2);
  assert.deepEqual([...p], [0.5, 1]);
});
