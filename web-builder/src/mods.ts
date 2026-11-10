// Le mod del repo, incluse nella pagina al build di Vite: patch.json (cosa scrivere) e mod.json (la scheda).
// Piu' le mod caricate da chi usa il sito (local.ts), solo nel suo browser.

import type { ModSpec } from "./core/build.ts";
import type { Card } from "./core/modfile.ts";

export type { Card };

const patches = import.meta.glob<ModSpec>("../../mods/*/patch.json", { eager: true, import: "default" });
const cards = import.meta.glob<Card>("../../mods/*/mod.json", { eager: true, import: "default" });

export const specs: Record<string, ModSpec> = {};
export const info: Record<string, Card> = {};
for (const [path, spec] of Object.entries(patches)) {
  const card = cards[path.replace(/patch\.json$/, "mod.json")];
  if (!card) continue;
  specs[spec.name] = spec;
  info[spec.name] = card;
}

export const REPO = "https://github.com/Angelo-politek/Synthack-OS";
export const modUrl = (name: string): string => `${REPO}/tree/main/mods/${name}`;

// Gruppi delle tessere: per cosa si usa la mod. Una mod che non e' qui (le nuove, le locali) va in "more".
export const GROUPS: { id: string; title: string; note: string }[] = [
  { id: "sound", title: "Sound", note: "Effects, inputs, modulation." },
  { id: "sequencer", title: "Sequencer", note: "Playing and performing." },
  { id: "samples", title: "Samples", note: "Record, load and play samples. They work with the SAMPLER machine." },
  { id: "system", title: "System", note: "How the OS shows and runs things." },
  { id: "more", title: "More", note: "" },
];
const GROUP_OF: Record<string, string> = {
  "master-comp": "sound", fx3: "sound", "dual-mono": "sound", lfo3: "sound",
  "perf-fx": "sequencer", arp: "sequencer", poly: "sequencer",
  "long-samples": "samples", recorder: "samples",
  "readable-values": "system", "modulation-skip": "system", about: "system",
};
export const groupOf = (name: string): string => GROUP_OF[name] ?? "more";
