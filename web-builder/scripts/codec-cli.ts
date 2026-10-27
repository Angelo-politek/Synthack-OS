// Compressori del builder da riga di comando, per i test di parita' con Python (tests/test_web_builder.py).
//   node web-builder/scripts/codec-cli.ts shlz <in> <out>

import { readFileSync, writeFileSync } from "node:fs";
import * as shlz from "../src/core/shlz.ts";

const [cmd, inp, out] = process.argv.slice(2);
if (cmd !== "shlz" || !inp || !out) {
  console.error("usage: codec-cli.ts shlz <in> <out>");
  process.exit(2);
}
writeFileSync(out, shlz.compress(new Uint8Array(readFileSync(inp))));
