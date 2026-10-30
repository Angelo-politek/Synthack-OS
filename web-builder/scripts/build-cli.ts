// Il builder del browser da riga di comando (Node 24, niente WSL): stesse mod e stesso output di build.py.
//   node web-builder/scripts/build-cli.ts --stock firmware/Syntakt_OS1.41.syx splash fx3 ... -o out/web.syx

import { readdirSync, readFileSync, existsSync, mkdirSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build, BuildError, type ModSpec } from "../src/core/build.ts";

const MODS = resolve(dirname(fileURLToPath(import.meta.url)), "../../mods");

export function loadSpecs(dir = MODS): Record<string, ModSpec> {
  const specs: Record<string, ModSpec> = {};
  for (const d of readdirSync(dir)) {
    const f = join(dir, d, "patch.json");
    if (existsSync(f)) {
      const s = JSON.parse(readFileSync(f, "utf-8")) as ModSpec;
      specs[s.name] = s;
    }
  }
  return specs;
}

function main(argv: string[]): number {
  let stock = "", out = "", name = "";
  const mods: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--stock") stock = argv[++i];
    else if (argv[i] === "-o") out = argv[++i];
    else if (argv[i] === "--name") name = argv[++i];
    else mods.push(basename(argv[i].replace(/[\\/]+$/, "")));   // accetta anche mods/<nome>
  }
  if (!stock || !out || !mods.length) {
    console.error("usage: build-cli.ts --stock <Syntakt_OS1.41.syx> <mod>... -o <out.syx> [--name NAME]");
    return 2;
  }
  try {
    const t0 = Date.now();
    const r = build(new Uint8Array(readFileSync(stock)), mods, loadSpecs(), basename(out), (p) => {
      if (p.stage === "compress" && p.total) process.stderr.write(`\r  compress ${Math.round(100 * p.done! / p.total)}%`);
    }, { splashName: name });
    process.stderr.write("\n");
    for (const l of r.log) console.log("  " + l);
    mkdirSync(dirname(resolve(out)), { recursive: true });
    writeFileSync(out, r.syx);
    writeFileSync(out.replace(/\.syx$/i, "") + ".json", JSON.stringify(r.manifest, null, 2) + "\n");
    console.log(`OK ${out}  mods=${r.manifest.mods.join(",")}  sha256=${r.manifest.output_sha256.slice(0, 16)}...  ${((Date.now() - t0) / 1000).toFixed(1)} s`);
    return 0;
  } catch (e) {
    if (!(e instanceof BuildError) && !(e instanceof Error)) throw e;
    console.error(`BUILD FAILED: ${e.message}`);
    return 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) process.exit(main(process.argv.slice(2)));
