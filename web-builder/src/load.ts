// Indicatore di carico: CPU audio, area mod, kit, codice della CPU #2, sommati sulle mod scelte (dipendenze
// comprese). Dati da tools/build/budget.py: misure nell'emulatore e spazio prenotato nel registro.

import budget from "./budget.json";

interface Cost { cpu: number; modarea: number; kit: number; project: number; sec7: number }
type Key = "cpu" | "modarea" | "kit" | "sec7";

const LIMITS = budget.limits as Record<Key, number>;
const COSTS = budget.mods as Record<string, Cost>;

const METERS: { key: Key; label: string; kb: boolean; over: string; note: string }[] = [
  { key: "cpu", label: "Audio CPU", kb: false, over: "Audio CPU above ~3 000 extra instructions per block: the UI is likely to lag.",
    note: "Extra instructions per audio block on CPU #1, worst case. Above ~3 000 the Syntakt UI lags." },
  { key: "modarea", label: "Mod RAM", kb: true, over: "Mod RAM full: these mods don't fit together.",
    note: "RAM reserved for mod code and data (64 KB)." },
  { key: "kit", label: "Kit words", kb: false, over: "Kit words full: these mods don't fit together.",
    note: "Spare words saved with the kit (kitstore)." },
  { key: "sec7", label: "Engine code", kb: true, over: "Engine code full: these machines don't fit together.",
    note: "Code for machines on the sound engine (CPU #2), counted uncompressed against the room left in the compressed section 7." },
];

const fmt = (n: number): string => n.toLocaleString("en-US").replace(/,/g, " ");
const kb = (n: number): string => (n / 1024).toFixed(n && n < 10240 ? 1 : 0);

export function renderLoad(box: HTMLElement): void {
  box.replaceChildren();
  for (const m of METERS) {
    const row = document.createElement("div");
    row.className = "meter";
    row.dataset.key = m.key;
    row.title = m.note;
    row.innerHTML = `<span class="m-label">${m.label}</span><span class="m-val"></span>`
      + `<span class="m-track" aria-hidden="true"><span class="m-fill"></span><span class="m-mark"></span></span>`;
    box.append(row);
  }
  box.append(Object.assign(document.createElement("p"), { className: "m-note" }));
}

/** names: mod da costruire, dipendenze comprese; unknown: mod caricate in locale, senza misure. */
export function updateLoad(box: HTMLElement, names: string[], unknown: string[]): void {
  const sum = (k: Key): number => names.reduce((s, n) => s + (COSTS[n]?.[k] ?? 0), 0);
  for (const m of METERS) {
    const row = box.querySelector<HTMLElement>(`.meter[data-key="${m.key}"]`)!;
    const v = sum(m.key), lim = LIMITS[m.key];
    const scale = m.key === "cpu" ? Math.max(lim * 1.5, v) : lim;   // la CPU puo' superare la soglia: si vede di quanto
    const over = v > lim;
    row.classList.toggle("over", over);
    row.querySelector<HTMLElement>(".m-fill")!.style.width = `${Math.min(100, (100 * v) / scale)}%`;
    row.querySelector<HTMLElement>(".m-mark")!.style.left = `${(100 * lim) / scale}%`;
    row.querySelector<HTMLElement>(".m-val")!.textContent = m.kb ? `${kb(v)} / ${kb(lim)} KB` : `${fmt(v)} / ${fmt(lim)}`;
  }
  const overs = METERS.filter((m) => sum(m.key) > LIMITS[m.key]).map((m) => m.over);
  const note = box.querySelector(".m-note")!;
  note.classList.toggle("bad", overs.length > 0);
  note.textContent = [...overs, unknown.length ? `Not counted (no measurements yet): ${unknown.join(", ")}.`
    : "Measured in the emulator, worst case. The build checks the boot margin."].join(" ");
}

export const measured = (name: string): boolean => name in COSTS;
