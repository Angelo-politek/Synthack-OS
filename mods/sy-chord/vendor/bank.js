// SY CHORD wave bank editing: the pure, importable half of the tool.
// No DOM, no files, no network -- the tool view (js/tools/sychord-waves.js) drives it and
// web/test/e2e.test.mjs drives exactly the same functions, so what the page queues is what the
// test verifies. Building the .syx and checking it is the workbench's job (js/workbench.js):
// this module only produces a rewritten copy of section 7.
//
// A "bank" is a plain array of 32 slot entries, one per WAVE key frame:
//   { kind: "factory", from: j }                   frame j of the user's own firmware
//   { kind: "custom", name, samples, harmonics, cycle, report }
// A factory entry with from !== k is a *moved* frame: it must be copied byte for byte,
// never re-normalised, because writeFrame() would round it to 16-bit precision.

import * as fw from "./syntakt-fw.js";
import { conditionCycle } from "./wave-dsp.js";

export const FRAME_COUNT = 32;          // frames 0..31
export const FRAME_BYTES = fw.WAVE.SAMPLES * 4; // 257 samples, big-endian int32

/** WAVE parameter value (CC 18) that selects frame k exactly. */
export const waveValue = (k) => 4 * k;

export const factoryEntry = (k) => ({ kind: "factory", from: k });

/** A pristine bank: every frame is its own factory frame. */
export function initialBank() {
  return Array.from({ length: FRAME_COUNT }, (_, k) => factoryEntry(k));
}

/** True when slot k still holds its own untouched factory frame. */
export function isIdentity(entry, k) {
  return entry.kind === "factory" && entry.from === k;
}

/** "factory" | "moved" | "custom" -- the badge shown on a card. */
export function entryState(entry, k) {
  if (entry.kind === "custom") return "custom";
  return entry.from === k ? "factory" : "moved";
}

/**
 * Condition user audio into a slot entry. `samples` is kept so that changing the
 * band limit later can re-condition from the original material, not from the result.
 */
export function customEntry(name, samples, harmonics) {
  const { cycle, report } = conditionCycle(samples, { harmonics });
  return { kind: "custom", name, samples, harmonics, cycle, report };
}

/** Replace slot k. Nothing else moves. */
export function replaceAt(bank, k, entry) {
  assertFrame(k);
  const out = bank.slice();
  out[k] = entry;
  return out;
}

/**
 * Insert at frame p: old frames p..30 move up to p+1..31, old frame 31 is dropped.
 * Frame 0 never moves, so p must be 1..31.
 */
export function insertAt(bank, p, entry) {
  assertFrame(p);
  if (p < 1) throw new Error("cannot insert at frame 0: the sine is shared with other machines");
  const out = bank.slice();
  for (let k = FRAME_COUNT - 1; k > p; k--) out[k] = bank[k - 1];
  out[p] = entry;
  return out;
}

/** Put slot k back to its own factory frame. */
export function resetAt(bank, k) {
  return replaceAt(bank, k, factoryEntry(k));
}

/** Fill consecutive slots from `start`, stopping at frame 31. Returns the new bank. */
export function fillFrom(bank, start, entries) {
  let out = bank.slice();
  for (let i = 0; i < entries.length && start + i < FRAME_COUNT; i++) out[start + i] = entries[i];
  return out;
}

/** How many slots `fillFrom` would actually use. */
export function fillCapacity(start) {
  return Math.max(0, FRAME_COUNT - start);
}

/** Re-condition every custom slot at a new band limit, reusing the stored input samples. */
export function recondition(bank, harmonics) {
  return bank.map((e) => (e.kind === "custom" ? customEntry(e.name, e.samples, harmonics) : e));
}

/** True when any slot other than 0 differs from factory. */
export function hasChanges(bank) {
  return bank.some((e, k) => !isIdentity(e, k));
}

function assertFrame(k) {
  if (!Number.isInteger(k) || k < 0 || k >= FRAME_COUNT) throw new Error("frame must be 0..31");
}

// ---- the operations list -----------------------------------------------------------
//
// The tool does not store a bank: it stores an ordered list of operations and replays
// them over the bank read from the loaded image. Same operations in the same order =>
// identical bytes, and removing one operation restores exactly the earlier result.
//
//   op = { frame, mode: "replace" | "insert", name, samples, harmonics }
//
// `samples` is the raw audio of the imported WAV, so changing the band limit of one
// operation re-derives its wave from the original material and never from a result.

const entryCache = new WeakMap(); // op -> { harmonics, entry }: replay stays cheap, ops stay plain

/** Build an operation. Frame 0 can only ever be replaced; the sine never moves. */
export function makeOp(frame, mode, name, samples, harmonics) {
  assertFrame(frame);
  const m = mode === "insert" && frame >= 1 ? "insert" : "replace";
  return { frame, mode: m, name, samples, harmonics };
}

/** The conditioned wave of one operation, memoised per (op, band limit). */
export function opEntry(op) {
  const c = entryCache.get(op);
  if (c && c.harmonics === op.harmonics) return c.entry;
  const entry = customEntry(op.name, op.samples, op.harmonics);
  entryCache.set(op, { harmonics: op.harmonics, entry });
  return entry;
}

/** Change the band limit of one operation, returning a new list (the op object is replaced). */
export function setOpHarmonics(ops, index, harmonics) {
  const out = ops.slice();
  out[index] = { ...ops[index], harmonics };
  return out;
}

/** Append an operation. A Replace supersedes an earlier Replace of the same frame. */
export function addOp(ops, op) {
  const kept = op.mode === "replace"
    ? ops.filter((o) => !(o.mode === "replace" && o.frame === op.frame))
    : ops.slice();
  kept.push(op);
  return kept;
}

/** Drop the operation at `index`. */
export function removeOp(ops, index) {
  const out = ops.slice();
  out.splice(index, 1);
  return out;
}

/** Replay the whole list over `start` (by default a pristine bank). Deterministic. */
export function replayOps(ops, start = initialBank()) {
  let b = start.slice();
  for (const op of ops) {
    const entry = opEntry(op);
    b = op.mode === "insert" && op.frame >= 1 ? insertAt(b, op.frame, entry) : replaceAt(b, op.frame, entry);
  }
  return b;
}

/** Index of the operation that produced slot k, or -1: used by "Show" and the band slider. */
export function opIndexForSlot(ops, k) {
  const b = replayOps(ops);
  const e = b[k];
  if (!e || e.kind !== "custom") return -1;
  for (let i = ops.length - 1; i >= 0; i--) if (opEntry(ops[i]) === e) return i;
  return -1;
}

// ---- base images -------------------------------------------------------------------

/** The byte ranges of the wave mod inside section 7, as [start, endExclusive]. */
export function waveRegions(includeSine = true) {
  const r = [[fw.frameOffset(fw.WAVE.FRAMES), fw.WAVE.BANK_END]];
  if (includeSine) r.push([fw.WAVE.SINE_OFF, fw.WAVE.SINE_OFF + FRAME_BYTES]);
  return r;
}

/** Frames of `section` that differ from the same frame of `stockSection` (frame 0 included). */
export function changedFramesVsStock(stockSection, section) {
  const out = [];
  for (let k = 0; k < FRAME_COUNT; k++) {
    const o = fw.frameOffset(k);
    if (fw.diffRange(stockSection.subarray(o, o + FRAME_BYTES), section.subarray(o, o + FRAME_BYTES)) !== null) out.push(k);
  }
  return out;
}

/** A copy of `section` with every byte of the wave mod taken back from the stock section. */
export function revertWaveRegions(section, stockSection) {
  const out = section.slice();
  for (const [s, e] of waveRegions(true)) out.set(stockSection.subarray(s, e), s);
  return out;
}

// ---- building ----------------------------------------------------------------------

/**
 * Bit-exact copy of one stored frame (257 samples including the guard sample) from one
 * section-7 image into another, addressed with frameOffset(). No arithmetic, no rounding.
 */
export function copyFrameRaw(dst, dstK, src, srcK) {
  const from = fw.frameOffset(srcK), to = fw.frameOffset(dstK);
  dst.set(src.subarray(from, from + FRAME_BYTES), to);
}

/**
 * Build a new section 7 from the base section (the user's stock file, or the section 7 of
 * the already-modified image they loaded) plus the bank. Untouched slots are never
 * rewritten, kept and moved frames are raw byte copies and only custom slots go through
 * writeFrame().
 */
export function buildSection(baseSection, bank, opts = {}) {
  const allowFrame0 = !!opts.allowFrame0;
  if (!allowFrame0 && !isIdentity(bank[0], 0)) {
    throw new Error("frame 0 is locked: unlock it before building, or reset frame 0");
  }
  const out = baseSection.slice();
  const changed = [];
  for (let k = 0; k < FRAME_COUNT; k++) {
    const e = bank[k];
    if (isIdentity(e, k)) continue;
    if (e.kind === "factory") copyFrameRaw(out, k, baseSection, e.from);
    else fw.writeFrame(out, k, e.cycle);
    changed.push(k);
  }
  return { section: out, changed, frame0Changed: changed.includes(0) };
}

// ---- preview -----------------------------------------------------------------------

/** Same normalisation writeFrame() applies, so plots show what will actually be stored. */
export function normaliseForPlot(cycle) {
  const y = Float64Array.from(cycle);
  let mean = 0;
  for (const x of y) mean += x;
  mean /= y.length;
  let peak = 0;
  for (const x of y) peak = Math.max(peak, Math.abs(x - mean));
  if (!(peak > 0)) return y;
  for (let i = 0; i < y.length; i++) y[i] = (y[i] - mean) / peak;
  y[0] = 0;
  return y;
}

/** The 256-sample cycle that slot k currently represents, ready to plot. */
export function previewCycle(baseSection, bank, k) {
  const e = bank[k];
  if (e.kind === "factory") return fw.readFrame(baseSection, e.from);
  return normaliseForPlot(e.cycle);
}
