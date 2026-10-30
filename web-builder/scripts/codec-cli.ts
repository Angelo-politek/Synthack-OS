// Compressori del builder da riga di comando, per i test di parita' con Python (tests/test_web_builder.py).
//   node web-builder/scripts/codec-cli.ts shlz <in> <out>
//   node web-builder/scripts/codec-cli.ts splash <patch.json> <name>     -> hex della prima patch

import { readFileSync, writeFileSync } from "node:fs";
import type { ModSpec } from "../src/core/build.ts";
import * as shlz from "../src/core/shlz.ts";
import { namedSplash } from "../src/core/splash.ts";

const [cmd, a, b] = process.argv.slice(2);
if (cmd === "shlz" && a && b) writeFileSync(b, shlz.compress(new Uint8Array(readFileSync(a))));
else if (cmd === "splash" && a && b !== undefined)
  process.stdout.write(namedSplash(JSON.parse(readFileSync(a, "utf-8")) as ModSpec, b).patches[0].hex!);
else {
  console.error("usage: codec-cli.ts shlz <in> <out> | splash <patch.json> <name>");
  process.exit(2);
}
