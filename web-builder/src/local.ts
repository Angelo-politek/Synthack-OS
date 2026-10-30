// Mod caricate da "Create your mod": il testo del file resta nel browser (localStorage) e si ricontrolla
// a ogni caricamento con parseModFile. Restano finche' la mod non entra nel repo e il sito si aggiorna.

import type { ModSpec } from "./core/build.ts";
import { ModFileError, parseModFile, type Card } from "./core/modfile.ts";

const KEY = "synthack.local-mods.v1";

interface Stored { name: string; text: string; added: number }
export interface LocalMod { name: string; spec: ModSpec; card: Card; added: number }

function load(): Stored[] {
  try {
    const v: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((s): s is Stored => typeof s?.name === "string" && typeof s?.text === "string") : [];
  } catch {
    return [];
  }
}

function save(list: Stored[]): boolean {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

/** Le mod locali ancora valide; problems: quelle scartate e perche'. */
export function localMods(repo: Record<string, ModSpec>): { mods: LocalMod[]; problems: string[] } {
  const known = { ...repo }, mods: LocalMod[] = [], problems: string[] = [];
  for (const s of load()) {
    if (repo[s.name]) {
      problems.push(`${s.name} is now in the official list: the local copy is ignored.`);
      continue;
    }
    try {
      const { spec, card } = parseModFile(s.text, known);
      known[spec.name] = spec;
      mods.push({ name: spec.name, spec, card, added: s.added });
    } catch (e) {
      problems.push(`${s.name}: ${e instanceof Error ? e.message : String(e)}`);
    }
  }
  return { mods, problems };
}

/** Controlla e salva; una mod locale con lo stesso nome viene sostituita. Errori: ModFileError. */
export function addLocal(text: string, repo: Record<string, ModSpec>): LocalMod {
  let name = "";
  try {
    const n: unknown = (JSON.parse(text) as { name?: unknown })?.name;
    if (typeof n === "string") name = n;
  } catch { /* lo segnala parseModFile */ }
  const others = load().filter((s) => s.name !== name);
  const known = { ...repo };
  for (const m of localMods(repo).mods) if (m.name !== name) known[m.name] = m.spec;
  const { spec, card } = parseModFile(text, known);
  const added = Date.now();
  if (!save([...others, { name: spec.name, text, added }]))
    throw new ModFileError("the mod is valid, but this browser does not allow saving it (storage blocked or full)");
  return { name: spec.name, spec, card, added };
}

export function removeLocal(name: string): void {
  save(load().filter((s) => s.name !== name));
}
