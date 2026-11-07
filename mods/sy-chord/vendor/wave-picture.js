// The small wave picture the Syntakt draws in the WAVE cell, rendered from a cycle.
//
// One picture per WAVE value (0..127). The instrument keeps them as 1-bit bitmaps,
// 17 px wide and 17 px tall: time runs top to bottom, amplitude left to right.
// Each picture is a polyline through 17 points of the cycle (every 16th sample of a
// 256-point cycle, sample 256 = sample 0), x = 8 + 5 * y rounded, joined by lines.
// The values between two key frames show the same linear morph the synth plays.
//
// This module renders pictures from cycles; it knows nothing about the firmware file.
// Pure functions, no dependencies; Node and browser.

export const PICTURE_W = 17;
export const PICTURE_H = 17;
export const PICTURE_BYTES = 68;          // 17 rows x 4 bytes (one big-endian 32-bit word per row, MSB = x 0)
export const PICTURE_COUNT = 128;         // one per WAVE value
export const CENTRE_X = 8;
export const AMPLITUDE_PX = 5;
export const CYCLE_LEN = 256;

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Sample index of picture row r (0..16) in a 256-point cycle; row 16 wraps to sample 0. */
export const rowSample = (r) => (r * 16) % CYCLE_LEN;

/** The 17 x positions of a cycle's polyline (integers 0..16). */
export function polylineX(cycle) {
  if (cycle.length < CYCLE_LEN) throw new Error("cycle must have 256 samples");
  const xs = new Array(PICTURE_H);
  for (let r = 0; r < PICTURE_H; r++) {
    const y = clamp(cycle[rowSample(r)], -1, 1);
    xs[r] = clamp(Math.floor(CENTRE_X + AMPLITUDE_PX * y + 0.5), 0, PICTURE_W - 1);
  }
  return xs;
}

/** Render one picture: a Uint8Array of 68 bytes, 4 per row, MSB first. */
export function renderPicture(cycle) {
  const xs = polylineX(cycle);
  const px = new Uint8Array(PICTURE_W * PICTURE_H);
  const set = (x, y) => { px[y * PICTURE_W + x] = 1; };
  for (let r = 0; r < PICTURE_H; r++) {
    if (r > 0) line(xs[r - 1], r - 1, xs[r], r, set);
    else set(xs[0], 0);
  }
  return packPixels(px);
}

/** Bresenham segment from (x0,y0) to (x1,y1), both ends inclusive. */
function line(x0, y0, x1, y1, set) {
  const dx = Math.abs(x1 - x0), dy = Math.abs(y1 - y0);
  const sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx - dy, x = x0, y = y0;
  for (;;) {
    set(x, y);
    if (x === x1 && y === y1) return;
    const e2 = 2 * err;
    if (e2 > -dy) { err -= dy; x += sx; }
    if (e2 < dx) { err += dx; y += sy; }
  }
}

/** 17x17 pixel array (row-major, 1 = lit) -> 68 bytes as the instrument stores them. */
export function packPixels(px) {
  const out = new Uint8Array(PICTURE_BYTES);
  for (let r = 0; r < PICTURE_H; r++) {
    let word = 0;
    for (let c = 0; c < PICTURE_W; c++) if (px[r * PICTURE_W + c]) word |= 1 << (31 - c);
    out[r * 4] = (word >>> 24) & 0xff; out[r * 4 + 1] = (word >>> 16) & 0xff;
    out[r * 4 + 2] = (word >>> 8) & 0xff; out[r * 4 + 3] = word & 0xff;
  }
  return out;
}

/** 68 bytes -> 17x17 pixel array (row-major, 1 = lit). */
export function unpackPixels(bytes) {
  const px = new Uint8Array(PICTURE_W * PICTURE_H);
  for (let r = 0; r < PICTURE_H; r++) {
    const word = ((bytes[r * 4] << 24) | (bytes[r * 4 + 1] << 16) | (bytes[r * 4 + 2] << 8) | bytes[r * 4 + 3]) >>> 0;
    for (let c = 0; c < PICTURE_W; c++) px[r * PICTURE_W + c] = (word >>> (31 - c)) & 1;
  }
  return px;
}

/** Linear morph of two cycles: (1 - f) * a + f * b. */
export function morphCycles(a, b, f) {
  const out = new Float64Array(CYCLE_LEN);
  for (let i = 0; i < CYCLE_LEN; i++) out[i] = a[i] * (1 - f) + b[i] * f;
  return out;
}

/**
 * The cycle the synth plays at WAVE value v (0..127), given the 32 key-frame cycles
 * (index k = value / 4): a linear morph between frames v >> 2 and (v >> 2) + 1,
 * the last frame morphing into itself.
 */
export function cycleAtValue(frames, v) {
  if (frames.length !== 32) throw new Error("need 32 key frames");
  const k = v >> 2, f = (v & 3) / 4;
  return morphCycles(frames[k], frames[Math.min(k + 1, 31)], f);
}

/** All 128 pictures for a bank of 32 key-frame cycles, as an array of Uint8Array(68). */
export function picturesForBank(frames) {
  const out = new Array(PICTURE_COUNT);
  for (let v = 0; v < PICTURE_COUNT; v++) out[v] = renderPicture(cycleAtValue(frames, v));
  return out;
}

/** For display and tests: the picture as 17 strings of '#' and '.'. */
export function asciiPicture(bytes) {
  const px = unpackPixels(bytes);
  const rows = [];
  for (let r = 0; r < PICTURE_H; r++) {
    let s = "";
    for (let c = 0; c < PICTURE_W; c++) s += px[r * PICTURE_W + c] ? "#" : ".";
    rows.push(s);
  }
  return rows;
}
