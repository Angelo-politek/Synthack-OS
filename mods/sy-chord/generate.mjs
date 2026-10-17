import { readFileSync, writeFileSync } from "node:fs";
import assert from "node:assert/strict";
import * as fw from "./vendor/syntakt-fw.js";
import * as bank from "./vendor/bank.js";
import * as chord from "./vendor/chord-waves.js";
import { picturesForBank } from "./vendor/wave-picture.js";
import { BLOCK_OF_VALUE, OPERANDS, SECTION_BASE, BLOCK_REGION } from "./vendor/sychord-picture-map.js";
const [in3, in7, out3, out7, metaFile] = process.argv.slice(2);
if (![in3, in7, out3, out7, metaFile].every(Boolean)) throw Error("five file paths required");
const raw3 = new Uint8Array(readFileSync(in3));
const raw7 = new Uint8Array(readFileSync(in7));
assert.equal(raw7.length, fw.WAVE.SECTION_LEN);
const N = 1024, twopi = 2 * Math.PI;
const cycle = fn => Float64Array.from({ length: N }, (_, i) => fn(twopi * i / N, i / N));
const harmonic = (weight, limit = 40) => cycle(t => { let v = 0; for (let h = 1; h <= limit; h++) v += weight(h) * Math.sin(h * t); return v; });
const specs = [
  ["Saw", harmonic(h => 1 / h), 40], ["Soft saw", harmonic(h => 1 / h ** 1.5), 32], ["Bright saw", harmonic(h => 1 / h ** 0.8), 40], ["Odd saw", harmonic(h => (h % 2 ? 1 : 0.25) / h), 36],
  ["Folded saw", cycle((t, p) => Math.sin(2 * Math.PI * (p + 0.22 * Math.sin(t)))), 32], ["Reverse saw", cycle((t, p) => 1 - 2 * p), 40], ["Square", cycle(t => Math.sin(t) >= 0 ? 1 : -1), 40],
  ["Pulse 25", cycle((t, p) => p < 0.25 ? 1 : -1), 40], ["Pulse 12", cycle((t, p) => p < 0.125 ? 1 : -1), 40], ["Pulse 38", cycle((t, p) => p < 0.375 ? 1 : -1), 40],
  ["Soft pulse", harmonic(h => Math.sin(Math.PI * h * 0.25) / (h * h)), 32], ["Double pulse", cycle((t, p) => (p < 0.16 || (p > 0.5 && p < 0.66)) ? 1 : -1), 40],
  ["Organ 1-2-4", harmonic(h => ({ 1: 1, 2: 0.7, 4: 0.5 })[h] || 0), 16], ["Drawbar", harmonic(h => ({ 1: 1, 2: 0.8, 3: 0.25, 4: 0.5, 6: 0.3, 8: 0.2 })[h] || 0), 16],
  ["Hollow odd", harmonic(h => h % 2 ? 1 / h ** 1.2 : 0), 32], ["Fifth stack", harmonic(h => ({ 1: 1, 3: 0.7, 6: 0.4, 9: 0.2 })[h] || 0), 20],
  ["Octave stack", harmonic(h => (h & (h - 1)) === 0 ? 1 / Math.sqrt(h) : 0), 32], ["FM bright", cycle(t => Math.sin(t + 2.2 * Math.sin(2 * t))), 40],
  ["FM glass", cycle(t => Math.sin(t + 4.0 * Math.sin(3 * t))), 40], ["FM wood", cycle(t => Math.sin(t + 1.3 * Math.sin(5 * t))), 32],
  ["Wavefold", cycle(t => Math.sin(2.8 * Math.sin(t))), 40], ["Formant", harmonic(h => Math.exp(-(((h - 10) / 4) ** 2)) * Math.sin(h * 0.7) + (h === 1 ? 0.4 : 0), 32), 32],
  ["Sync edge", cycle(t => Math.sin(t) + 0.45 * Math.sin(5 * t) + 0.25 * Math.sin(9 * t)), 32],
];
for (const id of ["maj", "min", "sus4", "dim", "maj7", "7", "m7", "maj9"]) { const c = chord.chordCycle(id); specs.push([c.name, c.samples, Math.max(40, c.topHarmonic)]); }
assert.equal(specs.length, 31);
const entries = bank.initialBank();
specs.forEach(([name, samples, harmonics], i) => { entries[i + 1] = bank.customEntry(name, samples, harmonics); });
const { section: new7, changed } = bank.buildSection(raw7, entries);
assert.equal(changed.join(","), Array.from({ length: 31 }, (_, i) => i + 1).join(","));
assert.deepEqual(new7.subarray(fw.WAVE.SINE_OFF, fw.WAVE.SINE_OFF + bank.FRAME_BYTES), raw7.subarray(fw.WAVE.SINE_OFF, fw.WAVE.SINE_OFF + bank.FRAME_BYTES));
const new3 = new Uint8Array(raw3);
const frames = Array.from({ length: 32 }, (_, k) => fw.readFrame(new7, k));
const pictures = picturesForBank(frames);
const shared = new Set(OPERANDS.map(o => o.value));
for (let v = 1; v < 128; v++) if (!shared.has(v)) new3.set(pictures[v], BLOCK_OF_VALUE[v]);
for (const o of OPERANDS) { const addr = SECTION_BASE + BLOCK_OF_VALUE[o.showValue]; new3.set([(addr >>> 24) & 255, (addr >>> 16) & 255, (addr >>> 8) & 255, addr & 255], o.pointer); }
const regions = [{ section: 7, start: fw.WAVE.BANK_END - fw.WAVE.FRAMES * fw.WAVE.STEP, end: fw.WAVE.BANK_END }, { section: 3, start: BLOCK_REGION.start, end: BLOCK_REGION.end }, ...OPERANDS.map(o => ({ section: 3, start: o.pointer, end: o.pointer + 4 }))];
for (const [section, oldBytes, newBytes] of [[3, raw3, new3], [7, raw7, new7]]) for (let i = 0; i < oldBytes.length; i++) if (oldBytes[i] !== newBytes[i]) assert(regions.some(r => r.section === section && r.start <= i && i < r.end), `undeclared byte ${section}:${i.toString(16)}`);
writeFileSync(out3, new3); writeFileSync(out7, new7);
writeFileSync(metaFile, JSON.stringify({ waves: specs.map(([name], i) => ({ wave: (i + 1) * 4, name })), regions }, null, 2));
