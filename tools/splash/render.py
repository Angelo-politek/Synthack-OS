"""Splash SyntHack: trasforma un logo in ASCII art in una bitmap 128x64 a 1 bit.

Il logo NON viene scritto con il font della Syntakt: lo disegniamo noi, al momento del build,
con un mini-font vettoriale (ogni simbolo dell'ASCII art e' un insieme di segmenti in un
quadrato unitario, disegnati a qualunque dimensione di cella). Cosi' l'anteprima PNG sul PC e'
identica, pixel per pixel, a quello che apparira' sullo schermo.

    python tools/splash/render.py --preview out/splash      # anteprime di tutti i candidati
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

W, H = 128, 64

# Simboli dell'ASCII art come segmenti ((x0, y0), (x1, y1)) nel quadrato [0,1]x[0,1] (y verso il basso)
GLYPHS: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {
    "_": [((0, 1), (1, 1))],
    "-": [((0, .5), (1, .5))],
    "|": [((.5, 0), (.5, 1))],
    "/": [((0, 1), (1, 0))],
    "\\": [((0, 0), (1, 1))],
    "(": [((.8, 0), (.3, .3)), ((.3, .3), (.3, .7)), ((.3, .7), (.8, 1))],
    ")": [((.2, 0), (.7, .3)), ((.7, .3), (.7, .7)), ((.7, .7), (.2, 1))],
    "[": [((.8, 0), (.3, 0)), ((.3, 0), (.3, 1)), ((.3, 1), (.8, 1))],
    "]": [((.2, 0), (.7, 0)), ((.7, 0), (.7, 1)), ((.7, 1), (.2, 1))],
    "<": [((1, .25), (0, .6)), ((0, .6), (1, .95))],
    ">": [((0, .25), (1, .6)), ((1, .6), (0, .95))],
    ",": [((.6, .8), (.3, 1))],
    ".": [((.5, 1), (.5, 1))],
    "'": [((.5, 0), (.5, .3))],
    "`": [((.3, 0), (.6, .3))],
    "~": [((0, .5), (.3, .35)), ((.3, .35), (.7, .6)), ((.7, .6), (1, .45))],
    "^": [((0, .4), (.5, 0)), ((.5, 0), (1, .4))],
    "#": [((0, y / 4), (1, y / 4)) for y in range(5)],
}

# Font bitmap 3x5 per il testo normale (versione)
TEXT_FONT = {
    "v": ["...", "...", "#.#", "#.#", ".#."], ".": ["...", "...", "...", "...", ".#."],
    "0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["##.", "..#", ".#.", "#..", "###"], "3": ["##.", "..#", ".#.", "..#", "##."],
    " ": ["...", "...", "...", "...", "..."],
}


@dataclass
class Bitmap:
    px: list[list[int]]

    @classmethod
    def blank(cls) -> "Bitmap":
        return cls([[0] * W for _ in range(H)])

    def set(self, x: int, y: int) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.px[y][x] = 1

    def line(self, x0: int, y0: int, x1: int, y1: int) -> None:      # Bresenham
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        err = dx + dy
        while True:
            self.set(x0, y0)
            if x0 == x1 and y0 == y1:
                return
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def to_bytes_rowmajor(self) -> bytes:
        """1 bit per pixel, righe da sinistra a destra, bit 7 = pixel piu' a sinistra.
        (Il formato reale del framebuffer Syntakt va ancora verificato: vedi docs/re-journal.md.)"""
        out = bytearray()
        for row in self.px:
            for x in range(0, W, 8):
                b = 0
                for k in range(8):
                    b = (b << 1) | row[x + k]
                out.append(b)
        return bytes(out)

    def to_bytes_syntakt(self) -> bytes:
        """Formato del framebuffer Syntakt (verificato su set_pixel 0x400F7140, OS 1.41):
        per colonne, 8 byte per colonna; byte = fb[x*8 + y//8], bit = 7 - (y % 8), 1 = acceso."""
        out = bytearray(W * H // 8)
        for y, row in enumerate(self.px):
            for x, v in enumerate(row):
                if v:
                    out[x * 8 + y // 8] |= 0x80 >> (y % 8)
        return bytes(out)

    @classmethod
    def from_bytes_syntakt(cls, raw: bytes) -> "Bitmap":
        bm = cls.blank()
        for x in range(W):
            for y in range(H):
                if raw[x * 8 + y // 8] & (0x80 >> (y % 8)):
                    bm.px[y][x] = 1
        return bm

    def to_png(self, path: Path, scale: int = 4) -> None:
        from PIL import Image
        img = Image.new("L", (W, H))
        img.putdata([255 if v else 0 for row in self.px for v in row])
        img = img.resize((W * scale, H * scale), Image.NEAREST)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path)


def draw_art(bm: Bitmap, art: list[str], cw: int, ch: int, x0: int, y0: int) -> None:
    for r, line in enumerate(art):
        for c, chch in enumerate(line):
            for (ax, ay), (bx, by) in GLYPHS.get(chch, []):
                X0, Y0 = x0 + c * cw, y0 + r * ch
                bm.line(X0 + round(ax * (cw - 1)), Y0 + round(ay * (ch - 1)),
                        X0 + round(bx * (cw - 1)), Y0 + round(by * (ch - 1)))


def draw_text(bm: Bitmap, text: str, x0: int, y0: int, scale: int = 1) -> None:
    for i, chch in enumerate(text):
        for r, row in enumerate(TEXT_FONT[chch]):
            for c, p in enumerate(row):
                if p == "#":
                    for sy in range(scale):
                        for sx in range(scale):
                            bm.set(x0 + (i * 4 + c) * scale + sx, y0 + r * scale + sy)


def compose(art: list[str], cw: int, ch: int, version: str = "v0.1") -> Bitmap:
    """Logo centrato in alto, versione centrata sotto."""
    bm = Bitmap.blank()
    aw, ah = max(len(l) for l in art) * cw, len(art) * ch
    vh = 5 * 2
    gap = 6
    top = max(0, (H - (ah + gap + vh)) // 2)
    draw_art(bm, art, cw, ch, (W - aw) // 2, top)
    vw = (len(version) * 4 - 1) * 2
    draw_text(bm, version, (W - vw) // 2, top + ah + gap, scale=2)
    return bm


def figlet(text: str, font: str) -> list[str]:
    import pyfiglet
    lines = [l.rstrip() for l in pyfiglet.figlet_format(text, font=font).split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return lines


CANDIDATES = {   # nome: (font figlet, larghezza cella, altezza cella)
    "A_mini": ("mini", 6, 8),
    "A_straight": ("straight", 6, 8),
    "B_small": ("small", 3, 6),
    "B_smslant": ("smslant", 3, 6),
    "B_cybermedium": ("cybermedium", 3, 8),
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--preview", type=Path, required=True, help="cartella per le anteprime PNG")
    a = ap.parse_args()
    for name, (font, cw, ch) in CANDIDATES.items():
        art = figlet("SyntHack", font)
        bm = compose(art, cw, ch)
        bm.to_png(a.preview / f"{name}.png")
        print(f"{name}: font '{font}', {max(map(len, art))}x{len(art)} caratteri, celle {cw}x{ch} px")


if __name__ == "__main__":
    main()
