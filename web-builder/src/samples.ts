// SPDX-License-Identifier: GPL-2.0-or-later
// Samples page: Synfact's long-sample protocol over WebMIDI (src/core/datarpc.ts, hzfs.ts, wav.ts).

import { DataClient, Transport, type Link } from "./core/datarpc.ts";
import { freeSpace, Store, type Entry, type Index, RATE } from "./core/hzfs.ts";
import { catalogueName, wavBody } from "./core/wav.ts";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const log = (s: string) => { const el = $("sm-log"); el.textContent += s + "\n"; el.scrollTop = el.scrollHeight; };
let store: Store | null = null, order: Entry[] = [], busy = false;

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
  store = new Store(new DataClient(new Transport(link)), log);
  $("sm-status").textContent = `Connected: ${out.name}. Reading…`;
  await refresh();
}

function fmt(e: Entry): [string, string] {
  return [`${(e.frames / RATE).toFixed(1)} s`, `${(e.bytes / 2 ** 20).toFixed(2)} MiB`];
}

function draw(): void {
  const rows = $("sm-rows");
  rows.replaceChildren(...order.map((e, i) => {
    const tr = document.createElement("tr");
    const [len, size] = fmt(e);
    tr.innerHTML = `<td class="n">${i + 1}</td><td></td><td>${len}</td><td>${size}</td><td></td>`;
    tr.children[1].textContent = e.name;
    const cell = tr.children[4];
    const btn = (t: string, f: () => void, dis = false) => {
      const b = Object.assign(document.createElement("button"), { className: "btn ghost small", textContent: t, type: "button", disabled: dis || busy });
      b.onclick = f;
      cell.append(b);
    };
    btn("↑", () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; dirty(); }, i === 0);
    btn("↓", () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; dirty(); }, i === order.length - 1);
    btn("Remove", () => remove(e));
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
  $("sm-free").textContent = `${index.entries.length} samples · ${(f.free / 2 ** 20).toFixed(0)} MiB free`;
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

async function save(): Promise<void> {
  if (!store || busy) return;
  await run(async () => {
    const map = order.slice(0, 64).map((e) => e.id);
    while (map.length < 64) map.push(0);
    await store!.setSlots(map);
    log("Order saved. Power cycle the Syntakt to load it.");
  });
}

async function remove(e: Entry): Promise<void> {
  if (!store || busy || !confirm(`Remove ${e.name} from the Syntakt?`)) return;
  await run(async () => { await store!.remove(e.id); log(`Removed ${e.name}.`); });
}

async function add(files: FileList): Promise<void> {
  if (!store || busy) return;
  await run(async () => {
    const used = new Set(order.map((e) => e.name));
    const prog = $("sm-prog"), bar = $("sm-bar");
    prog.hidden = false;
    for (const f of [...files]) {
      const name = catalogueName(f.name, used);
      try {
        const body = wavBody(new Uint8Array(await f.arrayBuffer()), name);
        log(`${f.name} -> "${name}", ${(((body.length - 64) / 2) / RATE).toFixed(1)} s`);
        await store!.put(name, body, (a, b) => { bar.style.width = `${(100 * a / b).toFixed(1)}%`; });
        const { index } = await store!.current();                 // new files: at the end of the saved order
        if (index.slotMap.some(Boolean)) {
          const map = index.slotMap.slice(), id = index.entries[index.entries.length - 1].id, free = map.indexOf(0);
          if (free >= 0 && !map.includes(id)) { map[free] = id; await store!.setSlots(map); }
        }
      } catch (err) {
        log(`[!] ${f.name}: ${(err as Error).message}`);
      }
    }
    prog.hidden = true;
    log("Done. Power cycle the Syntakt to load the new samples.");
  });
}

async function run(job: () => Promise<void>): Promise<void> {
  busy = true; draw();
  try { await job(); } catch (err) { log(`[!] ${(err as Error).message}`); }
  busy = false;
  try { await refresh(); } catch (err) { log(`[!] ${(err as Error).message}`); }
}

$("sm-connect").onclick = () => { connect().catch((e: Error) => log(`[!] ${e.message}`)); };
$("sm-save").onclick = () => { void save(); };
$<HTMLInputElement>("sm-files").onchange = (e) => {
  const files = (e.target as HTMLInputElement).files;
  if (files?.length) void add(files);
  (e.target as HTMLInputElement).value = "";
};
