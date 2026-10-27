// Le mod del repo, incluse nella pagina al build di Vite: patch.json (cosa scrivere) e mod.json (la scheda).

import type { ModSpec } from "./core/build.ts";

export interface Card {
  title: string;
  kind: "feature" | "infra" | "test";
  summary: string;
}

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
