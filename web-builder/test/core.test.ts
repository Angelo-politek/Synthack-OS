// Test senza firmware: primitive contro node:crypto, compressori andata e ritorno, un contenitore ELE3 finto
// (con e senza coda HMAC) ricostruito e riletto. La parita' con build.py sull'OS vero sta in
// tests/test_web_builder.py (serve l'OS stock in locale).

import { createHash, createHmac } from "node:crypto";
import assert from "node:assert/strict";
import { test } from "node:test";
import { depack, depackMargin, pack } from "../src/core/aplib.ts";
import { resolve, BuildError, type ModSpec } from "../src/core/build.ts";
import { contentChecksum, Firmware } from "../src/core/firmware.ts";
import { hex, hmacSha256, sha256, Sha256 } from "../src/core/sha256.ts";
import * as shlz from "../src/core/shlz.ts";
import { decode, encode } from "../src/core/transport.ts";

function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) >>> 24);
}

/** Dati simili a codice: blocchi ripetuti a distanze vicine e lontane, rumore, zeri. */
function codeLike(n: number, seed = 1): Uint8Array {
  const r = rng(seed), d = new Uint8Array(n);
  for (let i = 0; i < n;) {
    const k = r() % 4, L = 1 + (r() % 40);
    if (k === 0 || i < 16) for (let j = 0; j < L && i < n; j++) d[i++] = r();
    else if (k === 1) for (let j = 0; j < L && i < n; j++) d[i++] = 0;
    else {
      const back = 1 + ((r() << 8 | r()) % Math.min(i, k === 2 ? 64 : 200_000));
      for (let j = 0; j < L && i < n; j++, i++) d[i] = d[i - back];
    }
  }
  return d;
}

const samples: [string, Uint8Array][] = [
  ["one byte", new Uint8Array([0x42])],
  ["zeros", new Uint8Array(70_000)],
  ["random", Uint8Array.from({ length: 5000 }, rng(7))],
  ["code-like", codeLike(100_000)],
  ["text", new TextEncoder().encode("SYNTHACK ".repeat(500) + "the quick brown fox ".repeat(300))],
];

test("SHA-256 and HMAC match node:crypto", () => {
  for (const n of [0, 1, 55, 56, 63, 64, 65, 119, 120, 100_000]) {
    const d = Uint8Array.from({ length: n }, rng(n));
    assert.equal(hex(sha256(d)), createHash("sha256").update(d).digest("hex"));
    const k = Uint8Array.from({ length: 32 }, rng(n + 1));
    assert.equal(hex(hmacSha256(k, d)), createHmac("sha256", k).update(d).digest("hex"));
    const inc = new Sha256().update(d.subarray(0, n >> 1)).update(d.subarray(n >> 1)).digest();
    assert.equal(hex(inc), hex(sha256(d)));
  }
});

test("aPLib: pack then depack gives the input back, at every level", () => {
  for (const [name, d] of samples)
    for (const level of [0, 3]) {
      const z = pack(d, level);
      assert.deepEqual(depack(z, false), d, `${name}, level ${level}`);
      assert.equal(depackMargin(z).size, d.length, `${name}: the boot check walks the whole stream`);
      const dv = new DataView(z.buffer);
      assert.equal(dv.getUint32(0), z.length - 8);
      assert.equal(dv.getUint32(4), z.subarray(8).reduce((a, b) => (a + b) >>> 0, 0));
    }
});

test("aPLib: higher levels never compress worse", () => {
  const d = codeLike(60_000, 3);
  const sizes = [0, 1, 2, 3].map((l) => pack(d, l).length);
  for (let l = 1; l < 4; l++) assert.ok(sizes[l] <= sizes[l - 1], sizes.join(" "));
});

test("aPLib: a stream that copies from before its start is rejected", () => {
  // bit 0 (copia), gamma 3 ("11"), byte 0 -> distanza 1, lunghezza "01": nulla ancora in uscita
  const bad = new Uint8Array([0, 0, 0, 2, 0, 0, 0, 0x68, 0x68, 0x00]);
  assert.equal(depack(bad, false), null);
  assert.equal(depack(bad, true), null);
});

test("aPLib: the boot margin falls when output catches up with input", () => {
  const z = pack(new Uint8Array(300_000), 0);          // zeri: quasi niente in ingresso, tanto in uscita
  const { margin } = depackMargin(z);
  assert.ok(margin < 0x1ffc00 - 290_000 && margin > 0x1ffc00 - 300_000, String(margin));
});

test("SHLZ: compress then decompress gives the input back", () => {
  for (const [name, d] of samples) assert.deepEqual(shlz.decompress(shlz.compress(d)), d, name);
  assert.deepEqual(shlz.decompress(shlz.compress(new Uint8Array(0))), new Uint8Array(0));
});

test("SysEx: encode then decode round trip, every packet checksum valid", () => {
  const c = codeLike(5000, 9), pre = new Uint8Array(8);
  const syx = encode(c, pre, 0x16, 0x10, null);
  const t = decode(syx);
  assert.equal(t.device, 0x16);
  assert.equal(t.pktBad, 0);
  assert.equal(t.pktOk, t.ndata);
  assert.deepEqual(t.stream.subarray(8, 8 + c.length), c);
});

/** Contenitore ELE3 finto: sezioni compresse e grezze, chiave HMAC facoltativa ricavata dalla sezione 3. */
function fakeImage(hmac: boolean): { syx: Uint8Array; s3: Uint8Array; s7: Uint8Array } {
  const s3 = codeLike(60_000, 11), s7 = codeLike(3000, 12);
  if (hmac) {
    const mat = [0xbe, 0xf9, 0xa3, 0xf7, 0xc6, 0x71, 0x78, 0xf2, ...new TextEncoder().encode("Fake device key"), 0];
    s3.set(mat, 1000);
    s3.set(Uint8Array.from({ length: 32 }, rng(5)), 1000 + mat.length);
  }
  const ids = [5, 3, 7], bodies = [new TextEncoder().encode("20260101T000000"), pack(s3), s7];
  const head = new Uint8Array(0x20 + 16 * ids.length);
  head.set(new TextEncoder().encode("ELE3\0\0\0Syntakt 1.41"));
  new DataView(head.buffer).setUint32(0x1c, ids.length);
  const parts: number[] = [...head];
  ids.forEach((id, i) => {
    while (parts.length % 16) parts.push(0);
    const dv = new DataView(head.buffer, 0x20 + 16 * i);
    dv.setUint32(0, id);
    dv.setUint32(4, parts.length);
    dv.setUint32(8, bodies[i].length);
    parts.push(...bodies[i]);
  });
  let c = Uint8Array.from(parts);
  c.set(head);
  if (hmac) {
    const off = (c.length + 4 + 15) & ~15, nc = new Uint8Array(off + 32);
    nc.set(c);
    // stessa derivazione del tool: sha(s) ^ sha(reverse(s)) ^ costante
    const s = new TextEncoder().encode("Fake device key"), cst = s3.subarray(1000 + 24, 1000 + 56);
    const key = sha256(s).map((x, i) => x ^ sha256(s.slice().reverse())[i] ^ cst[i]);
    nc.set(hmacSha256(key, nc.subarray(0, off)), off);
    c = nc;
  } else {
    const nc = new Uint8Array((c.length + 15) & ~15);
    nc.set(c);
    c = nc;
  }
  const pre = new Uint8Array(8), dv = new DataView(pre.buffer);
  dv.setUint32(0, c.length);
  dv.setUint32(4, contentChecksum(c, c.length));
  return { syx: encode(c, pre, 0x16, 0x10, null), s3, s7 };
}

for (const hmac of [false, true])
  test(`ELE3 ${hmac ? "with" : "without"} HMAC trailer: parse, verify, rebuild with new sections`, () => {
    const { syx, s3, s7 } = fakeImage(hmac);
    const fw = new Firmware(syx);
    assert.equal(fw.version, "1.41");
    assert.equal(!!fw.key, hmac);
    assert.deepEqual(fw.verify(), { ok: true, problems: [] });
    assert.deepEqual(fw.extract(3), s3);
    assert.deepEqual(fw.extract(7), s7);

    const n3 = s3.slice(), n7 = s7.slice();
    n3[30_000] ^= 0xff;
    n7[10] ^= 0xff;
    const out = new Firmware(fw.rebuild(new Map([[3, n3], [7, n7]])));
    assert.deepEqual(out.verify(), { ok: true, problems: [] });
    assert.equal(!!out.key, hmac);
    assert.deepEqual(out.extract(3), n3);
    assert.deepEqual(out.extract(7), n7, "a raw section stays raw");
    assert.deepEqual(out.extract(5), fw.extract(5));

    const same = fw.rebuild(new Map());
    assert.deepEqual(same, syx, "nothing replaced: the same file");

    const broken = out.raw.slice();
    broken[5000] ^= 1;
    assert.equal(new Firmware(broken).verify().ok, false);
  });

const spec = (name: string, requires?: string[]): ModSpec => ({ name, os: "1.41", requires, patches: [] });

test("dependencies: added before the mods that need them", () => {
  const specs = { a: spec("a", ["infra"]), b: spec("b", ["infra", "store"]), infra: spec("infra"), store: spec("store", ["infra"]) };
  assert.deepEqual(resolve(["b", "a"], specs), { order: ["infra", "store", "b", "a"], added: ["infra", "store"] });
  assert.throws(() => resolve(["x"], { x: spec("x", ["y"]), y: spec("y", ["x"]) }), BuildError);
  assert.throws(() => resolve(["x"], { x: spec("x", ["missing"]) }), /missing not found/);
});
