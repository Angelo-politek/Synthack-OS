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
