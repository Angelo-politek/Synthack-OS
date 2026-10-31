// Chord waves for SY CHORD: one cycle that holds a whole chord.
// Pure functions, no dependencies, no I/O: runs in a browser and in Node (ES module).
//
// A single cycle can only contain whole-number harmonics of the note being played, so every
// chord tone has to land on one. Two ways to do that, both offered:
//
//   "octave": the root sits on harmonic 16, exactly four octaves above the played note, and
//             every other tone is rounded to the nearest harmonic. The root always sounds on
//             the note you play; a few tones are up to about 30 cents off just intonation.
//   "just":   the smallest whole numbers with exactly the chord's ratios (4:5:6, 10:12:15, ...).
//             Every interval is pure, but the root lands wherever those numbers put it, so it
//             is not always an octave of the played note (minor: 10 = 3 octaves and a third).
//
// The tones are equal-level sines with phases chosen to keep the peak low, so the wave
// comes out loud after writeFrame() normalises it.

export const ROOT_HARMONIC = 16;
export const TUNINGS = ["octave", "just"];
const SAMPLES = 1024; // plenty for harmonics up to 127; conditionCycle() resamples to 256

// Just intonation ratios relative to the root, as [numerator, denominator].
export const CHORDS = [
  { id: "maj", name: "Major", ratios: [[1, 1], [5, 4], [3, 2]] },
  { id: "min", name: "Minor", ratios: [[1, 1], [6, 5], [3, 2]] },
  { id: "sus2", name: "Sus2", ratios: [[1, 1], [9, 8], [3, 2]] },
  { id: "sus4", name: "Sus4", ratios: [[1, 1], [4, 3], [3, 2]] },
  { id: "dim", name: "Diminished", ratios: [[1, 1], [6, 5], [36, 25]] },
  { id: "aug", name: "Augmented", ratios: [[1, 1], [5, 4], [25, 16]] },
  { id: "pow", name: "Power (root, fifth, octave)", ratios: [[1, 1], [3, 2], [2, 1]] },
  { id: "6", name: "Major 6", ratios: [[1, 1], [5, 4], [3, 2], [5, 3]] },
  { id: "7", name: "Dominant 7", ratios: [[1, 1], [5, 4], [3, 2], [7, 4]] },
  { id: "maj7", name: "Major 7", ratios: [[1, 1], [5, 4], [3, 2], [15, 8]] },
  { id: "m7", name: "Minor 7", ratios: [[1, 1], [6, 5], [3, 2], [9, 5]] },
  { id: "maj9", name: "Major 9", ratios: [[1, 1], [5, 4], [3, 2], [15, 8], [9, 4]] },
  { id: "m9", name: "Minor 9", ratios: [[1, 1], [6, 5], [3, 2], [9, 5], [9, 4]] },
];

export const chordById = (id) => CHORDS.find((c) => c.id === id) || null;

/** How many inversions a chord has: one per tone above the root, none for the power chord. */
export const inversionCount = (chord) => (chord.id === "pow" ? 0 : chord.ratios.length - 1);

const gcd = (a, b) => (b ? gcd(b, a % b) : a);
const lcm = (a, b) => (a / gcd(a, b)) * b;

/** Harmonic of each tone in root position, lowest first. */
function rootPosition(chord, tuning) {
  if (tuning === "just") {
    const den = chord.ratios.reduce((m, [, d]) => lcm(m, d), 1);
    const h = chord.ratios.map(([n, d]) => (n * den) / d);
    const g = h.reduce(gcd);
    return h.map((x) => x / g);
  }
  return chord.ratios.map(([n, d]) => Math.round((ROOT_HARMONIC * n) / d));
}

const cents = (ratio) => 1200 * Math.log2(ratio);

/**
 * The harmonics a chord uses. Inversion i moves the lowest i tones up an octave.
 * @returns {{harmonics:number[], rootHarmonic:number, worstCents:number}}
 *   worstCents: the largest distance of any tone from its just interval above the root.
 */
export function chordHarmonics(chordId, inversion = 0, tuning = "octave") {
  const chord = chordById(chordId);
  if (!chord) throw new Error("unknown chord: " + chordId);
  if (!TUNINGS.includes(tuning)) throw new Error("unknown tuning: " + tuning);
  const inv = Math.round(Number(inversion) || 0);
  if (inv < 0 || inv > inversionCount(chord)) throw new Error(chord.name + " has no inversion " + inv);

  const base = rootPosition(chord, tuning);
  let worstCents = 0;
  base.forEach((h, i) => {
    const [n, d] = chord.ratios[i];
    worstCents = Math.max(worstCents, Math.abs(cents(h / base[0]) - cents(n / d)));
  });
  const harmonics = base.map((h, i) => (i < inv ? 2 * h : h)).sort((a, b) => a - b);
  return { harmonics, rootHarmonic: inv ? 2 * base[0] : base[0], worstCents };
}

/** Semitones between the played note and the chord's root, e.g. 48 for harmonic 16. */
export const semitonesAbove = (harmonic) => 12 * Math.log2(harmonic);

/** A short name for the changes list: "Major chord", "Minor 7 chord, 2nd inversion". */
export function chordName(chordId, inversion = 0, tuning = "octave") {
  const chord = chordById(chordId);
  const ord = ["", "1st", "2nd", "3rd", "4th"][inversion] || inversion + "th";
  return chord.name + " chord" + (inversion ? ", " + ord + " inversion" : "") + (tuning === "just" ? ", just" : "");
}

function sumOfSines(harmonics, phases, n = SAMPLES) {
  const out = new Float64Array(n);
  harmonics.forEach((h, k) => {
    for (let i = 0; i < n; i++) out[i] += Math.sin((2 * Math.PI * h * i) / n + phases[k]);
  });
  return out;
}

const peakOf = (xs) => xs.reduce((m, x) => Math.max(m, Math.abs(x)), 0);

/**
 * Phases that keep the summed peak low, so the chord is loud once writeFrame() normalises it.
 * Schroeder's formula is the first candidate; a fixed pseudo-random search (same seed every
 * time, so the same chord always gives the same wave) usually beats it for sparse harmonics.
 */
function lowPeakPhases(harmonics, tries = 256) {
  const K = harmonics.length;
  let best = harmonics.map((_, k) => (Math.PI * k * k) / K);
  let bestPeak = peakOf(sumOfSines(harmonics, best, 256));
  let seed = 0x2545f491;
  const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
  for (let t = 0; t < tries; t++) {
    const phases = harmonics.map((_, k) => (k ? 2 * Math.PI * rnd() : 0));
    const peak = peakOf(sumOfSines(harmonics, phases, 256));
    if (peak < bestPeak) { bestPeak = peak; best = phases; }
  }
  return best;
}

/**
 * One cycle of the chord, ready for bank.makeOp().
 * @returns {{samples:Float64Array, name:string, harmonics:number[], topHarmonic:number,
 *            rootHarmonic:number, worstCents:number}}
 */
export function chordCycle(chordId, inversion = 0, tuning = "octave") {
  const { harmonics, rootHarmonic, worstCents } = chordHarmonics(chordId, inversion, tuning);
  const samples = sumOfSines(harmonics, lowPeakPhases(harmonics));
  return {
    samples,
    name: chordName(chordId, inversion, tuning),
    harmonics,
    topHarmonic: harmonics[harmonics.length - 1],
    rootHarmonic,
    worstCents,
  };
}
