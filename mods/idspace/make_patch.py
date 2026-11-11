"""Genera mods/idspace/patch.json: id dei parametri oltre 504 per le mod (README.md).

    python mods/idspace/make_patch.py          # richiede binutils m68k in WSL (CONTRIBUTING.md)

Nell'OS stock: descrittori a 0x4022D83C (505 x 52 B), oggetti per parametro a 0x41BA0A24 (505 x 84 B), limiti
`cmpi.l #0x1F9` / `#0x1F8` davanti a ogni accesso (un id fuori intervallo diventa l'id 0). La patch:
- sposta i riferimenti alla tabella dei descrittori sulla copia di N voci (idspace_layout.TABLE), che ids_boot
  riempie dalla lista di avvio di modarea prima dei costruttori statici;
- alza i limiti a N, tranne i tre cicli d'avvio che costruiscono le mappe inverse (gruppo / id interno -> id, CC):
  gli id delle mod restano fuori da quelle mappe e non ricevono CC MIDI;
- aggancia le due ricerche degli oggetti per parametro e quella degli elementi di pagina.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path[:0] = [str(REPO / "tools" / "unpack"), str(REPO / "tools" / "build")]
import eft  # noqa: E402
import idspace_layout as I  # noqa: E402
import modarea_layout as L  # noqa: E402
import registry  # noqa: E402

LOAD = 0x4000_0400
NOP = bytes.fromhex("4e71")
WSL_BINUTILS = "~/tools/m68k/root"
DESC, OBJ_BASE = 0x4022_D83C, 0x41BA_0A24
LOOPS = {0x4001_4708, 0x4002_4352, 0x400A_61A0}         # cicli d'avvio su tutti gli id: restano a 505
HOOKS = [(0x4007_BA2A, "222f00040c81", "ids_obj32", "oggetto per parametro"),
         (0x4007_BBE2, "222f00040c81", "ids_obj52", "oggetto per parametro: chiamata del testo (+20)"),
         (0x4007_BA48, "7224202f0004", "ids_page", "elemento di pagina dall'indice"),
         (0x400A_6598, "2f02702c2408", "ids_destcopy", "menu DEST: riga della machine (impacchettata)"),
         (0x400A_65D2, "2f02740c222f", "ids_destiid", "menu DEST: voce -> id interno"),
         (0x400A_5CE4, "222f00040c81", "ids_dest_type", "gruppo di un id (id delle mod senza gruppo: machine DESTX)"),
         (0x4001_1F96, "4ef9400a6464", "ids_lix_id", "indice logico -> id per la machine: voci DESTX della FX track")]
# menu DEST degli LFO (funzione 0x4004DF.., chiamata a 0x4004E47E): (indirizzo, byte stock, nuovi o simbolo da chiamare)
DEST_SITES = [
    (0x4004_E542, "4eb9400a5ce4", "ids_dest_first", "gruppo iniziale: prima voce da 16 bit"),
    (0x4001_476E, "45f9400a66e2", "lea:ids_dest_flags", "lista della manopola DEST: filtro dei flag (id delle mod: voci DESTX)"),
    (0x4004_E55A, "58aefcf8", "54aefcf8", "ciclo delle voci: puntatore della lista +2 (id da 16 bit)"),
    (0x4004_E55E, "47f9400a5ce42d58fcf0", "ids_destnext", "ciclo delle voci: voce da 16 bit, fine riga"),
    (0x4004_E66A, "7021", "7042", "ciclo delle voci: al massimo 66"),
    (0x4004_E090, "28330c04", "ids_op_e090", "testo della voce: id da 16 bit"),
    (0x4004_E096, "4eb9400a5ce4", "ids_dest_type", "testo della voce: gruppo (id delle mod senza gruppo: machine DESTX)"),
    (0x4004_E8A8, "2f320c044eb9400a5ce4", "ids_dest_e8a8", "gruppo della voce: id da 16 bit"),
    (0x4004_EC0A, "41f60c002f28ff7c4eb9400a5ce4", "ids_dest_ec0a", "encoder: gruppo della voce, id da 16 bit")]
CODE_END = I.EXT
IN_DEST, IN_DESTX_FIRST = (126, 128, 129, 130), 20     # posti DESTX 20..23 (registro)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stdout}{r.stderr}")
    return r.stdout


def sites(sec3: bytes):
    """(indirizzo, vecchio valore, nuovo valore, descrizione) degli operandi a 32 bit da cambiare."""
    out = []
    code = range(0x4001_0000 - LOAD, 0x400F_0000 - LOAD)
    for m in re.finditer(rb"\x0c[\x80-\x87]\x00\x00\x01[\xf8\xf9]|[\xb0-\xbf][\xbc\xfc]\x00\x00\x01[\xf8\xf9]", sec3):
        a = LOAD + m.start()
        if m.start() not in code or a in LOOPS:
            continue
        old = struct.unpack_from(">I", sec3, m.start() + 2)[0]
        out.append((a + 2, old, I.N - (0x1F9 - old), f"limite degli id {old:#x} -> {I.N - (0x1F9 - old):#x}"))
    for i in range(code.start, code.stop - 4, 2):
        v = struct.unpack_from(">I", sec3, i)[0]
        if DESC <= v < DESC + 52 * I.STOCK_N:
            off = v - DESC
            out.append((LOAD + i, v, I.TABLE + off, f"descrittori +{off:#x} -> copia di idspace"))
    return out


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    defs = {"TABLE": I.TABLE, "EXT": I.EXT, "OBJDEF": I.OBJDEF, "OBJ": I.OBJ, "BUILT": I.BUILT,
            "PAGEDEF": I.PAGEDEF, "FIRST": I.FIRST, "N": I.N, "PAGE_FIRST": I.PAGE_FIRST, "PAGE_N": I.PAGE_N,
            "ROWS": I.ROWS, "DESTX": I.DESTX, "DESTX_N": I.DESTX_N, "DEST_N": I.DEST_N, "DEST_ROWS": I.DEST_ROWS}
    with tempfile.TemporaryDirectory(prefix="idspace-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "idspace.S", tmp / "idspace.S")
        w = eft.to_wsl_path(tmp)
        bu = f"R={WSL_BINUTILS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        ds = " ".join(f"--defsym {k}={v}" for k, v in defs.items())
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-as -mcpu=54418 {ds} idspace.S -o i.o")
        wsl(bu + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={I.CODE:#x} -o i.elf i.o")
        wsl(bu + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary i.elf i.bin")
        syms = {p[2]: int(p[0], 16) for p in (l.split() for l in wsl(bu + "$R/usr/bin/m68k-linux-gnu-nm i.elf").splitlines())
                if len(p) == 3}
        blob = (tmp / "i.bin").read_bytes()
    if I.CODE + len(blob) > CODE_END:
        raise SystemExit(f"codice troppo grande: {len(blob)} B")
    slot = next(s for s, who in registry.BOOT_SLOTS.items() if who == "idspace")
    patches = [{"section": 3, "addr": f"{L.IMG + I.CODE - L.RAM:#010X}", "len": len(blob), "append": True,
                "hex": blob.hex(), "ram": f"{I.CODE:#010x}", "what": "(area mod) idspace: copia, oggetti, pagine"},
               {"section": 3, "addr": f"{L.boot_slot(slot):#010X}", "len": 4, "append": True,
                "hex": struct.pack(">I", syms["ids_boot"]).hex(), "ram": f"{L.RAM + L.BOOT_LIST + 4 * slot:#010x}",
                "what": f"lista di avvio di modarea, posto {slot}: ids_boot"}]
    for addr, orig, sym, what in HOOKS:
        old = sec3[addr - LOAD:addr - LOAD + 6]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 6, "expect_sha256": sha(old),
                        "hex": struct.pack(">HI", 0x4EF9, syms[sym]).hex(), "what": f"jmp {sym}: {what}"})
    for addr, orig, new, what in DEST_SITES:
        old = sec3[addr - LOAD:addr - LOAD + len(orig) // 2]
        if old.hex() != orig:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()}")
        if new == "ids_op_e090":
            code = blob[syms[new] - I.CODE:syms[new] - I.CODE + 4]
        elif new.startswith("lea:"):
            code = bytes.fromhex(orig[:4]) + struct.pack(">I", syms[new[4:]])
        elif new.startswith("ids_"):
            code = struct.pack(">HI", 0x4EB9, syms[new]) + NOP * ((len(old) - 6) // 2)
        else:
            code = bytes.fromhex(new)
        assert len(code) == len(old), (hex(addr), code.hex())
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": len(code), "expect_sha256": sha(old),
                        "hex": code.hex(), "what": what})
    # LFO della FX track: l'ingresso esterno tra le destinazioni (richiesta dalla macchina, RC1). Sono parametri
    # dell'OS (IN LR 126, BAL 128, DEL 129, REV 130: parole del blocco External Mixer del kit FX, che l'LFO modula
    # sul posto), solo assenti dalla riga 45 dell'OS. In mono valgono per IN L; IN R sta nel kitstore: non modulabile.
    for k, pid in enumerate(IN_DEST):
        at = I.destx(IN_DESTX_FIRST + k)
        patches.append({"section": 3, "addr": f"{L.IMG + at - L.RAM:#010X}", "len": 4, "append": True,
                        "hex": struct.pack(">BBH", 45, 3, pid).hex(), "ram": f"{at:#010x}",
                        "what": f"menu DEST della FX track: ingresso esterno, id {pid}"})
    found = sites(sec3)
    for addr, old, new, what in found:
        patches.append({"section": 3, "addr": f"{addr:#010X}", "len": 4, "expect_sha256": sha(struct.pack(">I", old)),
                        "hex": struct.pack(">I", new).hex(), "what": what})
    spec = {"name": "idspace", "os": "1.42", "requires": ["modarea"],
            "description": "Id dei parametri oltre 504 per le mod: copia dei descrittori con N voci, limiti alzati, "
                           "oggetti e pagine delle mod.",
            "generated_by": "mods/idspace/make_patch.py",
            "layout": {"table": f"{I.TABLE:#010x}", "n": I.N, "first": I.FIRST},
            "symbols": {k: f"{syms[k]:#010x}" for k in ("ids_boot", "ids_obj32", "ids_obj52", "ids_page", "ids_destcopy",
                                                         "ids_destiid", "ids_dest_boot", "ids_destnext", "ids_dest_first", "ids_dest_type", "ids_dest_flags")},
            "patches": patches}
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    n_lim = sum(1 for s in found if s[3].startswith("limite"))
    print(f"patch.json: {len(blob)} B a {I.CODE:#x}; {n_lim} limiti, {len(found) - n_lim} riferimenti ai descrittori")


if __name__ == "__main__":
    main()
