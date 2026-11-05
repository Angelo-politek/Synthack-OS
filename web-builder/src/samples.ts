// SPDX-License-Identifier: GPL-2.0-or-later
// Samples page: Synfact's long-sample protocol over WebMIDI (src/core/datarpc.ts, hzfs.ts, wav.ts), voice CPU memory
// as the boot plan fills it (core/sampedit.ts), and an editor (waveform, start, end, name) before a sample is stored.

import { DataClient, Transport, type Link } from "./core/datarpc.ts";
import { freeSpace, Store, type Entry, type Index, RATE } from "./core/hzfs.ts";
import { bodySamples, mib, PAGE, peaks, POOL_PAGES, stockBytes, usage } from "./core/sampedit.ts";
import { catalogueName, readWav, resample, sampBody } from "./core/wav.ts";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const log = (s: string) => { const el = $("sm-log"); el.textContent += s + "\n"; el.scrollTop = el.scrollHeight; };
let store: Store | null = null, client: DataClient | null = null, order: Entry[] = [], busy = false;
let stock = 0, stockCount = 0, storage = "";

async function connect(): Promise<void> {
  if (!("requestMIDIAccess" in navigator)) { log("This browser has no WebMIDI. Use Chrome or Edge."); return; }
  const access = await navigator.requestMIDIAccess({ sysex: true });
  const outs = [...access.outputs.values()], ins = [...access.inputs.values()];
  const pick = outs.filter((o) => /syntakt/i.test(o.name ?? ""));
  const sel = $<HTMLSelectElement>("sm-port");
  if (pick.length !== 1) {
    sel.hidden = false;
    sel.replaceChildren(...outs.map((o, i) => Object.assign(document.createElement("option"), { value: String(i), textContent: o.name ?? `port ${i}` })));
    if (!pick.length) { log("No MIDI port named Syntakt: pick it in the list, then Connect again."); return; }
  }
  const out = pick.length === 1 ? pick[0] : outs[Number(sel.value)];
  const inp = ins.find((i) => i.name === out.name) ?? ins.find((i) => /syntakt/i.test(i.name ?? ""));
  if (!inp) { log("No matching MIDI input."); return; }
  const link: Link = {
    send: (m) => out.send(m),
    onMessage: (fn) => { inp.onmidimessage = (e) => { if (e.data) fn(e.data); }; },
  };
  client = new DataClient(new Transport(link));
  store = new Store(client, log);
  $("sm-status").textContent = `Connected: ${out.name}. Reading the stock samples…`;
  const lengths: number[] = [];
  for (let n = 1; n <= 64; n++) lengths.push(await client.stockLength(n));
  stock = stockBytes(lengths);
  stockCount = lengths.filter((l) => l > 64).length;
  $("sm-status").textContent = "Reading the long samples…";
  await refresh();
}

/** the voice CPU memory bar, the storage line, and the table */
function draw(): void {
  const u = usage(stock, order), total = POOL_PAGES;
  const seg = (cls: string, pages: number, title: string) => {
    const d = Object.assign(document.createElement("span"), { className: cls, title });
    d.style.width = `${(100 * pages / total).toFixed(3)}%`;
    return d;
  };
  const longPages = u.files.filter((f) => f.loads).reduce((t, f) => t + f.pages, 0) + (u.files.length ? 1 : 0);
  $("sm-mem").replaceChildren(
    seg("seg stock", u.stockPages, `stock samples: ${mib(u.stockPages * PAGE)}`),
    seg("seg long", longPages, `long samples: ${mib(longPages * PAGE)}`));
  const late = u.files.filter((f) => !f.loads).length;
  $("sm-mem-text").textContent = `Voice memory at the next boot: stock ${mib(u.stockPages * PAGE)} (${stockCount} samples) · `
    + `long ${mib(longPages * PAGE)} · free ${mib(u.freePages * PAGE)} of 64 MiB`
    + (late ? ` · ${late} sample${late > 1 ? "s" : ""} won't load (no room)` : "");
  $("sm-free").textContent = storage;
  const rows = $("sm-rows");
  rows.replaceChildren(...u.files.map((f, i) => {
    const e = f.e, tr = document.createElement("tr");
    if (!f.loads) tr.className = "late";
    tr.innerHTML = `<td class="n">${i + 1}</td><td class="nm"></td><td>${(e.frames / RATE).toFixed(1)} s</td>`
      + `<td>${mib(f.pages * PAGE)} <span class="share">${(100 * f.pages / total).toFixed(1)}%</span></td><td class="act"></td>`;
    tr.children[1].textContent = e.name + (f.loads ? "" : "  (won't load)");
    const cell = tr.children[4];
    const btn = (t: string, fn: () => void, dis = false) => {
      const b = Object.assign(document.createElement("button"), { className: "btn ghost small", textContent: t, type: "button", disabled: dis || busy });
      b.onclick = fn;
      cell.append(b);
    };
    btn("↑", () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; dirty(); }, i === 0);
    btn("↓", () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; dirty(); }, i === order.length - 1);
    btn("Rename", () => void rename(e));
    btn("Edit", () => void editStored(e));
    btn("Remove", () => void remove(e));
    return tr;
  }));
}

function dirty(): void { $<HTMLButtonElement>("sm-save").disabled = false; draw(); }

async function refresh(): Promise<void> {
  if (!store) return;
  await store.ensure();
  const { index, copies } = await store.current();
  order = ordered(index);
  const f = freeSpace(copies, index.windows);
  storage = `Internal storage: ${index.entries.length} long samples · ${mib(f.free)} free`;
  $("sm-status").textContent = "Connected.";
  $("sm-lib").hidden = false;
  $<HTMLButtonElement>("sm-save").disabled = true;
  draw();
}

/** the order the Syntakt plays: the slot map when set, else the catalogue order */
function ordered(index: Index): Entry[] {
  if (!index.slotMap.some(Boolean)) return index.entries.slice();
  const byId = new Map(index.entries.map((e) => [e.id, e]));
  const out = index.slotMap.filter((id) => byId.has(id)).map((id) => byId.get(id)!);
  for (const e of index.entries) if (!out.includes(e)) out.push(e);       // not mapped yet: at the end
  return out;
}

async function saveOrder(map = order.slice(0, 64).map((e) => e.id)): Promise<void> {
  while (map.length < 64) map.push(0);
  await store!.setSlots(map);
}

async function save(): Promise<void> {
  if (!store || busy) return;
  await run(async () => { await saveOrder(); log("Order saved. Power cycle the Syntakt to load it. Projects saved with their own list keep it."); });
}

async function remove(e: Entry): Promise<void> {
  if (!store || busy || !confirm(`Remove ${e.name} from the Syntakt?`)) return;
  await run(async () => { await store!.remove(e.id); log(`Removed ${e.name}.`); });
}

async function rename(e: Entry): Promise<void> {
  if (!store || busy) return;
  const name = prompt("New name (up to 32 characters):", e.name)?.trim();
  if (!name || name === e.name) return;
  await run(async () => { await store!.rename(e.id, name); log(`Renamed ${e.name} -> ${name}.`); });
}

// ---- editor: waveform, start, end, name; Play plays the part picked

interface Edit { name: string; s: Float32Array; a: number; b: number }

function editor(name: string, s: Float32Array): Promise<Edit | null> {
  const dlg = $<HTMLDialogElement>("sm-edit"), cv = $<HTMLCanvasElement>("sm-wave");
  const nameIn = $<HTMLInputElement>("sm-name"), aIn = $<HTMLInputElement>("sm-start"), bIn = $<HTMLInputElement>("sm-end");
  const info = $("sm-sel");
  nameIn.value = name;
  aIn.max = bIn.max = String(s.length);
  aIn.value = "0";
  bIn.value = String(s.length);
  const w = cv.width, h = cv.height, pk = peaks(s, w), g = cv.getContext("2d")!;
  let audio: AudioContext | null = null, src: AudioBufferSourceNode | null = null;
  const paint = () => {
    const a = +aIn.value, b = +bIn.value, xa = Math.round(w * a / s.length), xb = Math.round(w * b / s.length);
    g.clearRect(0, 0, w, h);
    for (let x = 0; x < w; x++) {
      const y = pk[x] * h / 2;
      g.fillStyle = x >= xa && x < xb ? "#e8e8e8" : "#555";
      g.fillRect(x, h / 2 - y, 1, Math.max(1, 2 * y));
    }
    g.fillStyle = "#ff5a36";
    g.fillRect(xa, 0, 2, h);
    g.fillRect(Math.max(0, xb - 2), 0, 2, h);
    const len = (b - a) / RATE;
    info.textContent = `start ${(a / RATE).toFixed(3)} s · end ${(b / RATE).toFixed(3)} s · length ${len.toFixed(2)} s · ${mib(64 + 2 * (b - a))}`;
  };
  const stop = () => { try { src?.stop(); } catch { /* not started */ } src = null; };
  aIn.oninput = () => { if (+aIn.value >= +bIn.value) aIn.value = String(+bIn.value - 1); paint(); };
  bIn.oninput = () => { if (+bIn.value <= +aIn.value) bIn.value = String(+aIn.value + 1); paint(); };
  cv.onpointerdown = (ev) => {                                  // click: the nearer end moves there
    const r = cv.getBoundingClientRect(), at = Math.round(s.length * (ev.clientX - r.left) / r.width);
    if (Math.abs(at - +aIn.value) <= Math.abs(at - +bIn.value)) aIn.value = String(Math.min(at, +bIn.value - 1));
    else bIn.value = String(Math.max(at, +aIn.value + 1));
    paint();
  };
  $("sm-play").onclick = () => {
    stop();
    audio ??= new AudioContext({ sampleRate: RATE });
    const a = +aIn.value, b = +bIn.value, buf = audio.createBuffer(1, b - a, RATE);
    buf.copyToChannel(s.slice(a, b), 0);
    src = audio.createBufferSource();
    src.buffer = buf;
    src.connect(audio.destination);
    src.start();
  };
  $("sm-stop").onclick = stop;
  paint();
  dlg.showModal();
  return new Promise((done) => {
    const close = (r: Edit | null) => { stop(); void audio?.close(); dlg.close(); done(r); };
    $("sm-ok").onclick = () => {
      const n = nameIn.value.trim();
      if (!n || new TextEncoder().encode(n).length > 32) { alert("The name needs 1 to 32 characters."); return; }
      close({ name: n, s, a: +aIn.value, b: +bIn.value });
    };
    $("sm-cancel").onclick = () => close(null);
    dlg.oncancel = (ev) => { ev.preventDefault(); close(null); };
  });
}

const bar = (a: number, b: number) => { $("sm-bar").style.width = `${(100 * a / b).toFixed(1)}%`; };

/** store an edited sample; replacing: the old one leaves, the new one takes its place in the order */
async function store1(ed: Edit, replacing?: Entry): Promise<void> {
  const used = new Set(order.filter((e) => e !== replacing).map((e) => e.name));
  if (used.has(ed.name)) throw new Error(`"${ed.name}" already exists`);
  const tmp = replacing && replacing.name === ed.name ? catalogueName(`${ed.name}~new`, new Set(order.map((e) => e.name))) : ed.name;
  const body = sampBody(ed.s.subarray(ed.a, ed.b), ed.name);
  log(`Storing "${ed.name}", ${((ed.b - ed.a) / RATE).toFixed(1)} s…`);
  const e = await store!.put(tmp, body, bar);
  const { index } = await store!.current();
  const map = index.slotMap.slice();
  if (replacing) {
    const at = order.indexOf(replacing);
    await store!.remove(replacing.id);
    if (tmp !== ed.name) await store!.rename(e.id, ed.name);
    if (map.some(Boolean) || at >= 0) {
      const ids = order.map((x) => (x === replacing ? e.id : x.id)).slice(0, 64);
      await saveOrder(ids);
    }
  } else if (map.some(Boolean)) {                              // new: at the end of the saved order
    const free = map.indexOf(0);
    if (free >= 0 && !map.includes(e.id)) { map[free] = e.id; await store!.setSlots(map); }
  }
}

async function add(files: FileList): Promise<void> {
  if (!store || busy) return;
  await run(async () => {
    const used = new Set(order.map((e) => e.name));
    $("sm-prog").hidden = false;
    for (const f of [...files]) {
      try {
        const { rate, mono } = readWav(new Uint8Array(await f.arrayBuffer()));
        const ed = await editor(catalogueName(f.name, used), resample(mono, rate));
        if (!ed) { log(`${f.name}: skipped.`); continue; }
        await store1(ed);
        used.add(ed.name);
        order = ordered((await store!.current()).index);
      } catch (err) {
        log(`[!] ${f.name}: ${(err as Error).message}`);
      }
    }
    $("sm-prog").hidden = true;
    log("Done. Power cycle the Syntakt to load the new samples.");
  });
}

async function editStored(e: Entry): Promise<void> {
  if (!store || busy) return;
  await run(async () => {
    $("sm-prog").hidden = false;
    log(`Reading ${e.name} from the Syntakt…`);
    const s = bodySamples(await store!.body(e.id, bar));
    const ed = await editor(e.name, s);
    if (ed && (ed.a > 0 || ed.b < s.length || ed.name !== e.name)) {
      if (ed.a === 0 && ed.b === s.length) await store!.rename(e.id, ed.name);   // name only: no rewrite
      else await store1(ed, e);
      log("Done. Power cycle the Syntakt to load the change.");
    }
    $("sm-prog").hidden = true;
  });
}

async function run(job: () => Promise<void>): Promise<void> {
  busy = true; draw();
  try { await job(); } catch (err) { log(`[!] ${(err as Error).message}`); }
  busy = false;
  $("sm-prog").hidden = true;
  try { await refresh(); } catch (err) { log(`[!] ${(err as Error).message}`); }
}

$("sm-connect").onclick = () => { connect().catch((e: Error) => log(`[!] ${e.message}`)); };
$("sm-save").onclick = () => { void save(); };
$<HTMLInputElement>("sm-files").onchange = (e) => {
  const files = (e.target as HTMLInputElement).files;
  if (files?.length) void add(files);
  (e.target as HTMLInputElement).value = "";
};
