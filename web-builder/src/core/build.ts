// Build delle mod sull'OS stock: port di tools/build/build.py, con le stesse regole e gli stessi controlli
// (impronte dei byte originali, sovrapposizioni, sezioni protette, area mod compressa, margine di avvio,
// confronto finale sezione per sezione). A parita' di mod l'uscita e' identica a quella di build.py.

import { depackMargin } from "./aplib.ts";
import { Firmware, SYNTAKT } from "./firmware.ts";
import { sha256hex } from "./sha256.ts";
import * as shlz from "./shlz.ts";
import { cleanName, namedSplash } from "./splash.ts";

const LOAD_ADDR = 0x4000_0400;            // sezioni 3 e 7 si caricano qui
const PATCHABLE = new Set([3, 7]);
const APPENDABLE = new Set([3]);          // sezione 7: limite del caricatore della CPU #2 da trovare
const PROTECTED = new Set([2, 6]);        // recovery: mai riscritte
export const MIN_MARGIN = 4096;           // tools/build/bootcheck.py
export const STOCK_SHA256: Record<string, string> = {
  "1.41": "8e2488f462c4a5656396a895f113bcd415e9900fa8709340dccf45d4cb9ed19e",
};

export interface PatchSpec {
  section: number;
  addr: string;
  len: number;
  expect_sha256?: string;
  append?: boolean;
  hex?: string;
  ascii?: string;
}

export interface ModSpec {
  name: string;
  os?: string;
  requires?: string[];
  layout?: Record<string, unknown>;
  patches: PatchSpec[];
}

export class BuildError extends Error {}

interface Patch {
  mod: string;
  section: number;
  addr: number;
  data: Uint8Array;
  expect: string;
  append: boolean;
  offset: number;
  end: number;
}

export interface Manifest {
  os: string;
  stock_sha256: string;
  mods: string[];
  output: string;
  output_sha256: string;
  boot_margin: number;
  splash_name?: string;
}

export interface Options {
  splashName?: string;     // nome sulla splash d'avvio (vuoto: la splash standard)
}

export const BASE_MODS = ["splash"];       // in ogni build del sito

export interface Progress {
  stage: "check" | "patch" | "compress" | "verify";
  done?: number;
  total?: number;
}

function fromHex(s: string): Uint8Array {
  s = s.replace(/ /g, "");
  if (s.length % 2 || /[^0-9a-fA-F]/.test(s)) throw new BuildError("invalid hex");
  const b = new Uint8Array(s.length / 2);
  for (let i = 0; i < b.length; i++) b[i] = parseInt(s.substr(2 * i, 2), 16);
  return b;
}

/** Mod in ordine (prima le dipendenze) e nomi di quelle aggiunte perche' richieste. */
export function resolve(names: string[], specs: Record<string, ModSpec>): { order: string[]; added: string[] } {
  const given = new Set(names);
  const order: string[] = [], added: string[] = [];
  const state = new Map<string, "busy" | "done">();
  const visit = (name: string, chain: string[]): void => {
    if (state.get(name) === "done") return;
    if (state.get(name) === "busy") throw new BuildError("circular dependencies: " + [...chain, name].join(" -> "));
    const spec = specs[name];
    if (!spec) throw new BuildError(`dependency ${name} not found`);
    state.set(name, "busy");
    for (const req of spec.requires ?? []) visit(req, [...chain, name]);
    state.set(name, "done");
    order.push(name);
    if (!given.has(name)) added.push(name);
  };
  for (const n of given) visit(n, []);
  return { order, added };
}

function loadMod(spec: ModSpec, os: string): Patch[] {
  const name = spec.name;
  if (spec.os !== os) throw new BuildError(`${name}: written for OS ${spec.os}, not ${os}`);
  return spec.patches.map((p, i) => {
    let data: Uint8Array;
    if (p.ascii !== undefined) data = new TextEncoder().encode(p.ascii);
    else if (p.hex !== undefined) data = fromHex(p.hex);
    else throw new BuildError(`${name}[${i}]: needs 'ascii' or 'hex'`);
    if (data.length !== p.len) throw new BuildError(`${name}[${i}]: ${data.length} new bytes but 'len' = ${p.len}`);
    if (!PATCHABLE.has(p.section)) throw new BuildError(`${name}[${i}]: section ${p.section} cannot be modified`);
    if (p.append && p.hex === undefined) throw new BuildError(`${name}[${i}]: an appended patch needs 'hex'`);
    const addr = parseInt(p.addr, 16), offset = addr - LOAD_ADDR;
    return { mod: name, section: p.section, addr, data, expect: p.append ? "" : (p.expect_sha256 ?? "").toLowerCase(),
             append: !!p.append, offset, end: offset + data.length };
  });
}

function modArea(specs: ModSpec[]): { img: number; size: number } | null {
  for (const s of specs) {
    const lay = s.layout ?? {};
    if (lay.compress === "shlz") return { img: parseInt(lay.img as string, 16), size: parseInt(lay.size as string, 16) };
  }
  return null;
}

function expectedArea(patches: Patch[], img: number): Uint8Array {
  let len = 0;
  for (const p of patches) if (p.append) len = Math.max(len, p.addr - img + p.data.length);
  const out = new Uint8Array(len);
  for (const p of patches) if (p.append) out.set(p.data, p.addr - img);
  return out;
}

const hexAddr = (a: number): string => "0x" + a.toString(16);

function applyPatches(sections: Map<number, Uint8Array>, patches: Patch[]): Map<number, Uint8Array> {
  const taken = new Map<number, Patch[]>();
  for (const p of patches) {
    const sec = sections.get(p.section);
    if (!sec) throw new BuildError(`${p.mod}: section ${p.section} not loaded`);
    for (const q of taken.get(p.section) ?? [])
      if (p.offset < q.end && q.offset < p.end) throw new BuildError(`${p.mod} and ${q.mod} modify the same bytes (${hexAddr(p.addr)})`);
    if (p.append) {
      if (!APPENDABLE.has(p.section)) throw new BuildError(`${p.mod}: appended patch to section ${p.section}: only section 3 for now`);
      if (p.offset < sec.length) throw new BuildError(`${p.mod}: appended patch at ${hexAddr(p.addr)} inside the stock section`);
    } else {
      if (p.offset < 0 || p.end > sec.length) throw new BuildError(`${p.mod}: ${hexAddr(p.addr)} outside section ${p.section}`);
      if (sha256hex(sec.subarray(p.offset, p.end)) !== p.expect)
        throw new BuildError(`${p.mod}: the original bytes at ${hexAddr(p.addr)} are not the expected ones (different OS or modified file)`);
    }
    taken.set(p.section, [...(taken.get(p.section) ?? []), p]);
  }
  const out = new Map<number, Uint8Array>();
  for (const [s, sec] of sections) {
    const end = Math.max(sec.length, ...patches.filter((p) => p.section === s).map((p) => p.end));
    const b = new Uint8Array(end);
    b.set(sec);
    for (const p of patches) if (p.section === s) b.set(p.data, p.offset);
    out.set(s, b);
  }
  return out;
}

export interface BuildResult {
  syx: Uint8Array;
  manifest: Manifest;
  log: string[];
}

/** stock: il .syx scaricato da elektron.se; mods: le mod scelte (le dipendenze si aggiungono da sole; la
 * splash c'e' sempre, prima delle altre, come in build.py quando la si indica per prima). */
export function build(stock: Uint8Array, mods: string[], specs: Record<string, ModSpec>, outName: string,
                      onProgress: (p: Progress) => void = () => {}, opts: Options = {}): BuildResult {
  const log: string[] = [];
  onProgress({ stage: "check" });
  const fw = new Firmware(stock);
  const version = fw.version;
  if (fw.device !== SYNTAKT || !fw.verify().ok) throw new BuildError("this is not a valid Syntakt OS file");
  const stockSha = sha256hex(stock);
  if (STOCK_SHA256[version] !== stockSha) throw new BuildError(`this is not the expected stock OS ${version} (different fingerprint)`);
  const { order, added } = resolve([...BASE_MODS.filter((b) => specs[b] && !mods.includes(b)), ...mods], specs);
  if (added.length) log.push(`dependencies added: ${added.join(", ")}`);
  const name = cleanName(opts.splashName ?? "");
  const modSpecs = order.map((n) => (n === "splash" ? namedSplash(specs[n], name) : specs[n]));
  const patches = modSpecs.flatMap((s) => loadMod(s, version));
  const needed = [...new Set(patches.map((p) => p.section))].sort((a, b) => a - b);

  onProgress({ stage: "patch" });
  const original = new Map(needed.map((s) => [s, fw.extract(s)]));
  const sections = applyPatches(original, patches);
  const area = modArea(modSpecs);
  let image: Uint8Array | null = null;
  if (area && sections.has(3) && sections.get(3)!.length > area.img - LOAD_ADDR) {
    const sec = sections.get(3)!, off = area.img - LOAD_ADDR;
    image = sec.slice(off);                                   // area mod come la vedra' la RAM
    if (image.length > area.size) throw new BuildError(`mod area: ${image.length} B, more than the ${area.size} B in RAM`);
    const z = shlz.compress(image);
    const b = new Uint8Array(off + z.length);
    b.set(sec.subarray(0, off));
    b.set(z, off);
    sections.set(3, b);
  }
  for (const s of sections.keys()) if (PROTECTED.has(s)) throw new BuildError(`section ${s} is protected (recovery)`);
  const syx = fw.rebuild(sections, 3, (_id, done, total) => onProgress({ stage: "compress", done, total }));

  // --- verifiche sul risultato
  onProgress({ stage: "verify" });
  const out = new Firmware(syx);
  if (!out.verify().ok || out.version !== version) throw new BuildError("the built .syx does not pass the checksum verification");
  const c = out.container(), s3 = out.section(3);
  const { margin } = depackMargin(c.subarray(s3.offset, s3.offset + s3.compLen));
  if (margin < MIN_MARGIN)
    throw new BuildError(`section 3 would not unpack at boot: margin ${margin} B (minimum ${MIN_MARGIN}); the Syntakt would hang on the logo`);
  log.push(`boot: decompression margin ${margin} B (minimum ${MIN_MARGIN})`);
  for (const { id } of fw.sections) {
    const old = fw.extract(id), neu = out.extract(id);
    if (!needed.includes(id)) {
      if (old.length !== neu.length || old.some((x, i) => x !== neu[i])) throw new BuildError(`section ${id} changed but no patch touches it`);
      continue;
    }
    const mine = patches.filter((p) => p.section === id);
    const allowed = new Uint8Array(Math.max(old.length, neu.length));
    for (const p of mine) allowed.fill(1, Math.max(0, p.offset), Math.min(allowed.length, p.end));
    let diff = 0, outside = false;
    for (let i = 0; i < old.length; i++)
      if (i >= neu.length || old[i] !== neu[i]) {
        diff++;
        if (!allowed[i]) outside = true;
      }
    let tail = false;
    if (image && area && id === 3) {                        // area compressa: confronto dopo la decompressione
      const off = area.img - LOAD_ADDR;
      const got = shlz.decompress(neu.subarray(off)), want = expectedArea(mine, area.img);
      if (got.length !== want.length || got.some((x, i) => x !== want[i]))
        throw new BuildError("mod area: the compressed stream does not reproduce the appended patches");
      for (let i = old.length; i < off; i++) if (neu[i]) tail = true;
    } else {
      for (let i = old.length; i < neu.length; i++) if (neu[i] && !allowed[i]) tail = true;
    }
    if (neu.length < old.length || outside || tail) throw new BuildError(`section ${id}: changes outside the declared patches`);
    if (neu.length > old.length && !mine.some((p) => p.append)) throw new BuildError(`section ${id}: grown without appended patches`);
    log.push(`section ${id}: ${diff} bytes changed, all inside the patches`
      + (neu.length > old.length ? `; ${neu.length - old.length} bytes appended (mod area)` : ""));
  }
  const manifest: Manifest = {
    os: version,
    stock_sha256: stockSha,
    mods: order,
    output: outName,
    output_sha256: sha256hex(syx),
    boot_margin: margin,
  };
  if (name) manifest.splash_name = name;
  return { syx, manifest, log };
}
