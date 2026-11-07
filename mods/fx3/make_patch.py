"""Mod fx3: costruisce patch.json da fx3.c (terza mandata effetti: chorus, flanger, phaser, crusher).

- compila fx3.c per ColdFire e lo collega nell'area mod a +0xA000 (tabelle generate qui);
- aggancia la funzione di mix a blocchi: ciclo per traccia (0x4008F418), delay (0x4008F8A0: mandata
  del chorus verso il delay), somme del master (0x4008FB7C: bus 3, chorus a 24 kHz e ritorno);
- SND3 = id 72 (nascosto, salvato per traccia) nella pagina AMP 1 accanto a DEL e REV (PAN in pagina 2);
- pagina FX3 = pagina 25 dell'OS ("OB8", inutilizzata) come seconda pagina del tab REVERB, con gli id
  nascosti delle tracce MIDI 246..253 tramite vparams; valori salvati nel kit del pattern.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
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
import dualmono_layout as DL  # noqa: E402
import modarea_layout  # noqa: E402
import kitstore_layout as KS  # noqa: E402
import idspace_layout as IDS  # noqa: E402

_vp = importlib.util.spec_from_file_location("vparams_make_patch", REPO / "mods" / "vparams" / "make_patch.py")
vparams = importlib.util.module_from_spec(_vp)
_vp.loader.exec_module(vparams)

LOAD = 0x4000_0400
MODAREA_RAM, MODAREA_IMG = modarea_layout.RAM, modarea_layout.IMG
CODE_BASE, CODE_END = MODAREA_RAM + 0xA000, MODAREA_RAM + 0xDFF0   # linea a +0xE000 (4 KB)
TOOLS = "~/tools/m68k/root"
IDS_OBJ = IDS.OBJ_ENTRY                 # oggetto per parametro (id dell'OS o delle mod), ingresso fisso di idspace
NEW = {old: old + 259 for old in range(246, 254)} | {269: 513}   # id delle mod (idspace) al posto di quelli MIDI
# id stock modello dell'oggetto (dati +0..+19 e funzioni non sostituite), trovati nell'emulatore il 2026-11-06
# LFO della FX track: id interni di parole del kit FX che l'OS non usa (<= 70, limite dell'LFO), come DEST dei
# parametri della pagina FX3. Sei liberi: WID resta senza (e TYPE). Gruppo del riverbero (49): la pagina e' REVERB 2.
FX_SLOT = {247: 0x24, 248: 0x27, 250: 0x29, 251: 0x1A, 249: 0x46, 253: 0x37}
FX_GROUP = 49
FX_DESTX_FIRST = 14                     # posti DESTX (registro): 14..19
TEMPLATE = {246: 288, 247: 34, 248: 34, 249: 277, 250: 34, 251: 34, 252: 34, 253: 277, 269: 277}
CFLAGS = (f"-DFX_SLOT_SPD={FX_SLOT[247]} -DFX_SLOT_DEP={FX_SLOT[248]} -DFX_SLOT_TIME={FX_SLOT[250]} "
          f"-DFX_SLOT_FDBK={FX_SLOT[251]} -DFX_SLOT_DSND={FX_SLOT[249]} -DFX_SLOT_RSND={FX_SLOT[253]} ") + f"-DIDS_OBJ={IDS_OBJ:#x} -DMODAREA_RAM={modarea_layout.RAM:#x} -DDM_HDR={DL.HDR:#x} -DKS_FX3_R={DL.FX3_R:#x} -DKS_FX3_FX={KS.word(*KS.PARTS["fx3"][0]):#x} -mcpu=54418 -O2 -ffreestanding -fno-builtin -nostdlib -fno-pic -fno-common -Wall -Wextra"
FS = 24000                              # il chorus lavora a 24 kHz
DESC = 0x4022_D83C
P_PLAIN, G_KNOB, G_SEND, S_BAR = 0x41B9_EFD0, 0x41B9_ECD0, 0x41B9_EBD0, 0x41B9_E5D0
G_REV = 0x41B9_EBA0                     # icona della mandata al riverbero delle tracce (id 79)
VP_SLOT = 9                             # posti 9..15 della tabella di vparams

HOOKS = [  # (indirizzo, byte originali, simbolo, jsr/jmp, riempimento con nop)
    (0x4008_F418, "ae000900ae810900", "fx3_trk_hook", "ciclo per traccia: jsr fx3_trk_hook ; nop"),
    (0x4008_FB7C, "486efed848798000e0f0", "fx3_mix_hook",
     "somme del master: jsr fx3_mix_hook (bus 3, chorus, ritorno) ; nop ; nop"),
    (0x4019_4FEE, "42b941ba083c", "fx3_page_stub", "pagina 25 (FX3): caselle all'avvio"),
    (0x4019_4C14, "42b941ba06a0", "fx3_amp_stub", "pagine AMP: SND3 (72) in G della pagina 1, PAN (80) in E della pagina 2"),
    (0x4008_F53C, "588f342a0714", "fx3_in_hook", "mandate dell'ingresso: jsr fx3_in_hook (SND3 dell'ingresso)"),
    (0x4019_4F88, "42b941ba07f8", "fx3_in_page", "pagina External Mixer: SND3 dell'ingresso (269) nella casella C"),
    (0x4019_4D72, "42b941ba0724", "fx3_fxamp_stub",
     "pagine AMP della FX track: SND3 (144) in G della pagina 1, PAN (153) in E della pagina 2"),
]
# cicli dell'OS che completano i bus d'ingresso di delay e riverbero (bus += analogiche, saturato):
# jsr al nostro (stesso lavoro, meno istruzioni, piu' la mandata DEL / REV di FX3) ; jmp oltre il ciclo
BUS_LOOPS = [(0x4008_F852, "43f98000dbd441f98000dbd0", "fx3_del_hook", 0x4008_F882,
              "ingresso del delay: jsr fx3_del_hook (ciclo dell'OS + mandata DEL) ; jmp 0x4008F882"),
             (0x4008_F98A, "43f98000dbd441f98000dbd0", "fx3_rev_hook", 0x4008_F9BA,
              "ingresso del riverbero: jsr fx3_rev_hook (ciclo dell'OS + mandata REV) ; jmp 0x4008F9BA")]
# tab REVERB: vettore delle pagine {21} -> {21, 25}; nomi della pagina 25
REVERB_COUNT, REVERB_ARRAY = 0x4003_588C, 0x4003_5892
PAGE_NAMES = [(0x4019_4F5A, "4024ec67", "fx3_page_s", "pagina 25: nome breve"),
              (0x4019_4FA0, "40251e23", "fx3_page_l", "pagina 25: nome lungo")]
NO_STYLE = 0x41BA_0A68                 # +68 dell'id 0: std::function vuota (nessuno stile, come LFO MODE)
DRAW_HOOK, DRAW_ORIG = 0x4004_2CE0, "4fefffa048d77cfc"  # disegno dei tab DELAY/REVERB (caselle 5-6 = filtro)
# blocco della FX track del kit nel file: scrittura e lettura (le parole 0, 0x1A e 0x46 si perdevano)
KIT_HOOKS = [(0x400A_6E0E, "2f0b2f0a246f000c", "fx3_kser_hook", "kit -> file (FX track): jmp fx3_kser_hook ; nop"),
             (0x400A_6DA6, "4feffff448d71c00", "fx3_kdes_hook", "file -> kit (FX track): jmp fx3_kdes_hook ; nop")]
# classe del tab AMP: gli id sotto 73 (diversi da 73-74) erano trattati come parti dell'inviluppo, senza
# grafica propria; con bra -> "casella normale" SND3 (72) disegna la sua icona
AMP_FIX = (0x4004_1E84, "605c", "6058")
# stesso tab per la FX track: gli id 0x56..0x90 (144 = SND3 della FX track) come caselle normali
AMP_FIX_FX = (0x4004_1EB0, "6030", "602c")
# schermata ROUTING (FUNC+FX): la voce 13, vuota nell'OS, instrada il ritorno di FX3 nella FX track
ROUTE_JMP = [(0x4004_C5E2, "7224b28067000222", "fx3_rt_key", "ROUTING: tasto 13 -> jmp fx3_rt_key ; nop"),
             (0x4004_BF86, "4feffff048d7041c", "fx3_rt_get", "ROUTING: stato della voce -> jmp fx3_rt_get ; nop")]
ROUTE_DRAW = (0x4004_C242, "4eb9400f7468", "fx3_rt_draw", "ROUTING: voce 13 disegnata come 'FX3'")
ROUTE_LED = (0x4004_C480, "6716", "6712", "ROUTING: LED del tasto 13 acceso come le voci 14-16")
# parametri della pagina: id, nomi, massimo, default; prototipi dell'oggetto {offset: (operando, atteso,
# nuovo)}; correzioni ai campi +0/+4 per comportarsi come DEL (250): tipo 0, prototipo d3
PARAMS = [
    (246, "TYPE", "FX3 Type", 3, 0,
     {20: (0x4018_F416, 0x41B9_EF60, "fx3_proto_type"), 36: (0x4018_F424, 0x41B9_ECC0, "fx3_proto_type_gfx"),
      68: (0x4018_F440, 0x41B9_E670, NO_STYLE)},
     [(0x4018_F3F8, "2f05", "2f03"), (0x4018_F400, "7005", "7000")]),
    (247, "SPD", "Chorus Speed", 127, 60,
     {20: (0x4018_F468, 0x41B9_EF60, "fx3_proto_spd"), 36: (0x4018_F476, 0x41B9_ECC0, G_KNOB)},
     [(0x4018_F454, "2f05", "2f03"), (0x4018_F456, "7204", "7200")]),
    (248, "DEP", "Chorus Depth", 127, 64,
     {20: (0x4018_F4B8, 0x41B9_EF60, "fx3_proto_dep"), 36: (0x4018_F4C6, 0x41B9_ECC0, G_KNOB)},
     [(0x4018_F4A6, "2f05", "2f03"), (0x4018_F4AE, "23c241ba5b84", "42b941ba5b84")]),
    (250, "TIME", "Chorus Delay", 127, 64, {20: (0x4018_F55C, 0x41B9_EFD0, "fx3_proto_del")}, []),
    (251, "FDBK", "Chorus Feedback", 127, 0, {20: (0x4018_F5AC, 0x41B9_EFD0, "fx3_proto_fdbk")}, []),
    (252, "WID", "Chorus Width", 127, 64, {20: (0x4018_F5FC, 0x41B9_EFD0, "fx3_proto_wid")}, []),
    (249, "DEL", "FX3 to Delay", 127, 0,
     {20: (0x4018_F508, 0x41B9_EF40, "fx3_proto_vol"), 36: (0x4018_F51A, 0x41B9_EC40, G_SEND),
      68: (0x4018_F536, 0x41B9_E670, S_BAR)},
     [(0x4018_F4F6, "2f04", "2f03")]),
    (253, "REV", "FX3 to Reverb", 127, 0,
     {20: (0x4018_F64E, 0x41B9_EF60, "fx3_proto_vol"), 36: (0x4018_F660, 0x41B9_ECC0, G_REV),
      68: (0x4018_F67C, 0x41B9_E670, S_BAR)},
     [(0x4018_F63A, "2f05", "2f03"), (0x4018_F642, "7004", "7000")]),
]
G_MOD = 0x41B9_E730                     # icona MOD delle macchine (id 176)
# SND3 dell'ingresso: id 269 (vparams), oggetto come DEL di fx3 (249): {offset: (operando, atteso, nuovo)}
SND_IN = {"id": 269, "slot": 7, "objs": {20: (0x4018_FB6E, 0x41B9_EFD0, "fx3_proto_vol"),
                                         36: (0x4018_FB80, 0x41B9_E8B0, G_SEND), 68: (0x4018_FB9C, 0x41B9_E670, S_BAR)},
          "fix": [(0x4018_FB5A, "2f05", "2f03"), (0x4018_FB62, "7201", "7200")]}
# SND3 della FX track: id 144 (vparams; prima "Delay Time" nascosto della FX track, la cui parola tiene fx3)
SND_FX = {"id": 144, "slot": 8, "objs": {20: (0x4018_CC0E, 0x41B9_EFD0, "fx3_proto_vol"),
                                         36: (0x4018_CC20, 0x41B9_ECD0, G_SEND), 68: (0x4018_CC3C, 0x41B9_E670, S_BAR)}}
SND3 = {"id": 72, "g36": (0x4018_B53E, G_KNOB, G_MOD), "s68": (0x4018_B55A, 0x41B9_E670, S_BAR)}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def wsl(cmd: str) -> str:
    r = subprocess.run(["wsl.exe", "-e", "bash", "-lc", cmd], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"comando WSL fallito:\n{cmd}\n{r.stderr}")
    return r.stdout + r.stderr


# ---- tabelle (curve scelte qui, nessun dato dell'OS); i testi si compongono in fx3.c
CURVES = {  # nome: (unita', funzione di v = 0..127)
    "RATE_C": (1000, lambda v: 0.05 * 200 ** (v / 127)),       # chorus: 0.05 .. 10 Hz (mHz)
    "RATE_F": (1000, lambda v: 0.02 * 250 ** (v / 127)),       # flanger, phaser: 0.02 .. 5 Hz
    "DEP_C": (1000, lambda v: 8 * (v / 127) ** 2),             # chorus: 0 .. 8 ms (us)
    "TIME_C": (1000, lambda v: 1 + 29 * (v / 127) ** 1.5),     # chorus: 1 .. 30 ms
    "DEP_F": (1000, lambda v: 4 * (v / 127) ** 2),             # flanger: 0 .. 4 ms
    "TIME_F": (1000, lambda v: 0.1 + 7.9 * (v / 127) ** 2),    # flanger: 0.1 .. 8 ms
    "FREQ_P": (1, lambda v: 100 * 40 ** (v / 127)),            # phaser: 100 Hz .. 4 kHz
    "DRV_G": (256, lambda v: 10 ** (24 * v / 127 / 20)),       # crusher: 0 .. 24 dB (Q8)
}
PH_LO, PH_N = 20, 292                   # coefficienti del phaser: 20 Hz * 2^(i/32), fino a ~11 kHz


def txt_db(g: float) -> str:
    return "-inf" if g <= 0 else f"{20 * math.log10(g):.1f}dB"


def tables() -> str:
    # SIN_T e PH_A le legge solo l'assembly: globali (una static non usata dal C sparirebbe con un avviso)
    arr = lambda t, name, vals: (f"{'' if name in ('SIN_T', 'PH_A') else 'static '}const {t} {name}[{len(vals)}] = "
                                 f"{{{', '.join(str(v) for v in vals)}}};\n")
    txt = lambda name, vals: (f"static const char {name}[128][8] = {{" +
                              ", ".join(json.dumps(v) for v in vals) + "};\n")
    out = "/* generato da mods/fx3/make_patch.py */\n"
    out += arr("short", "SIN_T", [round(32767 * math.sin(2 * math.pi * i / 256)) for i in range(257)])
    for name, (unit, f) in CURVES.items():
        out += arr("u16", name, [round(unit * f(v)) for v in range(128)])
    out += arr("u16", "FIDX_P", [round(32 * 256 * math.log2(CURVES["FREQ_P"][1](v) / PH_LO)) for v in range(128)])
    t = [math.tan(math.pi * PH_LO * 2 ** (i / 32) / FS) for i in range(PH_N)]
    out += f"#define PH_N {PH_N}\n" + arr("s16", "PH_A", [round(4096 * (x - 1) / (x + 1)) for x in t])
    out += arr("s32", "VOL_Q15", [round(32767 * (v / 127) ** 2) for v in range(128)])
    out += txt("VOL_TXT", [txt_db((v / 127) ** 2) for v in range(128)])
    return out


def names() -> str:
    """Nomi in RAM (il tipo li riscrive): i descrittori puntano qui."""
    out = "".join(f'char fx3_n{i}_s[6] DATA = "{s}";\nchar fx3_n{i}_l[20] DATA = "{ln}";\n'
                  for i, (_, s, ln, *_r) in enumerate(PARAMS))
    return out + 'char fx3_page_l[12] DATA = "Chorus";\n'


def build_blob() -> tuple[bytes, dict[str, int], str]:
    with tempfile.TemporaryDirectory(prefix="fx3-") as tmp:
        tmp = Path(tmp)
        shutil.copy(HERE / "fx3.c", tmp / "fx3.c")
        (tmp / "fx3_tables.h").write_text(tables(), encoding="ascii")
        (tmp / "fx3_names.h").write_text(names(), encoding="ascii")
        w = eft.to_wsl_path(tmp)
        env = f"R={TOOLS}; export LD_LIBRARY_PATH=$R/usr/lib/x86_64-linux-gnu; cd {w}; "
        gcc = "$R/usr/bin/m68k-linux-gnu-gcc-13 -B$R/usr/libexec/gcc/m68k-linux-gnu/13/ -B$R/usr/bin/m68k-linux-gnu-"
        warn = wsl(env + f"{gcc} {CFLAGS} -c fx3.c -o fx3.o")
        if "warning" in warn:
            raise SystemExit(warn)
        wsl(env + f"$R/usr/bin/m68k-linux-gnu-ld -N -Ttext={CODE_BASE:#x} -e fx3_mix_hook -o fx3.elf fx3.o")
        undef = wsl(env + "$R/usr/bin/m68k-linux-gnu-nm -u fx3.elf").strip()
        if undef:
            raise SystemExit(f"simboli esterni non permessi (libgcc?): {undef}")
        heads = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -h fx3.elf")
        for name, size in re.findall(r"^\s*\d+\s+(\.\S+)\s+([0-9a-f]+)", heads, re.M):
            if name in (".bss", ".sbss") and int(size, 16):
                raise SystemExit("fx3.c non deve avere variabili in .bss")
        wsl(env + "$R/usr/bin/m68k-linux-gnu-objcopy -O binary -j .text -j .rodata -j .data fx3.elf fx3.bin")
        syms = {}
        for line in wsl(env + "$R/usr/bin/m68k-linux-gnu-nm fx3.elf").splitlines():
            parts = line.split()
            if len(parts) == 3:
                syms[parts[2]] = int(parts[0], 16)
        dis = wsl(env + "$R/usr/bin/m68k-linux-gnu-objdump -d -m m68k:isa-c:emac fx3.elf")
        blob = (tmp / "fx3.bin").read_bytes()
    return blob, syms, dis


def main() -> None:
    stock = REPO / "firmware" / "Syntakt_OS1.42.syx"
    sec3 = eft.unpack(stock, REPO / "unpacked" / stock.stem, ids=[3])[3].read_bytes()
    blob, syms, dis = build_blob()
    if CODE_BASE + len(blob) > CODE_END:
        raise SystemExit(f"non ci sta: {len(blob)} B")
    emac = [int(m[1], 16) for m in re.finditer(r"^\s*([0-9a-f]+):\s+(?:[0-9a-f]{4} ?)+\s+(\S+)\s*(.*)$", dis, re.M)
            if re.match(r"^(mac[lw]|msac[lw]|movclrl)$", m[2]) or re.search(r"%(acc|macsr|mask)", m[3])]
    sums = [x for x in emac if syms["fx3_sum"] <= x < syms["fx3_sum_end"]]      # somme del bus
    allowed = sorted([syms["fx3_trk_hook"], syms["fx3_trk_hook"] + 4, syms["fx3_macsr"]] + sums)
    if emac != allowed or len(sums) != (16 + 1) + (8 + 1) + (24 + 1) + 7 + 11:
        raise SystemExit(f"EMAC fuori dai trampolini e dalle somme: {[hex(a) for a in emac]}")

    def fixed(addr: int, new: bytes, what: str, expect: str | None = None) -> dict:
        old = sec3[addr - LOAD:addr - LOAD + len(new)]
        if expect is not None and old.hex() != expect:
            raise SystemExit(f"{addr:#x}: byte inattesi {old.hex()} (attesi {expect})")
        return {"section": 3, "addr": f"{addr:#010X}", "len": len(new), "expect_sha256": sha(old),
                "hex": new.hex(), "what": what}

    long = lambda v: struct.pack(">I", v)
    patches = [{"section": 3, "addr": f"{MODAREA_IMG + CODE_BASE - MODAREA_RAM:#010X}", "len": len(blob),
                "append": True, "hex": blob.hex(), "ram": f"{CODE_BASE:#010x}", "what": "(area mod) fx3.c"}]
    for addr, orig, sym, what in HOOKS:
        code = struct.pack(">HI", 0x4EB9, syms[sym])
        code += b"\x4e\x71" * ((len(orig) // 2 - len(code)) // 2)
        patches.append(fixed(addr, code, what, orig))
    for addr, orig, sym, back, what in BUS_LOOPS:
        patches.append(fixed(addr, struct.pack(">HIHI", 0x4EB9, syms[sym], 0x4EF9, back), what, orig))
    patches.append(fixed(REVERB_COUNT, bytes.fromhex("7202"), "tab REVERB: 2 pagine", "7201"))
    patches.append(fixed(REVERB_ARRAY, long(syms["fx3_reverb_pages"]), "tab REVERB: pagine {21, 25}", "401c8248"))
    for addr, orig, sym, what in PAGE_NAMES:
        patches.append(fixed(addr, long(syms[sym]), what, orig))
    for addr, orig, sym, what in KIT_HOOKS:
        patches.append(fixed(addr, struct.pack(">HI", 0x4EF9, syms[sym]) + bytes.fromhex("4e71"), what, orig))
    patches.append(fixed(DRAW_HOOK, struct.pack(">HI", 0x4EF9, syms["fx3_draw_hook"]) + bytes.fromhex("4e71"),
                         "tab DELAY/REVERB: pagina 25 col disegno generico a 8 caselle", DRAW_ORIG))
    for addr, orig, sym, what in ROUTE_JMP:
        patches.append(fixed(addr, struct.pack(">HI", 0x4EF9, syms[sym]) + bytes.fromhex("4e71"), what, orig))
    patches.append(fixed(ROUTE_DRAW[0], struct.pack(">HI", 0x4EB9, syms[ROUTE_DRAW[2]]), ROUTE_DRAW[3],
                         ROUTE_DRAW[1]))
    patches.append(fixed(ROUTE_LED[0], bytes.fromhex(ROUTE_LED[2]), ROUTE_LED[3], ROUTE_LED[1]))
    patches.append(fixed(AMP_FIX[0], bytes.fromhex(AMP_FIX[2]), "tab AMP: SND3 (72) come casella normale",
                         AMP_FIX[1]))
    resolve = lambda v: syms[v] if isinstance(v, str) else v
    # SND3: id 72, icona propria e barra, nomi
    r = DESC + 52 * SND3["id"]
    for key, what in (("g36", "+36: icona MOD delle macchine"), ("s68", "+68: barra")):
        addr, orig, new = SND3[key]
        patches.append(fixed(addr, long(resolve(new)), f"id 72 (SND3) {what}", f"{orig:08x}"))
    patches += [fixed(r + 40, long(syms["fx3_snd_l"]), "id 72: nome lungo 'FX3 Send'"),
                fixed(r + 48, long(syms["fx3_snd_s"]), "id 72: nome breve 'FX3'"),
                fixed(r + 36, long(0xE00), "id 72: destinazione di modulazione (LFO), come la mandata DEL (78)",
                      "00000000")]
    def ext(at: int, data: bytes, what: str) -> dict:
        """Patch accodata nell'area mod (descrittori, oggetti di idspace)."""
        return {"section": 3, "addr": f"{modarea_layout.IMG + at - modarea_layout.RAM:#010X}", "len": len(data),
                "append": True, "hex": data.hex(), "ram": f"{at:#010x}", "what": what}

    def new_id(old: int, mx: int, df: int, nl: int, ns: int, protos: dict, what: str) -> list[dict]:
        """Id delle mod al posto di `old`: descrittore (quello stock di `old` con intervallo e nomi nostri) e
        oggetto (modello + prototipi). Il gruppo e l'id interno restano quelli di `old`: le mappe inverse
        dell'OS contengono solo gli id stock (idspace), vparams intercetta lettura e scrittura."""
        pid = NEW[old]
        d = bytearray(sec3[DESC - LOAD + 52 * old:DESC - LOAD + 52 * old + 52])
        d[8:20] = struct.pack(">III", 0, mx << 8, df << 8)
        d[24:32] = struct.pack(">II", 0xFFFF_FFFF, 0xFFFF_FFFF)                 # niente CC ne' NRPN
        d[40:44], d[48:52] = long(nl), long(ns)
        if old in FX_SLOT:                                                       # DEST dell'LFO della FX track
            d[0:8] = struct.pack(">ii", FX_GROUP, FX_SLOT[old])
        o = struct.pack(">4I", TEMPLATE[old], *(resolve(protos[f]) if f in protos else 0 for f in (20, 36, 68)))
        return [ext(IDS.desc(pid), bytes(d), f"idspace: descrittore dell'id {pid} ({what})"),
                ext(IDS.objdef(pid), o, f"idspace: oggetto dell'id {pid} ({what}), modello {TEMPLATE[old]}")]

    # SND3 dell'ingresso
    patches.append(vparams.entry(SND_IN["slot"], NEW[269], syms["fx3_in_get"], syms["fx3_in_set"], "fx3 SND3 IN"))
    patches += new_id(269, 127, 0, syms["fx3_in_l"], syms["fx3_snd_s"],
                      {f: v[2] for f, v in SND_IN["objs"].items()}, "SND3 dell'ingresso")
    # SND3 della FX track
    patches.append(fixed(AMP_FIX_FX[0], bytes.fromhex(AMP_FIX_FX[2]), "tab AMP: SND3 della FX track (144) come "
                         "casella normale", AMP_FIX_FX[1]))
    r = DESC + 52 * SND_FX["id"]
    patches.append(vparams.entry(SND_FX["slot"], SND_FX["id"], syms["fx3_fx_get"], syms["fx3_fx_set"], "fx3 SND3 FX"))
    for off, (addr, orig, new) in SND_FX["objs"].items():
        patches.append(fixed(addr, long(resolve(new)), f"id 144 +{off}: {resolve(new):#010x}", f"{orig:08x}"))
    patches += [fixed(r + 8, struct.pack(">III", 0, 0x7F00, 0), "id 144 -> SND3 della FX track: min, max, default"),
                fixed(r + 40, long(syms["fx3_fx_l"]), "id 144: nome lungo 'FX Track FX3 Send'"),
                fixed(r + 48, long(syms["fx3_snd_s"]), "id 144: nome breve 'FX3'"),
                fixed(r + 28, long(0xFFFF_FFFF), "id 144: niente NRPN", "00000097")]
    # pagina FX3
    for k, old in enumerate((247, 248, 250, 251, 249, 253)):             # menu DEST della FX track (riga 45)
        patches.append(ext(IDS.destx(FX_DESTX_FIRST + k), struct.pack(">BBH", 45, 3, NEW[old]),
                           f"idspace: menu DEST della FX track, voce {NEW[old]}"))
    for n, (pid, short, ln, mx, df, protos, extra) in enumerate(PARAMS):
        patches.append(vparams.entry(VP_SLOT + n, NEW[pid], syms["fx3_get"], syms["fx3_set"], f"fx3 {short}"))
        patches += new_id(pid, mx, df, syms[f"fx3_n{n}_l"], syms[f"fx3_n{n}_s"],
                          {f: v[2] for f, v in protos.items()}, f"pagina FX3, {short}")
    spec = {
        "name": "fx3", "os": "1.42", "requires": ["modarea", "vparams", "fastmix", "kitstore", "idspace"],
        "description": "Terza mandata effetti: SND3 per traccia (pagina AMP 2) verso un chorus stereo; "
                       "regolazioni e livello di ritorno sulla pagina 2 del tab REVERB.",
        "generated_by": "mods/fx3/make_patch.py",
        "symbols": {k: f"{syms[k]:#010x}" for k in (
            "fx3_trk_hook", "fx3_del_hook", "fx3_macsr", "fx3_mix_hook", "fx3_page_stub", "fx3_amp_stub",
            "fx3_s", "fx3_ret", "fx3_get", "fx3_set", "fx3_p", "fx3_tgt", "fx3_cur", "fx3_moving",
            "fx3_bus", "fx3_wet", "fx3_idle", "fx3_clr", "fx3_reverb_pages", "fx3_fmt_spd", "fx3_fmt_del", "fx3_fmt_dep",
            "fx3_fmt_type", "fx3_fmt_fdbk", "fx3_fmt_wid", "fx3_fmt_vol", "fx3_type_gfx",
            "fx3_draw_hook", "fx3_mgr", "fx3_phs", "fx3_n1_s", "fx3_n3_s", "fx3_n3_l", "fx3_page_l",
            "fx3_kser_hook", "fx3_kdes_hook", "fx3_rev_hook", "fx3_addsat", "fx3_in_hook", "fx3_in_page", "fx3_in_get", "fx3_in_set", "fx3_fx_get", "fx3_fx_set", "fx3_fxamp_stub",
            "fx3_route", "fx3_rt_key", "fx3_rt_get", "fx3_rt_draw", "fx3_lfo_on", "fx3_lfo_tick")},
        "emac_sites": [f"{x:#010x}" for x in allowed],
        "patches": patches,
    }
    (HERE / "patch.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (REPO / "out" / "fx3").mkdir(parents=True, exist_ok=True)
    (REPO / "out" / "fx3" / "fx3.lst").write_text(dis, encoding="utf-8")
    print(f"patch.json: {len(blob)} B a {CODE_BASE:#x}..{CODE_BASE + len(blob):#x}")


if __name__ == "__main__":
    main()
