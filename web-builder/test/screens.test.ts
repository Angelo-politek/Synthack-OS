// Schermate delle mod (src/previews/frames, generate da tools/emu/screens.py) e marcatori del Markdown.

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";
import { renderMarkdown, screenMarkers } from "../src/site/markdown.ts";

const DIR = new URL("../src/previews/frames/", import.meta.url);
const index: Record<string, string> = JSON.parse(readFileSync(new URL("index.json", DIR), "utf8"));

test("every scene in index.json has frames, every frame is 128x64", () => {
  const files = readdirSync(DIR).filter((f) => f.endsWith(".json") && f !== "index.json");
  const ids = new Set<string>();
  for (const f of files) {
    const data = JSON.parse(readFileSync(new URL(f, DIR), "utf8"));
    assert.equal(data.w * data.h, 128 * 64);
    for (const b of data.frames) assert.equal(Buffer.from(b, "base64").length, 1024, f);
    for (const [name, seq] of Object.entries<[number, number][]>(data.scenes)) {
      ids.add(`${f.slice(0, -5)}/${name}`);
      assert.ok(seq.length);
      for (const [i, n] of seq) assert.ok(i >= 0 && i < data.frames.length && n > 0, `${f} ${name}`);
    }
  }
  assert.deepEqual([...ids].sort(), Object.keys(index).sort());
});

test("screen markers become figures, unknown ones vanish with a warning", () => {
  const warnings: string[] = [];
  const src = "Text\n<!-- @screen:fx3/page -->\n  <!-- @screen:nope/none -->\nmore <!-- @screen:fx3/page --> inline\n";
  const out = screenMarkers(src, index, (m) => warnings.push(m));
  assert.match(out, /<figure class="oled-frame screen-shot" data-screen="fx3\/page"><div class="oled"><\/div><figcaption>[^<]+<\/figcaption><\/figure>/);
  assert.equal(out.match(/<figure/g)?.length, 1);                      // solo su una riga propria
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /nope\/none/);
  const html = renderMarkdown("# T\n\n<!-- @screen:fx3/page -->\n\nAfter.\n", {}, index).html;
  assert.match(html, /<figure class="oled-frame screen-shot" data-screen="fx3\/page">/);
  assert.match(html, /<p>After\.<\/p>/);
});
