// Schermo 128x64 a 1 bit: framebuffer (0/1, righe dall'alto), primitive di disegno, font 3x5 nostro
// (nessuna risorsa della Syntakt) e resa su canvas a scala intera, pixel per pixel.

export const W = 128, H = 64;
export type Fb = Uint8Array;

export const fb = (): Fb => new Uint8Array(W * H);

export function px(f: Fb, x: number, y: number, on = 1): void {
  x |= 0;
  y |= 0;
  if (x >= 0 && x < W && y >= 0 && y < H) f[y * W + x] = on;
}

export function fill(f: Fb, x: number, y: number, w: number, h: number, on = 1): void {
  for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) px(f, x + i, y + j, on);
}

export function rect(f: Fb, x: number, y: number, w: number, h: number, on = 1): void {
  hline(f, x, x + w - 1, y, on);
  hline(f, x, x + w - 1, y + h - 1, on);
  for (let j = 1; j < h - 1; j++) {
    px(f, x, y + j, on);
    px(f, x + w - 1, y + j, on);
  }
}

export function hline(f: Fb, x0: number, x1: number, y: number, on = 1): void {
  for (let x = Math.min(x0, x1); x <= Math.max(x0, x1); x++) px(f, x, y, on);
}

export function dots(f: Fb, x0: number, x1: number, y: number): void {
  for (let x = x0; x <= x1; x += 2) px(f, x, y);
}

export function line(f: Fb, x0: number, y0: number, x1: number, y1: number, on = 1): void {
  x0 = Math.round(x0); y0 = Math.round(y0); x1 = Math.round(x1); y1 = Math.round(y1);
  const dx = Math.abs(x1 - x0), dy = -Math.abs(y1 - y0), sx = x0 < x1 ? 1 : -1, sy = y0 < y1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    px(f, x0, y0, on);
    if (x0 === x1 && y0 === y1) return;
    const e2 = 2 * err;
    if (e2 >= dy) { err += dy; x0 += sx; }
    if (e2 <= dx) { err += dx; y0 += sy; }
  }
}

export function circle(f: Fb, cx: number, cy: number, r: number): void {
  let x = r, y = 0, err = 1 - r;
  while (x >= y) {
    for (const [a, b] of [[x, y], [y, x], [-y, x], [-x, y], [-x, -y], [-y, -x], [y, -x], [x, -y]]) px(f, cx + a, cy + b);
    y++;
    if (err < 0) err += 2 * y + 1;
    else { x--; err += 2 * (y - x) + 1; }
  }
}

// ---- font 3x5 proporzionale (disegnato per questo sito)
const G: Record<string, string> = {
  A: "010/101/111/101/101", B: "110/101/110/101/110", C: "011/100/100/100/011", D: "110/101/101/101/110",
  E: "111/100/110/100/111", F: "111/100/110/100/100", G: "011/100/101/101/011", H: "101/101/111/101/101",
  I: "111/010/010/010/111", J: "001/001/001/101/010", K: "101/101/110/101/101", L: "100/100/100/100/111",
  M: "10001/11011/10101/10001/10001", N: "1001/1101/1011/1001/1001", O: "010/101/101/101/010",
  P: "110/101/110/100/100", Q: "010/101/101/110/011", R: "110/101/110/101/101", S: "011/100/010/001/110",
  T: "111/010/010/010/010", U: "101/101/101/101/111", V: "101/101/101/101/010", W: "10001/10001/10101/11011/10001",
  X: "101/101/010/101/101", Y: "101/101/010/010/010", Z: "111/001/010/100/111",
  "0": "111/101/101/101/111", "1": "010/110/010/010/111", "2": "110/001/010/100/111", "3": "110/001/010/001/110",
  "4": "101/101/111/001/001", "5": "111/100/110/001/110", "6": "011/100/111/101/111", "7": "111/001/010/010/010",
  "8": "111/101/111/101/111", "9": "111/101/111/001/110",
  a: "000/011/101/101/011", b: "100/110/101/101/110", c: "000/011/100/100/011", d: "001/011/101/101/011",
  e: "000/010/111/100/011", f: "011/010/111/010/010", g: "000/011/101/011/110", h: "100/110/101/101/101",
  i: "1/0/1/1/1", k: "100/101/110/110/101", l: "1/1/1/1/1", m: "00000/11110/10101/10101/10101",
  n: "000/110/101/101/101", o: "000/010/101/101/010", p: "000/110/101/110/100", r: "000/101/110/100/100",
  s: "000/011/110/011/110", t: "010/111/010/010/011", u: "000/101/101/101/011", v: "000/101/101/101/010",
  w: "00000/10001/10101/10101/01010", y: "000/101/101/011/110", z: "000/111/011/100/111",
  ".": "0/0/0/0/1", ",": "00/00/00/01/10", ":": "0/1/0/1/0", "/": "001/001/010/100/100", "%": "101/001/010/100/101",
  "+": "000/010/111/010/000", "-": "000/000/111/000/000", "~": "0000/0000/0101/1010/0000", "<": "001/010/100/010/001",
  ">": "100/010/001/010/100", "(": "01/10/10/10/01", ")": "10/01/01/01/10", "'": "1/1/0/0/0", _: "000/000/000/000/111",
  "=": "000/111/000/111/000", "!": "1/1/1/0/1", "?": "110/001/010/000/010", "*": "000/101/010/101/000",
  "#": "01010/11111/01010/11111/01010", " ": "00/00/00/00/00",
};
const GLYPHS = new Map(Object.entries(G).map(([k, v]) => [k, v.split("/")]));
const glyph = (c: string): string[] => GLYPHS.get(c) ?? GLYPHS.get(c.toUpperCase()) ?? GLYPHS.get(" ")!;

export const FONT_H = 5;

export function measure(s: string, scale = 1): number {
  let w = 0;
  for (const c of s) w += glyph(c)[0].length + 1;
  return Math.max(0, w - 1) * scale;
}

/** align: 0 sinistra, 1 centro (x = centro), 2 destra (x = bordo destro). on = 0 scrive pixel spenti. */
export function text(f: Fb, x: number, y: number, s: string, align: 0 | 1 | 2 = 0, scale = 1, on = 1): void {
  if (align) x -= align === 1 ? Math.floor(measure(s, scale) / 2) : measure(s, scale) - 1;
  for (const c of s) {
    const g = glyph(c);
    for (let r = 0; r < 5; r++)
      for (let i = 0; i < g[r].length; i++) if (g[r][i] === "1") fill(f, x + i * scale, y + r * scale, scale, scale, on);
    x += (g[0].length + 1) * scale;
  }
}

/** Testo su fondo acceso (etichetta selezionata). */
export function inverse(f: Fb, x: number, y: number, s: string, align: 0 | 1 = 0): void {
  const w = measure(s), x0 = align ? x - Math.floor(w / 2) : x;
  fill(f, x0 - 1, y - 1, w + 2, 7);
  text(f, x0, y, s, 0, 1, 0);
}

// ---- resa su canvas: scala intera scelta dalla larghezza disponibile, pixel con un filo di separazione

// colori come ABGR (ImageData little-endian)
const rgba = (r: number, g: number, b: number): number => (255 << 24 | b << 16 | g << 8 | r) >>> 0;
const ON = rgba(0xe6, 0xf7, 0xff), OFF = rgba(0x06, 0x08, 0x0a), DIM = rgba(0x1a, 0x22, 0x26);

export class Oled {
  readonly fb = fb();
  private ctx: CanvasRenderingContext2D;
  private img: ImageData | null = null;
  private scale = 0;

  readonly canvas: HTMLCanvasElement;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    canvas.width = W;
    canvas.height = H;
  }

  /** Scala intera per la larghezza CSS data; ritorna true se e' cambiata. */
  fit(cssWidth: number): boolean {
    const dpr = window.devicePixelRatio || 1;
    const s = Math.max(1, Math.floor((cssWidth * dpr) / W));
    if (s === this.scale) return false;
    this.scale = s;
    this.canvas.width = W * s;
    this.canvas.height = H * s;
    this.canvas.style.width = `${(W * s) / dpr}px`;
    this.canvas.style.height = `${(H * s) / dpr}px`;
    this.img = this.ctx.createImageData(W * s, H * s);
    return true;
  }

  render(): void {
    if (!this.img) this.fit(this.canvas.clientWidth || W * 2);
    const s = this.scale, d = new Uint32Array(this.img!.data.buffer), rw = W * s, gap = s >= 4 ? 1 : 0;
    for (let y = 0; y < H; y++)
      for (let j = 0; j < s; j++) {
        const row = (y * s + j) * rw, edgeRow = j >= s - gap;
        for (let x = 0; x < W; x++) {
          const on = this.fb[y * W + x];
          let o = row + x * s;
          for (let i = 0; i < s; i++, o++) d[o] = on ? (edgeRow || i >= s - gap ? DIM : ON) : OFF;
        }
      }
    this.ctx.putImageData(this.img!, 0, 0);
  }
}
