// Una mod caricata dalla pagina "Create your mod": il suo patch.json (stesso formato di mods/<nome>/), con
// facoltativa la scheda {"card": {title, kind, summary}}. Resta nel browser di chi la carica.

import { STOCK_SHA256, type ModSpec } from "./build.ts";

export type Kind = "base" | "feature" | "machine" | "infra" | "test";
export const KINDS: readonly Kind[] = ["base", "feature", "machine", "infra", "test"];

export interface Card {
  title: string;
  kind: Kind;
  summary: string;
}

export class ModFileError extends Error {}

const HEX = /^[0-9a-fA-F]*$/;
const NAME = /^[a-z0-9][a-z0-9-]{0,39}$/;

/** Controlla il file e restituisce mod e scheda; gli errori sono frasi per chi l'ha scritta. */
export function parseModFile(text: string, known: Record<string, ModSpec>): { spec: ModSpec; card: Card } {
  let j: unknown;
  try {
    j = JSON.parse(text);
  } catch (e) {
    throw new ModFileError(`not valid JSON: ${(e as Error).message}`);
  }
  if (!j || typeof j !== "object" || Array.isArray(j)) throw new ModFileError("expected a patch.json object");
  const o = j as Record<string, unknown>;
  const name = o.name;
  if (typeof name !== "string" || !NAME.test(name))
    throw new ModFileError("'name' must be lowercase letters, digits and dashes (like the folder mods/<name>)");
  if (known[name]) throw new ModFileError(`a mod called '${name}' already exists: pick another name`);
  if (typeof o.os !== "string" || !STOCK_SHA256[o.os])
    throw new ModFileError(`'os' must be one of ${Object.keys(STOCK_SHA256).join(", ")}`);
  const requires = o.requires ?? [];
  if (!Array.isArray(requires) || requires.some((r) => typeof r !== "string"))
    throw new ModFileError("'requires' must be a list of mod names");
  for (const r of requires as string[]) if (!known[r]) throw new ModFileError(`'requires' names an unknown mod: ${r}`);
  if (!Array.isArray(o.patches) || !o.patches.length) throw new ModFileError("'patches' must be a non-empty list");
  o.patches.forEach((p: unknown, i: number) => {
    const at = `patches[${i}]`;
    if (!p || typeof p !== "object") throw new ModFileError(`${at}: expected an object`);
    const q = p as Record<string, unknown>;
    if (q.section !== 3 && q.section !== 7) throw new ModFileError(`${at}: 'section' must be 3 or 7`);
    if (typeof q.addr !== "string" || !/^0[xX][0-9a-fA-F]{1,8}$/.test(q.addr)) throw new ModFileError(`${at}: 'addr' must be a hex string like "0x4024F897"`);
    if (typeof q.len !== "number" || !Number.isInteger(q.len) || q.len <= 0) throw new ModFileError(`${at}: 'len' must be a positive integer`);
    const data = typeof q.hex === "string" ? q.hex.replace(/ /g, "") : undefined;
    if (data !== undefined ? !HEX.test(data) || data.length !== 2 * q.len : typeof q.ascii !== "string" || q.ascii.length !== q.len)
      throw new ModFileError(`${at}: needs 'hex' (or 'ascii') with exactly 'len' bytes`);
    if (q.append) {
      if (data === undefined) throw new ModFileError(`${at}: an appended patch needs 'hex'`);
    } else if (typeof q.expect_sha256 !== "string" || !/^[0-9a-fA-F]{64}$/.test(q.expect_sha256)) {
      throw new ModFileError(`${at}: 'expect_sha256' (SHA-256 of the original bytes) is missing`);
    }
  });
  const c = (o.card ?? {}) as Record<string, unknown>;
  const kind = (c.kind ?? "feature") as Kind;
  if (!KINDS.includes(kind) || kind === "base") throw new ModFileError(`card.kind must be one of feature, machine, infra, test`);
  const card: Card = {
    title: typeof c.title === "string" && c.title.trim() ? c.title.trim().slice(0, 60) : name,
    kind,
    summary: typeof c.summary === "string" ? c.summary.trim().slice(0, 300) : typeof o.description === "string" ? o.description.slice(0, 300) : "",
  };
  const { card: _drop, ...spec } = o;
  return { spec: spec as unknown as ModSpec, card };
}
